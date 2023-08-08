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

    p = argparse.ArgumentParser(description="constructor helper subcommand")
    p.add_argument(
        "--prefix",
        action="store",
        required=True,
        help="path to the conda environment to operate on",
    )
    p.add_argument(
        "--root-prefix",
        action="store",
        help="path to root path of the conda installation; "
        "defaults to --prefix if not provided",
    )
    p.add_argument(
        "--extract-conda-pkgs",
        action="store_true",
        help="extract conda packages found in prefix/pkgs",
    )
    p.add_argument(
        "--extract-tarball",
        action="store_true",
        help="extract tarball from stdin",
    )
    p.add_argument(
        "--make-menus",
        nargs="*",
        metavar="PKG_NAME",
        help="create menu items for the given packages; "
        "if none are given, create menu items for all packages "
        "in the environment specified by --prefix",
    )
    p.add_argument(
        "--rm-menus",
        action="store_true",
        help="remove menu items for all packages "
        "in the environment specified by --prefix",
    )

    args, args_unknown = p.parse_known_args()

    args.prefix = os.path.abspath(args.prefix)
    if args.root_prefix is None:
        args.root_prefix = args.prefix
    else:
        args.root_prefix = os.path.abspath(args.root_prefix)

    return args, args_unknown


def _constructor_extract_conda_pkgs():
    from concurrent.futures import ProcessPoolExecutor

    import tqdm
    from conda_package_handling import api
    from conda.base.constants import CONDA_PACKAGE_EXTENSIONS

    executor = ProcessPoolExecutor()

    os.chdir("pkgs")
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
    """
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
        _constructor_extract_conda_pkgs()

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

    return _conda_main()


if __name__ == "__main__":
    sys.exit(main())
