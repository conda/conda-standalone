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
from typing import List

if os.name == "nt" and "SSLKEYLOGFILE" in os.environ:
    # This causes a crash with requests 2.32+ on Windows
    # Root cause is 'urllib3.util.ssl_.create_urllib3_context()'
    # See https://github.com/conda/conda-standalone/issues/86
    del os.environ["SSLKEYLOGFILE"]


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
    # https://dholth.github.io/conda-benchmarks/#extract.TimeExtract.time_extract?conda-package-handling=2.0.0a2&p-format='.conda'&p-format='.tar.bz2'&p-lang='py'  # noqa
    DEFAULT_NUM_PROCESSORS = 1 if not CPU_COUNT else min(3, CPU_COUNT)

    class _NumProcessorsAction(argparse.Action):
        def __call__(self, parser, namespace, values, option_string=None):
            """Converts a string representing the max number of workers to an integer
            while performing validation checks; raises argparse.ArgumentError if anything fails.
            """

            ERROR_MSG = f"Value must be int between 0 (auto) and {CPU_COUNT}."
            try:
                num = int(values)
            except ValueError as exc:
                raise argparse.ArgumentError(self, ERROR_MSG) from exc

            # cpu_count can return None, so skip this check if that happens
            if CPU_COUNT:
                # See Windows notes for magic number of 61
                # https://docs.python.org/3/library/concurrent.futures.html#processpoolexecutor
                max_cpu_num = min(CPU_COUNT, 61) if os.name == "nt" else CPU_COUNT
                if num > max_cpu_num:
                    raise argparse.ArgumentError(self, ERROR_MSG)
            if num < 0:
                raise argparse.ArgumentError(self, ERROR_MSG)
            elif num == 0:
                num = None  # let the multiprocessing module decide
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
        default=DEFAULT_NUM_PROCESSORS,
        metavar="N",
        action=_NumProcessorsAction,
        help="Number of processors to use with --extract-conda-pkgs. "
        "Value must be int between 0 (auto) and the number of processors. "
        f"Defaults to {DEFAULT_NUM_PROCESSORS}.",
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
    from concurrent.futures import ProcessPoolExecutor, as_completed

    from conda.auxlib.type_coercion import boolify
    from conda.base.constants import CONDA_PACKAGE_EXTENSIONS
    from conda_package_handling import api
    from tqdm.auto import tqdm

    executor = ProcessPoolExecutor(max_workers=max_workers)

    os.chdir(os.path.join(prefix, "pkgs"))
    flist = []
    for ext in CONDA_PACKAGE_EXTENSIONS:
        for pkg in os.listdir(os.getcwd()):
            if pkg.endswith(ext):
                fn = os.path.join(os.getcwd(), pkg)
                flist.append(fn)
    if boolify(os.environ.get("CONDA_QUIET")):
        disabled = True
    else:
        disabled = None  # only for non-tty
    with ProcessPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(api.extract, fn): fn for fn in flist}
        with tqdm(total=len(flist), leave=False, disable=disabled) as pbar:
            for future in as_completed(futures):
                fn = futures[future]
                try:
                    future.result()
                except Exception as exc:
                    raise RuntimeError(f"Failed to extract {fn}: {exc}") from exc
                else:
                    pbar.set_description(f"Extracting: {os.path.basename(fn)}")
                    pbar.update()


def _constructor_extract_tarball():
    from conda_package_streaming.package_streaming import TarfileNoSameOwner

    t = TarfileNoSameOwner.open(mode="r|*", fileobj=sys.stdin.buffer)
    t.extractall()
    t.close()


def _constructor_menuinst(prefix, pkg_names=None, root_prefix=None, remove=False):
    from menuinst import install

    for json_path in Path(prefix, "Menu").glob("*.json"):
        if pkg_names and json_path.stem not in pkg_names:
            continue
        install(str(json_path), remove=remove, prefix=prefix, root_prefix=root_prefix)


