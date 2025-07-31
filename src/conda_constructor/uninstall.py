import os
import re
import sys
from pathlib import Path
from shutil import rmtree

from conda.base.constants import COMPATIBLE_SHELLS, PREFIX_MAGIC_FILE
from conda.base.context import context, reset_context
from conda.cli.main import main as conda_main
from conda.common.compat import on_win
from conda.common.path import win_path_to_unix
from conda.core.initialize import (
    CONDA_INITIALIZE_PS_RE_BLOCK,
    CONDA_INITIALIZE_RE_BLOCK,
    _read_windows_registry,
    make_initialize_plan,
    print_plan_results,
    run_plan,
    run_plan_elevated,
)
from conda.notices.cache import get_notices_cache_dir

from .menuinst import install_shortcut


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


def uninstall(
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
        install_shortcut(prefix_str, root_prefix=menuinst_base_prefix, remove=True)
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
