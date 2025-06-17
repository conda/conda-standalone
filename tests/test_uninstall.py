from __future__ import annotations

import os
import shutil
import subprocess
import sys
from contextlib import nullcontext
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from conda.base.constants import COMPATIBLE_SHELLS
from conda.common.path import win_path_to_unix
from conda.core.initialize import (
    Result,
    _read_windows_registry,
    make_initialize_plan,
    run_plan,
    run_plan_elevated,
)
from ruamel.yaml import YAML
from utils import CONDA_EXE, _get_shortcut_dirs, run_conda

if TYPE_CHECKING:
    from conda.testing.fixtures import CondaCLIFixture, TmpEnvFixture
    from pytest import MonkeyPatch

ON_WIN = sys.platform == "win32"
ON_MAC = sys.platform == "darwin"
ON_LINUX = not (ON_WIN or ON_MAC)
ON_CI = bool(os.environ.get("CI")) and os.environ.get("CI") != "0"
CONDA_CHANNEL = os.environ.get("CONDA_STANDALONE_TEST_CHANNEL", "conda-forge")

pytest_plugins = ["conda.testing.fixtures"]


def can_use_sudo() -> bool:
    if not shutil.which("sudo"):
        return False
    try:
        subprocess.run(["sudo", "-v"], check=True)
    except subprocess.CalledProcessError:
        return False
    return True


@pytest.fixture(scope="function")
def mock_system_paths(
    monkeypatch: MonkeyPatch,
    tmp_path: Path,
) -> dict[str, Path]:
    paths = {}
    if ON_WIN:
        homedir = tmp_path / "Users" / "conda"
        monkeypatch.setenv("USERPROFILE", str(homedir))
        monkeypatch.setenv("HOMEDRIVE", homedir.anchor[:-1])
        monkeypatch.setenv("HOMEPATH", f"\\{homedir.relative_to(homedir.anchor)}")
        # Monkeypatching LOCALAPPDATA will not help because user_cache_dir
        # typically does not use environment variables
        cachehome = homedir / "AppData" / "Local"
    elif ON_MAC:
        homedir = tmp_path / "Users" / "conda"
        cachehome = homedir / "Library" / "Caches"
        monkeypatch.setenv("HOME", str(homedir))
    else:
        homedir = tmp_path / "home" / "conda"
        monkeypatch.setenv("HOME", str(homedir))
        cachehome = homedir / "cache"

    paths = {
        "home": homedir,
        "cachehome": cachehome,
        "confighome": homedir / "config",
        "datahome": homedir / "data",
    }
    for mockdir in paths.values():
        mockdir.mkdir(parents=True, exist_ok=True)

    monkeypatch.setenv("XDG_CONFIG_HOME", str(paths["confighome"]))
    monkeypatch.setenv("XDG_CACHE_HOME", str(paths["cachehome"]))
    monkeypatch.setenv("XDG_DATA_HOME", str(paths["datahome"]))
    return paths


def run_uninstaller(
    prefix: Path,
    remove_caches: bool = False,
    remove_config_files: str | None = None,
    remove_user_data: bool = False,
    needs_sudo: bool = False,
):
    args = ["--prefix", str(prefix)]
    if remove_caches:
        args.append("--remove-caches")
    if remove_config_files:
        args.extend(["--remove-config-files", remove_config_files])
    if remove_user_data:
        args.append("--remove-user-data")
    run_conda("constructor", "uninstall", *args, needs_sudo=needs_sudo, check=True)


def test_uninstallation(
    mock_system_paths: dict[str, Path],
    tmp_env: TmpEnvFixture,
):
    environments_txt = mock_system_paths["home"] / ".conda" / "environments.txt"
    with tmp_env() as base_env, tmp_env() as second_env:
        assert environments_txt.exists()
        environments = environments_txt.read_text().splitlines()
        assert str(base_env) in environments and str(second_env) in environments
        run_uninstaller(base_env)
        assert not base_env.exists()
        environments = environments_txt.read_text().splitlines()
        assert str(base_env) not in environments and str(second_env) in environments


