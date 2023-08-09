#!/usr/bin/env python

"""
This module is the entry point executed when you run `conda.exe` on the command line.

It will end up calling the `conda` CLI, but it intercepts the call to do some
preliminary work and handling some special cases that arise when PyInstaller is involved.
"""
import os
import sys
from multiprocessing import freeze_support


def _create_dummy_executor(*args, **kwargs):
    "use this for debugging, because ProcessPoolExecutor isn't pdb/ipdb friendly"
    from concurrent.futures import Executor

    class DummyExecutor(Executor):
        def map(self, func, *iterables):
            for iterable in iterables:
                for thing in iterable:
                    yield func(thing)

    return DummyExecutor(*args, **kwargs)


def _fix_sys_path():
    """
    Before any more imports, leave cwd out of sys.path for internal 'conda shell.*' commands.
    see https://github.com/conda/conda/issues/6549
    """
    if (
        len(sys.argv) > 1
        and sys.argv[1].startswith("shell.")
        and sys.path
        and sys.path[0] == ""
    ):
        # The standard first entry in sys.path is an empty string,
        # and os.path.abspath('') expands to os.getcwd().
        del sys.path[0]


def _constructor_parse_cli():
    import argparse

    # This might be None!
    CPU_COUNT = os.cpu_count()
    # See validation results for magic number of 3
    # https://dholth.github.io/conda-benchmarks/#extract.TimeExtract.time_extract?
    #   conda-package-handling=2.0.0a2&p-format='.conda'&p-format='.tar.bz2'&p-lang='py'
    DEFAULT_NUM_WORKERS = 1 if not CPU_COUNT else min(3, CPU_COUNT)

    class _NumProcessorsAction(argparse.Action):
        def __call__(self, parser, namespace, values, option_string=None):
            """Converts a string representing the max number of workers to an integer
            while performing validation checks; raises argparse.ArgumentError if anything fails.
            """

            ERROR_MSG = f"Value must be int between 1 and the CPU count ({CPU_COUNT})."
            try:
                num = int(values)
            except ValueError as exc:
                raise argparse.ArgumentError(self, ERROR_MSG) from exc
            if num < 1:
                raise argparse.ArgumentError(self, ERROR_MSG)

            # cpu_count can return None, so skip this check if that happens
            if CPU_COUNT:
                # See Windows notes for magic number of 61
                # https://docs.python.org/3/library/concurrent.futures.html#processpoolexecutor
                max_cpu_num = min(CPU_COUNT, 61) if os.name == "nt" else CPU_COUNT
                if num > max_cpu_num:
                    raise argparse.ArgumentError(self, ERROR_MSG)

            setattr(namespace, self.dest, num)

    p = argparse.ArgumentParser(description="constructor helper subcommand")
    p.add_argument(
        "--prefix",
        action="store",
        required=True,
        help="path to the conda environment to operate on",
    )
    # We can't add this option yet because micromamba doesn't support it
    # Instead we check for the CONDA_ROOT_PREFIX env var; see below
    # p.add_argument(
    #     "--root-prefix",
    #     action="store",
    #     help="path to root path of the conda installation; "
    #     "defaults to --prefix if not provided",
    # )
    p.add_argument(
        "--num-processors",
        default=DEFAULT_NUM_WORKERS,
        action=_NumProcessorsAction,
        help="Number of processors to use with --extract-conda-pkgs",
    )

    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument(
        "--extract-conda-pkgs",
        action="store_true",
        help="extract conda packages found in prefix/pkgs",
    )
    g.add_argument(
        "--extract-tarball",
        action="store_true",
        help="extract tarball from stdin",
    )
    g.add_argument(
        "--make-menus",
        nargs="*",
        metavar="PKG_NAME",
        help="create menu items for the given packages; "
        "if none are given, create menu items for all packages "
        "in the environment specified by --prefix",
    )
    g.add_argument(
        "--rm-menus",
        action="store_true",
        help="remove menu items for all packages "
        "in the environment specified by --prefix",
    )

    args, args_unknown = p.parse_known_args()

    args.prefix = os.path.abspath(args.prefix)
    args.root_prefix = os.path.abspath(os.environ.get("CONDA_ROOT_PREFIX", args.prefix))

    if "--num-processors" in sys.argv and not args.extract_conda_pkgs:
        raise argparse.ArgumentError(
            "--num-processors can only be used with --extract-conda-pkgs"
        )

    return args, args_unknown


