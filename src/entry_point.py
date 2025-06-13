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

if os.name == "nt" and "SSLKEYLOGFILE" in os.environ:
    # This causes a crash with requests 2.32+ on Windows
    # Root cause is 'urllib3.util.ssl_.create_urllib3_context()'
    # See https://github.com/conda/conda-standalone/issues/86
    del os.environ["SSLKEYLOGFILE"]

if "CONDARC" not in os.environ:
    os.environ["CONDARC"] = os.path.join(sys.prefix, ".condarc")


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
    if len(sys.argv) > 1 and sys.argv[1].startswith("shell.") and sys.path and sys.path[0] == "":
        # The standard first entry in sys.path is an empty string,
        # and os.path.abspath('') expands to os.getcwd().
        del sys.path[0]


def _constructor_parse_cli():
    import argparse

    # This might be None!
    CPU_COUNT = os.cpu_count()
    # See validation results for magic number of 3
    # https://dholth.github.io/conda-benchmarks/#extract.TimeExtract.time_extract?conda-package-handling=2.0.0a2&p-format='.conda'&p-format='.tar.bz2'&p-lang='py'
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
        if all(getattr(args, arg.dest, None) is None for arg in group_args):
            required_args = [arg.option_strings[0] for arg in group_args]
            raise argparse.ArgumentError(
                f"one of the following arguments are required: {'/'.join(required_args)}"
            )

    if args.prefix is None:
        raise argparse.ArgumentError("the following arguments are required: --prefix")

    args.prefix = os.path.abspath(os.path.expanduser(os.path.expandvars(args.prefix)))
    args.root_prefix = os.path.abspath(os.environ.get("CONDA_ROOT_PREFIX", args.prefix))

    if "--num-processors" in sys.argv and not args.extract_conda_pkgs:
        raise argparse.ArgumentError("--num-processors can only be used with --extract-conda-pkgs")

    return args, args_unknown


def _constructor_extract_conda_pkgs(prefix, max_workers=None):
    from concurrent.futures import ProcessPoolExecutor, as_completed

    from conda.auxlib.type_coercion import boolify
    from conda.base.constants import CONDA_PACKAGE_EXTENSIONS
    from conda_package_handling import api
    from tqdm.auto import tqdm

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


def _is_subdir(directory: Path, root: Path) -> bool:
    """
    Helper function to detect whether a directory is a subdirectory.

    Rely on Path objects rather than string comparison to be portable.
    """
    return directory == root or root in directory.parents


def _get_init_reverse_plan(
    uninstall_prefix,
    prefixes: list[Path],
    for_user: bool,
    for_system: bool,
    anaconda_prompt: bool,
) -> list[dict]:
    """
    Prepare conda init --reverse runs for the uninstallation.

    Only grab the shells that were initialized by the prefix that
    is to be uninstalled since the shells within the prefix are
    removed later.
    """
    import re

    from conda.base.constants import COMPATIBLE_SHELLS
    from conda.common.compat import on_win
    from conda.common.path import win_path_to_unix
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
            str(uninstall_prefix),
            [shell],
            for_user,
            for_system,
            anaconda_prompt,
            reverse=True,
        )
        for initializer in plan:
            target_path = initializer["kwargs"]["target_path"]
            if target_path.startswith("HKEY"):
                # target_path for cmd.exe is a registry path
                reg_entry, _ = _read_windows_registry(target_path)
                if not isinstance(reg_entry, str):
                    continue
                autorun_parts = reg_entry.split("&")
                for prefix in prefixes:
                    hook = str(prefix / "condabin" / "conda_hook.bat")
                    if any(hook in part for part in autorun_parts):
                        reverse_plan.append(initializer)
                        break
            else:
                target_path = Path(target_path)
                # Only reverse for paths that are outside the uninstall prefix
                # since paths inside the uninstall prefix will be deleted anyway
                if not target_path.exists() or _is_subdir(target_path, uninstall_prefix):
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
                    if shell in ("csh", "tcsh") and sys.platform != "win32":
                        sentinel_str = str(prefix / "etc" / "profile.d" / "conda.csh")
                    else:
                        sentinel_str = str(prefix / BIN_DIRECTORY / "conda")
                    if sys.platform == "win32" and shell != "powershell":
                        # Remove /cygdrive to make the path shell-independent
                        sentinel_str = win_path_to_unix(sentinel_str).removeprefix("/cygdrive")
                    if any(sentinel_str in match for match in matches):
                        reverse_plan.append(initializer)
                        break
    return reverse_plan