@pytest.mark.parametrize("remove", (True, False), ids=("remove directory", "keep directory"))
def test_uninstallation_envs_dirs(
    mock_system_paths: dict[str, Path],
    conda_cli: CondaCLIFixture,
    remove: bool,
):
    yaml = YAML()
    envs_dir = mock_system_paths["home"] / "envs"
    testenv_name = "testenv"
    testenv_dir = envs_dir / testenv_name
    condarc = {
        "envs_dirs": [str(envs_dir)],
    }
    with open(mock_system_paths["home"] / ".condarc", "w") as crc:
        yaml.dump(condarc, crc)
    conda_cli("create", "-n", testenv_name, "-y")
    assert envs_dir.exists()
    assert envs_dir / ".conda_envs_dir_test"
    assert testenv_dir.exists()
    # conda-standalone should not remove the environments directory
    # if it finds other files than the magic file.
    if not remove:
        (envs_dir / "some_other_file").touch()
    run_uninstaller(envs_dir)
    assert envs_dir.exists() != remove


@pytest.mark.skipif(
    ON_WIN and not ON_CI,
    reason="CI only - interacts with user files and the registry",
)
@pytest.mark.parametrize(
    "for_user,reverse",
    (
        pytest.param(True, True, id="user, reverse"),
        pytest.param(False, True, id="system, reverse"),
        pytest.param(True, False, id="user, no reverse"),
        pytest.param(False, False, id="system, no reverse"),
    ),
)
def test_uninstallation_init_reverse(
    mock_system_paths: dict[str, Path],
    monkeypatch: MonkeyPatch,
    tmp_env: TmpEnvFixture,
    for_user: bool,
    reverse: bool,
):
    def _find_in_config(directory: str, target_path: str) -> bool:
        if target_path.startswith("HKEY"):
            reg_entry, _ = _read_windows_registry(target_path)
            if not isinstance(reg_entry, str):
                return False
            return directory in reg_entry
        else:
            config_file = Path(target_path)
            if not config_file.exists():
                return False
            content = config_file.read_text()
            if sys.platform == "win32" and not target_path.endswith(".ps1"):
                directory = win_path_to_unix(directory).removeprefix("/cygdrive")
            return directory in content

    # Patch out make_install_plan since it won't be used for uninstallation
    # and breaks for conda-standalone
    monkeypatch.setattr("conda.core.initialize.make_install_plan", lambda _: [])
    if not for_user and not ON_CI:
        pytest.skip("CI only - interacts with system files")
    with tmp_env() as base_env:
        anaconda_prompt = False
        if reverse:
            init_env = str(base_env)
        else:
            init_env = str(mock_system_paths["home"] / "testenv")
        initialize_plan = make_initialize_plan(
            init_env,
            COMPATIBLE_SHELLS,
            for_user,
            not for_user,
            anaconda_prompt,
            reverse=False,
        )
        # Filter out the LongPathsEnabled target since conda init --reverse does not remove it
        initialize_plan = [
            plan
            for plan in initialize_plan
            if not plan["kwargs"]["target_path"].endswith("LongPathsEnabled")
        ]
        run_plan(initialize_plan)
        if any(step["result"] == Result.NEEDS_SUDO for step in initialize_plan):
            if not can_use_sudo():
                # Revert previous initialization before skipping
                initialize_plan = make_initialize_plan(
                    init_env,
                    COMPATIBLE_SHELLS,
                    for_user,
                    not for_user,
                    anaconda_prompt,
                    reverse=True,
                )
                run_plan(initialize_plan)
                pytest.skip("Requires sudo.")
        run_plan_elevated(initialize_plan)
        for plan in initialize_plan:
            assert _find_in_config(init_env, plan["kwargs"]["target_path"])
        run_uninstaller(base_env)
        for plan in initialize_plan:
            target_path = plan["kwargs"]["target_path"]
            assert _find_in_config(init_env, target_path) != reverse
            if not reverse:
                continue
            parent = Path(target_path).parent
            if parent == mock_system_paths["home"]:
                assert parent.exists()
            elif parent.name in ("fish", ".conda", "conda", "xonsh"):
                assert not parent.exists()


def test_uninstallation_keep_config_dir(
    mock_system_paths: dict[str, Path],
    monkeypatch: MonkeyPatch,
    tmp_env: TmpEnvFixture,
):
    config_dir = mock_system_paths["home"] / ".config"
    fish_config_dir = config_dir / "fish"
    other_config_dir = config_dir / "other"
    other_config_dir.mkdir(parents=True)
    # Patch out make_install_plan since it won't be used for uninstallation
    # and breaks for conda-standalone
    monkeypatch.setattr("conda.core.initialize.make_install_plan", lambda _: [])
    for_user = True
    for_system = False
    anaconda_prompt = False
    shells = ["bash", "fish"]
    with tmp_env() as base_env:
        initialize_plan = make_initialize_plan(
            base_env,
            shells,
            for_user,
            for_system,
            anaconda_prompt,
            reverse=False,
        )
        run_plan(initialize_plan)
        assert fish_config_dir.exists()
        run_uninstaller(base_env)
        assert mock_system_paths["home"].exists()
        assert not fish_config_dir.exists()
        assert other_config_dir.exists()