def _constructor_extract_conda_pkgs(prefix, max_workers=None):
    from concurrent.futures import ProcessPoolExecutor

    import tqdm
    from conda.base.constants import CONDA_PACKAGE_EXTENSIONS
    from conda_package_handling import api

    executor = ProcessPoolExecutor(max_workers=max_workers)

    os.chdir(os.path.join(prefix, "pkgs"))
    flist = []
    for ext in CONDA_PACKAGE_EXTENSIONS:
        for pkg in os.listdir(os.getcwd()):
            if pkg.endswith(ext):
                fn = os.path.join(os.getcwd(), pkg)
                flist.append(fn)
    with tqdm.tqdm(total=len(flist), leave=False) as t:
        for fn, _ in zip(flist, executor.map(api.extract, flist)):
            t.set_description("Extracting : %s" % os.path.basename(fn))
            t.update()


def _constructor_extract_tarball():
    import tarfile

    t = tarfile.open(mode="r|*", fileobj=sys.stdin.buffer)
    t.extractall()
    t.close()


def _constructor_menuinst(prefix, pkg_names=None, root_prefix=None, remove=False):
    import importlib.util

    root_prefix = root_prefix or prefix

    utility_script = os.path.join(root_prefix, "Lib", "_nsis.py")
    spec = importlib.util.spec_from_file_location("constructor_utils", utility_script)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    if remove:
        module.rm_menus(prefix=prefix, root_prefix=prefix)
    elif pkg_names is not None:
        module.mk_menus(
            remove=False,
            prefix=prefix,
            pkg_names=pkg_names,
            root_prefix=prefix,
        )


def _constructor_subcommand():
    r"""
    This is the entry point for the `conda constructor` subcommand. This subcommand
    only exists in conda-standalone for now. constructor uses it to:

    - extract conda packages
    - extract the tarball payload contained in the shell installers
    - invoke menuinst to create and remove menu items on Windows

    It is supported by a module included in `constructor`, `_nsis.py`, which is placed
    in `$INSTDIR\Lib\_nsis.py` on Windows installations.
    """
    args, _ = _constructor_parse_cli()
    os.chdir(args.prefix)

    if args.extract_conda_pkgs:
        _constructor_extract_conda_pkgs(args.prefix, max_workers=args.num_processors)

    elif args.extract_tarball:
        _constructor_extract_tarball()

    # when called with --make-menus and no package names, the value is an empty list
    # hence the explicit check for None
    elif (args.make_menus is not None) or args.rm_menus:
        if sys.platform != "win32":
            raise NotImplementedError(
                "Menu creation and removal is only supported on Windows"
            )
        _constructor_menuinst(
            prefix=args.prefix,
            pkg_names=args.make_menus,
            remove=args.rm_menus,
            root_prefix=args.root_prefix,
        )


def _python_subcommand():
    """
    Since conda-standalone is actually packaging a full Python interpreter,
    we can leverage it by exposing an entry point that mimics its CLI.
    This can become useful while debugging.

    We don't use argparse because it might absorb some of the arguments.
    We are only trying to mimic a subset of the Python CLI, so it can be done
    by hand. Options we support are:

    - -V/--version: print the version
    - a path: run the file or directory/__main__.py
    - -c: run the command
    - -m: run the module
    - no arguments: start an interactive session
    - stdin: run the passed input as if it was '-c'
    """

    del sys.argv[1]  # remove the 'python' argument
    first_arg = sys.argv[1] if len(sys.argv) > 1 else None

    if first_arg is None:
        if sys.stdin.isatty():  # interactive
            from code import InteractiveConsole

            class CondaStandaloneConsole(InteractiveConsole):
                pass

            return CondaStandaloneConsole().interact(exitmsg="")
        else:  # piped stuff
            for line in sys.stdin:
                exec(line)
            return

    if first_arg in ("-V", "--version"):
        print("Python " + ".".join([str(x) for x in sys.version_info[:3]]))
        return

    import runpy

    if os.path.exists(first_arg):
        runpy.run_path(first_arg, run_name="__main__")
        return

    if len(sys.argv) > 2:
        if first_arg == "-m":
            del sys.argv[1]  # delete '-m'
            mod_name = sys.argv[1]  # save the actual module name
            del sys.argv[1]  # delete the module name
            runpy.run_module(mod_name, alter_sys=True, run_name="__main__")
            return
        elif first_arg == "-c":
            del sys.argv[0]  # remove the executable, but keep '-c' in sys.argv
            cmd = sys.argv[1]  # save the actual command
            del sys.argv[1]  # remove the passed command
            exec(cmd)  # the extra arguments are still in sys.argv
            return

    print("Usage: conda.exe python [-V] [-c cmd | -m mod | file] [arg] ...")
    if first_arg in ("-h", "--help"):
        return
    return 1


def _conda_main():
    from conda.cli import main

    _fix_sys_path()
    main()


def main():
    # https://docs.python.org/3/library/multiprocessing.html#multiprocessing.freeze_support
    freeze_support()
    if len(sys.argv) > 1:
        if sys.argv[1] == "constructor":
            return _constructor_subcommand()
        elif sys.argv[1] == "python":
            return _python_subcommand()

    return _conda_main()


if __name__ == "__main__":
    sys.exit(main())