def _constructor_uninstall_subcommand(
    uninstall_dir: str,
    remove_caches: bool = False,
    remove_config_files: str | None = None,
    remove_user_data: bool = False,
):
    """
    Remove a conda prefix or a directory containing conda environments.

    This command also provides options to remove various cache and configuration
    files to fully remove a conda installation.
    """
    from conda.base.constants import PREFIX_MAGIC_FILE

    # See: https://github.com/conda/conda/blob/475e6acbdc98122fcbef4733eb8cb8689324c1c8/conda/gateways/disk/create.py#L482-L488
    ENVS_DIR_MAGIC_FILE = ".conda_envs_dir_test"

    uninstall_prefix = Path(uninstall_dir)
    if (
        not (uninstall_prefix / PREFIX_MAGIC_FILE).exists()
        and not (uninstall_prefix / ENVS_DIR_MAGIC_FILE).exists()
    ):
        raise OSError(
            f"{uninstall_prefix} is not a valid conda environment or environments directory."
        )

    from shutil import rmtree

    from conda.base.context import context, reset_context
    from conda.cli.main import main as conda_main
    from conda.core.initialize import print_plan_results, run_plan, run_plan_elevated

    def _remove_file_directory(file: Path):
        """
        Try to remove a file or directory.

        If the file is a link, just unlink, do not remove the target.
        """
        try:
            if not file.exists():
                return
            if file.is_dir():
                rmtree(file)
            elif file.is_symlink() or file.is_file():
                file.unlink()
        except PermissionError:
            pass

    def _remove_config_file_and_parents(file: Path):
        """
        Remove a configuration file and empty parent directories.

        Only remove the configuration files created by conda.
        For that reason, search only for specific subdirectories
        and search backwards to be conservative about what is deleted.
        """
        rootdir = None
        _remove_file_directory(file)
        # Directories that may have been created by conda that are okay
        # to be removed if they are empty.
        if file.parent.parts[-1] in (".conda", "conda", "xonsh", "fish"):
            rootdir = file.parent
        # rootdir may be $HOME/%USERPROFILE% if the username is conda, etc.
        if not rootdir or rootdir == Path.home():
            return
        # Covers directories like ~/.config/conda/
        if rootdir.parts[-1] in (".config", "conda"):
            rootdir = rootdir.parent
        if rootdir == Path.home():
            return
        parent = file.parent
        while parent != rootdir.parent and not next(parent.iterdir(), None):
            _remove_file_directory(parent)
            parent = parent.parent

    print(f"Uninstalling conda installation in {uninstall_prefix}...")
    prefixes = [
        file.parent.parent.resolve() for file in uninstall_prefix.glob(f"**/{PREFIX_MAGIC_FILE}")
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
            uninstall_prefix, prefixes, for_user, for_system, anaconda_prompt
        )
        # Do not call conda.core.initialize() because it will always run make_install_plan.
        # That function will search for activation scripts in sys.prefix which do no exist
        # in the extraction directory of conda-standalone.
        run_plan(plan)
        run_plan_elevated(plan)
        print_plan_results(plan)
        for initializer in plan:
            target_path = initializer["kwargs"]["target_path"]
            if target_path.startswith("HKEY"):
                continue
            target_path = Path(target_path)
            if target_path.exists() and not target_path.read_text().strip():
                _remove_config_file_and_parents(target_path)

    # menuinst must be run separately because conda remove --all does not remove all shortcuts.
    # This is because some placeholders depend on conda's context.root_prefix, which is set to
    # the extraction directory of conda-standalone. The base prefix must be determined separately
    # since the uninstallation may be pointed to an environments directory or an extra environment
    # outside of the uninstall prefix.
    menuinst_base_prefix = None
    if conda_root_prefix := os.environ.get("CONDA_ROOT_PREFIX"):
        conda_root_prefix = Path(conda_root_prefix).resolve()
        menuinst_base_prefix = Path(conda_root_prefix)
    # If not set by the user, assume that conda-standalone is in the base environment.
    if not menuinst_base_prefix:
        standalone_path = Path(sys.executable).parent
        if (standalone_path / PREFIX_MAGIC_FILE).exists():
            menuinst_base_prefix = standalone_path
    # Fallback: use the uninstallation directory as root_prefix
    if not menuinst_base_prefix:
        menuinst_base_prefix = uninstall_prefix
    menuinst_base_prefix = str(menuinst_base_prefix)

    print("Removing environments...")
    # Uninstalling environments must be performed with the deepest environment first.
    # Otherwise, parent environments will delete the environment directory and
    # uninstallation logic (removing shortcuts, pre-unlink scripts, etc.) cannot be run.
    for prefix in reversed(prefixes):
        prefix_str = str(prefix)
        _constructor_menuinst(prefix_str, root_prefix=menuinst_base_prefix, remove=True)
        # If conda_root_prefix is the same as prefix, conda remove will not be able
        # to remove that environment, so temporarily unset it.
        if conda_root_prefix and conda_root_prefix == prefix:
            del os.environ["CONDA_ROOT_PREFIX"]
            reset_context()
        conda_main("remove", "-y", "-p", prefix_str, "--all")
        if conda_root_prefix and conda_root_prefix == prefix:
            os.environ["CONDA_ROOT_PREFIX"] = str(conda_root_prefix)
            reset_context()

    if uninstall_prefix.exists():
        # If the uninstall prefix is an environments directory,
        # it should only contain the magic file.
        # On Windows, the directory might still exist if conda-standalone
        # tries to delete itself (it gets renamed to a .conda_trash file).
        # In that case, the directory cannot be deleted - this needs to be
        # done by the uninstaller.
        delete_uninstall_prefix = True
        for file in uninstall_prefix.iterdir():
            if not file.name == ENVS_DIR_MAGIC_FILE:
                delete_uninstall_prefix = False
                break
        if delete_uninstall_prefix:
            _remove_file_directory(uninstall_prefix)

    if remove_caches:
        print("Cleaning cache directories.")
        from conda.notices.cache import get_notices_cache_dir

        conda_main("clean", "--all", "-y")
        # Delete empty package cache directories
        for directory in context.pkgs_dirs:
            pkgs_dir = Path(directory)
            if not pkgs_dir.exists():
                continue
            expected_files = [pkgs_dir / "urls", pkgs_dir / "urls.txt"]
            if all(file in expected_files for file in pkgs_dir.iterdir()):
                _remove_file_directory(pkgs_dir)

        notices_dir = Path(get_notices_cache_dir()).expanduser()
        _remove_config_file_and_parents(notices_dir)

    if remove_config_files:
        print("Removing .condarc files...")
        for config_file in context.config_files:
            if remove_config_files == "user" and not _is_subdir(config_file.parent, Path.home()):
                continue
            elif remove_config_files == "system" and _is_subdir(config_file.parent, Path.home()):
                continue
            _remove_config_file_and_parents(config_file)

    if remove_user_data:
        print("Removing user data...")
        _remove_file_directory(Path("~/.conda").expanduser())


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
        _constructor_uninstall_subcommand(
            args.prefix,
            remove_caches=args.remove_caches,
            remove_config_files=args.remove_config_files,
            remove_user_data=args.remove_user_data,
        )
        # os.chdir will break conda --clean, so return early
        return
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
