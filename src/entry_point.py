#!/usr/bin/env python

"""
This module is the entry point executed when you run `conda.exe` on the command line.

It will end up calling the `conda` CLI, but it intercepts the call to do some
preliminary work and handling some special cases that arise when PyInstaller is involved.
"""

import os
import sys
from multiprocessing import freeze_support
from pathlib import Path

from conda_constructor.extract import (
    DEFAULT_NUM_PROCESSORS,
    _NumProcessorsAction,
    extract_conda_pkgs,
    extract_tarball,
)
from conda_constructor.menuinst import install_shortcut
from conda_constructor.uninstall import uninstall

if os.name == "nt" and "SSLKEYLOGFILE" in os.environ:
    # This causes a crash with requests 2.32+ on Windows
    # Root cause is 'urllib3.util.ssl_.create_urllib3_context()'
    # See https://github.com/conda/conda-standalone/issues/86
    del os.environ["SSLKEYLOGFILE"]

if "CONDARC" not in os.environ:
    os.environ["CONDARC"] = os.path.join(sys.prefix, ".condarc")


def _fix_sys_path():
    """
    Before any more imports, leave cwd out of sys.path for internal 'conda shell.*' commands.
    see https://github.com/conda/conda/issues/6549
    """
    if len(sys.argv) > 1 and sys.argv[1].startswith("shell.") and sys.path and sys.path[0] == "":
        # The standard first entry in sys.path is an empty string,
        # and os.path.abspath('') expands to os.getcwd().
        del sys.path[0]


def _constructor_parse_cli():
    import argparse

    # Remove "constructor" so that it does not clash with the uninstall subcommand
    del sys.argv[1]
    p = argparse.ArgumentParser(
        prog="conda.exe constructor", description="constructor helper subcommand"
    )
    # Cannot use argparse to make this a required argument
    # or `conda.exe constructor uninstall --prefix`
    # will not work (would have to be `conda constructor --prefix uninstall`).
    # Requiring `--prefix` will be enforced manually later.
    p.add_argument(
        "--prefix",
        action="store",
        required=False,
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
        default=DEFAULT_NUM_PROCESSORS,
        metavar="N",
        action=_NumProcessorsAction,
        help="Number of processors to use with --extract-conda-pkgs. "
        "Value must be int between 0 (auto) and the number of processors. "
        f"Defaults to {DEFAULT_NUM_PROCESSORS}.",
    )

    g = p.add_mutually_exclusive_group()
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
        help="remove menu items for all packages in the environment specified by --prefix",
    )

    subcommands = p.add_subparsers(dest="command")
    uninstall_subcommand = subcommands.add_parser(
        "uninstall",
        description="Uninstalls a conda directory and all environments inside the directory.",
    )
    uninstall_subcommand.add_argument(
        "--prefix",
        action="store",
        required=True,
        help="Path to the conda directory to uninstall.",
    )
    uninstall_subcommand.add_argument(
        "--remove-caches",
        action="store_true",
        required=False,
        help=(
            "Removes the notices cache and runs conda --clean --all to clean package caches"
            " outside the installation directory."
            " This is especially useful when pkgs_dirs is set in a .condarc file."
            " Not recommended with multiple conda installations when softlinks are enabled."
        ),
    )
    uninstall_subcommand.add_argument(
        "--remove-config-files",
        choices=["user", "system", "all"],
        default=None,
        required=False,
        help=(
            "Removes all .condarc files."
            " `user` removes the files inside the current user's"
            " home directory and `system` removes all files outside of that directory."
            " Not recommended when multiple conda installations are on the system"
            " or when running on an environments directory."
        ),
    )
    uninstall_subcommand.add_argument(
        "--remove-user-data",
        action="store_true",
        required=False,
        help=(
            "Removes the ~/.conda directory."
            " Not recommended when multiple conda installations are on the system"
            " or when running on an environments directory."
        ),
    )

    args, args_unknown = p.parse_known_args()

    if args.command != "uninstall":
        group_args = getattr(g, "_group_actions")
        if all(getattr(args, arg.dest, None) in (None, False) for arg in group_args):
            required_args = [arg.option_strings[0] for arg in group_args]
            raise argparse.ArgumentError(
                None, f"one of the following arguments are required: {'/'.join(required_args)}"
            )

    if args.prefix is None:
        raise argparse.ArgumentError(None, "the following arguments are required: --prefix")

    args.prefix = Path(os.path.expandvars(args.prefix)).expanduser().resolve()
    args.root_prefix = Path(os.environ.get("CONDA_ROOT_PREFIX", args.prefix))

    if "--num-processors" in sys.argv and not args.extract_conda_pkgs:
        raise argparse.ArgumentError(
            None, "--num-processors can only be used with --extract-conda-pkgs"
        )

    return args, args_unknown


def _constructor_subcommand():
    r"""
    This is the entry point for the `conda constructor` subcommand. This subcommand
    only exists in conda-standalone for now. constructor uses it to:

    - extract conda packages
    - extract the tarball payload contained in the shell installers
    - invoke menuinst to create and remove menu items on Windows
    """
    args, _ = _constructor_parse_cli()

    if args.command == "uninstall":
        uninstall(
            args.prefix,
            remove_caches=args.remove_caches,
            remove_config_files=args.remove_config_files,
            remove_user_data=args.remove_user_data,
        )
        # os.chdir will break conda --clean, so return early
        return
    if args.extract_conda_pkgs:
        extract_conda_pkgs(args.prefix, max_workers=args.num_processors)

    elif args.extract_tarball:
        extract_tarball(args.prefix)

    # when called with --make-menus and no package names, the value is an empty list
    # hence the explicit check for None
    elif (args.make_menus is not None) or args.rm_menus:
        install_shortcut(
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

    if sys.argv[1] == "python":
        del sys.argv[1]
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


def _patch_root_prefix():
    root_prefix = Path(sys.executable).parent
    if (root_prefix / "_internal").is_dir():
        os.environ.setdefault("CONDA_ROOT", str(root_prefix))
        os.environ.setdefault("CONDA_ROOT_PREFIX", str(root_prefix))


def _conda_main():
    from conda.cli import main

    _fix_sys_path()
    try:
        no_rc = sys.argv.index("--no-rc")
        os.environ["CONDA_RESTRICT_RC_SEARCH_PATH"] = "1"
        del sys.argv[no_rc]
    except ValueError:
        pass
    return main()


def main():
    # https://docs.python.org/3/library/multiprocessing.html#multiprocessing.freeze_support
    freeze_support()
    if len(sys.argv) > 1:
        if sys.argv[1] == "constructor":
            return _constructor_subcommand()
        # Some parts of conda call `sys.executable -m`, so conda-standalone needs to
        # interpret `conda.exe -m` as `conda.exe python -m`.
        elif sys.argv[1] == "python" or sys.argv[1] == "-m":
            return _python_subcommand()

    _patch_root_prefix()
    return _conda_main()


if __name__ == "__main__":
    sys.exit(main())