def _constructor_subcommand():
    r"""
    This is the entry point for the `conda constructor` subcommand. This subcommand
    only exists in conda-standalone for now. constructor uses it to:

    - extract conda packages
    - extract the tarball payload contained in the shell installers
    - invoke menuinst to create and remove menu items on Windows
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


def _is_subdir(directory: Path, root: Path) -> bool:
    return any(root == parent for parent in directory.parents)


def _get_init_reverse_plan(
    root_prefix,
    prefixes: List[Path],
    for_user: bool,
    for_system: bool,
    anaconda_prompt: bool,
) -> List[dict]:
    import re

    from conda.activate import native_path_to_unix
    from conda.base.constants import COMPATIBLE_SHELLS
    from conda.common.compat import on_win
    from conda.core.initialize import (
        CONDA_INITIALIZE_PS_RE_BLOCK,
        CONDA_INITIALIZE_RE_BLOCK,
        _read_windows_registry,
        make_initialize_plan,
    )

    BIN_DIRECTORY = "Scripts" if on_win else "bin"
    reverse_plan = []
    for shell in COMPATIBLE_SHELLS:
        # Make plan for each shell individually because
        # not every plan includes the shell name
        plan = make_initialize_plan(
            root_prefix,
            [shell],
            for_user,
            for_system,
            anaconda_prompt,
            reverse=True,
        )
        for initializer in plan:
            target_path = initializer["kwargs"]["target_path"]
            if shell == "cmd.exe":
                # target_path for cmd.exe is a registry path
                reg_entry, _ = _read_windows_registry(target_path)
                if reg_entry is None:
                    continue
                autorun_parts = reg_entry.split("&")
                for prefix in prefixes:
                    hook = str(prefix / "condabin" / "conda_hook.bat")
                    if hook in autorun_parts:
                        reverse_plan.append(initializer)
                        break
            else:
                target_path = Path(target_path)
                # Only reverse for paths that are outside the root prefix
                # since paths inside the root prefix will be deleted anyway
                if not target_path.exists() or _is_subdir(target_path, root_prefix):
                    continue
                rc_content = target_path.read_text()
                if shell == "powershell":
                    pattern = CONDA_INITIALIZE_PS_RE_BLOCK
                else:
                    pattern = CONDA_INITIALIZE_RE_BLOCK
                flags = re.MULTILINE
                matches = re.findall(pattern, rc_content, flags=flags)
                if not matches:
                    continue
                for prefix in prefixes:
                    # Ignore .exe suffix to make the logic simpler
                    sentinel_str = str(prefix / BIN_DIRECTORY / "conda")
                    if shell != "powershell":
                        sentinel_str = native_path_to_unix(sentinel_str)
                        # Remove /cygdrive to make the path shell-independent
                        if sentinel_str.startswith("/cygdrive"):
                            sentinel_str = sentinel_str[9:]
                    if any(sentinel_str in match for match in matches):
                        reverse_plan.append(initializer)
                        break
    return reverse_plan


def _uninstall_subcommand():
    import argparse

    p = argparse.ArgumentParser(
        description="Uninstalls a conda directory and all environments inside."
    )
    p.add_argument(
        "prefix",
        help="Path to the conda directory to uninstall.",
    )
    p.add_argument(
        "--remove-condarcs",
        action="store_true",
        required=False,
        help=(
            "Remove all .condarc files."
            " If run with admin permissions, this will remove system .condarc files as well."
            " Not recommended when multiple conda installations are on the system"
            " or when running on an environments directory."
        ),
    )
    p.add_argument(
        "--remove-caches",
        action="store_true",
        required=False,
        help=(
            "Remove all cache directories created by conda."
            " This includes the .conda directory inside HOME/USERPROFILE."
            " Not recommended when multiple conda installations are on the system"
            " or when running on an environments directory."
        ),
    )
    p.add_argument(
        "--clean",
        action="store_true",
        required=False,
        help=(
            "Run conda --clean --all to remove package caches outside the installation directory."
            " This is only useful when pkgs_dirs is set in a .condarc file."
            " Not recommended with multiple conda installations when softlinks are enabled."
        ),
    )

    args, args_unknown = p.parse_known_args()

    root_prefix = Path(args.prefix).expanduser().resolve()
    if (
        not (root_prefix / "conda-meta" / "history").exists()
        and not (root_prefix / ".conda_envs_dir_test").exists()
    ):
        raise OSError(
            f"{root_prefix} is not a valid conda environment or environments directory."
        )

    import pdb
    from shutil import rmtree

    from conda.base.context import context
    from conda.cli.main import main as conda_main
    from conda.core.initialize import print_plan_results, run_plan, run_plan_elevated

    def _remove_directory(directory: Path):
        if not directory.exists():
            return
        if directory.is_symlink():
            link = directory
            directory = directory.resolve()
            os.remove(link)
        rmtree(directory)

    print(f"Uninstalling conda installation in {root_prefix}...")
    prefixes = [
        file.parent.parent.resolve()
        for file in root_prefix.glob("**/conda-meta/history")
    ]
    # Sort by path depth. This will place the root prefix first
    # Since it is more likely that profiles contain the root prefix,
    # this makes loops more efficient.
    prefixes.sort(key=lambda x: len(x.parts))

    # Run conda --init reverse for the shells
    # that contain a prefix that is being uninstalled
    anaconda_prompt = False
    print("Running conda init --reverse...")
    for for_user in (True, False):
        # Run user and system reversal separately because user
        # and system files may contain separate paths.
        for_system = not for_user
        anaconda_prompt = False
        plan = _get_init_reverse_plan(
            root_prefix, prefixes, for_user, for_system, anaconda_prompt
        )
        # Do not call conda.core.initialize() because it will always run make_install_plan.
        # That function will search for activation scripts in sys.prefix, which do no exist
        # in the extraction directory of conda-standalone.
        run_plan(plan)
        run_plan_elevated(plan)
        print_plan_results(plan)

    # Uninstalling environments must be performed with the deepest environment first.
    # Otherwise, parent environments will delete the environment directory and
    # uninstallation logic (removing shortcuts, pre-unlink scripts, etc.) cannot be run.
    print("Removing environments...")
    for prefix in reversed(prefixes):
        conda_main("remove", "-y", "-p", str(prefix), "--all", "-y")
    if root_prefix.exists():
        delete_root_prefix = True
        for file in root_prefix.iterdir():
            if file.name != ".conda_envs_dir_test":
                delete_root_prefix = False
                break
        if delete_root_prefix:
            _remove_directory(root_prefix)

    if args.clean:
        conda_main("clean", "--all", "-y")
        # Delete empty package cache directories
        for directory in context.pkgs_dirs:
            pkgs_dir = Path(directory)
            try:
                next(pkgs_dir.iterdir())
            except FileNotFoundError:
                pass
            except StopIteration:
                _remove_directory(pkgs_dir)

    if args.remove_condarcs:
        print("Removing .condarc files...")
        for config_file in context.config_files:
            try:
                os.remove(str(config_file))
            except PermissionError:
                pass

    if args.remove_caches:
        from conda.base.constants import APP_NAME
        from conda.gateways.anaconda_client import _get_binstar_token_directory
        from conda.notices.cache import get_notices_cache_dir
        from platformdirs import user_cache_dir, user_data_dir

        print("Removing config and cache directories...")
        cache_data_directories = (
            "~/.conda",
            _get_binstar_token_directory(),
            user_data_dir(APP_NAME),
            user_cache_dir(APP_NAME),
        )
        for cache_data_directory in cache_data_directories:
            directory = Path(cache_data_directory).expanduser()
            try:
                _remove_directory(directory)
            except PermissionError:
                pass

    return 0


def _conda_main():
    from conda.cli import main

    _fix_sys_path()
    return main()


def main():
    # https://docs.python.org/3/library/multiprocessing.html#multiprocessing.freeze_support
    freeze_support()
    if len(sys.argv) > 1:
        if sys.argv[1] == "constructor":
            return _constructor_subcommand()
        elif sys.argv[1] == "python":
            return _python_subcommand()
        elif sys.argv[1] == "uninstall":
            del sys.argv[1]
            return _uninstall_subcommand()

    return _conda_main()


if __name__ == "__main__":
    sys.exit(main())