def test_uninstallation_menuinst(
    mock_system_paths: dict[str, Path],
    monkeypatch: MonkeyPatch,
    menuinst_pkg_specs: list[tuple[str, dict[str, str]]],
):
    def _shortcuts_found(base_env: Path, shortcut_env: Path) -> list:
        variables = {
            "base": base_env.name,
            "name": shortcut_env.name,
        }
        shortcut_dirs = _get_shortcut_dirs()
        if ON_WIN:
            # For Windows, menuinst installed via conda does not pick up on the monkeypatched
            # environment variables, so add the hard-coded patched directory.
            # They do get patched for conda-standalone though.
            programs = "AppData\\Roaming\\Microsoft\\Windows\\Start Menu\\Programs"
            shortcut_dirs.append(mock_system_paths["home"] / programs)

        return [
            package[0]
            for package in menuinst_pkg_specs
            if any(
                (folder / package[1][sys.platform].format(**variables)).exists()
                for folder in shortcut_dirs
            )
        ]

    if ON_WIN:
        # menuinst will error out if the directories it installs into do not exist.
        for subdir in (
            "Desktop",
            "Documents",
            "AppData\\Local",
            "AppData\\Roaming\\Microsoft\\Internet Explorer\\Quick Launch",
            "AppData\\Roaming\\Microsoft\\Windows\\Start Menu\\Programs",
        ):
            (mock_system_paths["home"] / subdir).mkdir(parents=True, exist_ok=True)
    base_env = mock_system_paths["home"] / "baseenv"
    monkeypatch.setenv("CONDA_ROOT_PREFIX", str(base_env))
    # Conda test fixtures cannot be used here because menuinst
    # will not use monkeypatched paths.
    run_conda("create", "-y", "-p", str(base_env))
    (base_env / ".nonadmin").touch()
    shortcuts = [package[0] for package in menuinst_pkg_specs]
    shortcut_env = base_env / "envs" / "shortcutenv"
    run_conda("create", "-y", "-p", str(shortcut_env), *shortcuts)
    assert _shortcuts_found(base_env, shortcut_env) == shortcuts
    run_uninstaller(base_env)
    assert _shortcuts_found(base_env, shortcut_env) == []


@pytest.mark.parametrize(
    "shared_pkgs",
    (True, False),
    ids=("shared pkgs", "remove pkgs"),
)
@pytest.mark.skipif(not ON_CI, reason="CI only - may remove shared caches")
def test_uninstallation_remove_caches(
    mock_system_paths: dict[str, Path],
    tmp_env: TmpEnvFixture,
    shared_pkgs: bool,
):
    if "CONDA_PKGS_DIRS" in os.environ:
        pytest.skip("Test will fail with CONDA_PKGS_DIRS set.")
    # Set up notices
    if ON_WIN:
        try:
            import ctypes

            if not hasattr(ctypes, "windll"):
                pytest.skip("Test requires windll.ctypes for mocked locations to work.")
        except ImportError:
            pytest.skip("Test requires ctypes for mocked locations to work.")
        notices_dir = Path(mock_system_paths["cachehome"], "conda", "conda", "Cache", "notices")
    else:
        notices_dir = Path(mock_system_paths["cachehome"], "conda", "notices")
    notices_dir.mkdir(parents=True, exist_ok=True)
    (notices_dir / "notices.cache").touch()

    yaml = YAML()
    pkgs_dir = mock_system_paths["home"] / "pkgs"
    condarc = {
        "channels": [CONDA_CHANNEL],
        "pkgs_dirs": [str(pkgs_dir)],
    }
    with open(mock_system_paths["home"] / ".condarc", "w") as crc:
        yaml.dump(condarc, crc)

    other_env = tmp_env("python") if shared_pkgs else nullcontext()
    with (
        tmp_env("constructor") as base_env,
        other_env as _,
    ):
        assert pkgs_dir.exists()
        assert list(pkgs_dir.glob("constructor*")) != []
        assert list(pkgs_dir.glob("python*")) != []
        run_uninstaller(base_env, remove_caches=True)
        assert pkgs_dir.exists() == shared_pkgs
        if shared_pkgs:
            assert list(pkgs_dir.glob("constructor*")) == []
            assert list(pkgs_dir.glob("python*")) != []
        assert not notices_dir.exists()


def test_uninstallation_remove_user_data(
    mock_system_paths: dict[str, Path],
    tmp_env: TmpEnvFixture,
):
    with tmp_env() as base_env:
        dot_conda_dir = mock_system_paths["home"] / ".conda"
        assert dot_conda_dir.exists()
        run_uninstaller(base_env, remove_user_data=True)
        assert not dot_conda_dir.exists()


@pytest.mark.parametrize("remove", ("user", "system", "all"))
@pytest.mark.skipif(not ON_CI, reason="CI only - Writes to system files")
def test_uninstallation_remove_config_files(
    mock_system_paths: dict[str, Path],
    tmp_env: TmpEnvFixture,
    remove: str,
):
    yaml = YAML()
    remove_system = remove != "user"
    remove_user = remove != "system"
    condarc = {
        "channels": [CONDA_CHANNEL],
    }
    needs_sudo = False
    if ON_WIN:
        system_condarc = Path("C:/ProgramData/conda/.condarc")
    else:
        system_condarc = Path("/etc/conda/.condarc")
        try:
            system_condarc.parent.mkdir(parents=True, exist_ok=True)
        except PermissionError:
            if not can_use_sudo():
                pytest.skip("Test requires sudo.")
            needs_sudo = True
    user_condarc = mock_system_paths["confighome"] / "conda" / ".condarc"
    for condarc_file in (system_condarc, user_condarc):
        if needs_sudo and condarc_file == system_condarc:
            from textwrap import dedent

            # Running shutil does not work using python -m,
            # so create a temporary script and run as sudo.
            # Since datahome is the temporary location since
            # it is not used in this test.
            tmp_condarc_dir = mock_system_paths["datahome"] / ".tmp_condarc"
            tmp_condarc_dir.mkdir(parents=True, exist_ok=True)
            tmp_condarc_file = tmp_condarc_dir / ".condarc"
            with open(tmp_condarc_file, "w") as crc:
                yaml.dump(condarc, crc)
            script = dedent(
                f"""
                from pathlib import Path
                from shutil import copyfile

                condarc_file = Path("{condarc_file}")
                condarc_file.parent.mkdir(parents=True, exist_ok=True)
                copyfile("{tmp_condarc_file}", condarc_file)
                """
            )
            script_file = tmp_condarc_dir / "copy_condarc.py"
            script_file.write_text(script)
            run_conda("python", script_file, needs_sudo=True)
            shutil.rmtree(tmp_condarc_dir)
        else:
            condarc_file.parent.mkdir(parents=True, exist_ok=True)
            with open(condarc_file, "w") as crc:
                yaml.dump(condarc, crc)
    with tmp_env() as base_env:
        try:
            run_uninstaller(base_env, remove_config_files=remove, needs_sudo=needs_sudo)
            assert user_condarc.exists() != remove_user
            assert system_condarc.exists() != remove_system
        finally:
            if system_condarc.parent.exists():
                try:
                    shutil.rmtree(system_condarc.parent)
                except PermissionError:
                    run_conda(
                        "python",
                        "-c",
                        f"from shutil import rmtree; rmtree('{system_condarc.parent}')",
                        needs_sudo=True,
                    )


def test_delete_self(tmp_path: Path):
    instdir = tmp_path / "install"
    shutil.copytree(Path(CONDA_EXE).parent, instdir)
    # Make the path of the copied conda-standalone file(s) look like a conda environment.
    (instdir / "conda-meta").mkdir(parents=True)
    (instdir / "conda-meta" / "history").touch()
    subprocess.run(
        [
            str(instdir / "conda.exe"),
            "constructor",
            "uninstall",
            "--prefix",
            str(instdir),
        ],
        check=True,
    )
    if not ON_WIN:
        assert not instdir.exists()
    else:
        # On Windows, conda-standalone won't be able to delete itself
        # and leaves .conda_trash files behind. Those must be manually
        # removed by an uninstaller.
        unexpected_files = [
            file
            for file in instdir.glob("*")
            if not file.is_dir() and file.suffix != ".conda_trash"
        ]
        assert unexpected_files == []


def test_uninstallation_invalid_directory(tmp_path: Path):
    with pytest.raises(subprocess.SubprocessError):
        run_uninstaller(tmp_path)
