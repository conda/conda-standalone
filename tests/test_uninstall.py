import os
import sys
from pathlib import Path
from shutil import rmtree
from subprocess import SubprocessError
from typing import Generator

import pytest
from conda.base.constants import COMPATIBLE_SHELLS
from conda.common.path import win_path_to_unix
from conda.core.initialize import _read_windows_registry, make_initialize_plan, run_plan
from conftest import _get_shortcut_dirs, menuinst_pkg_specs, run_conda
from ruamel.yaml import YAML

ON_WIN = sys.platform == "win32"
ON_MAC = sys.platform == "darwin"
ON_LINUX = not (ON_WIN or ON_MAC)
ON_CI = bool(os.environ.get("CI"))
CONDA_CHANNEL = os.environ.get("CONDA_STANDALONE_TEST_CHANNEL", "conda-forge")


@pytest.fixture(scope="function")
def mock_system_paths(
    monkeypatch,
    tmp_path: Path,
) -> Generator[dict[str, Path], None, None]:
    paths = {}
    if ON_WIN:
        homedir = tmp_path / "Users" / "user"
        monkeypatch.setenv("USERPROFILE", str(homedir))
        # Monkeypatching LOCALAPPDATA will not help because user_cache_dir
        # typically does not use environment variables
        cachehome = homedir / "AppData" / "Local"
    elif ON_MAC:
        homedir = tmp_path / "Users" / "user"
        cachehome = homedir / "Library" / "Caches"
        monkeypatch.setenv("HOME", str(homedir))
    else:
        homedir = tmp_path / "home" / "users"
        monkeypatch.setenv("HOME", str(homedir))
        cachehome = homedir / "cache"

    paths = {
        "home": homedir,
        "binstar": homedir / "ContinuumIO" / "binstar",
        "cachehome": cachehome,
        "confighome": homedir / "config",
        "datahome": homedir / "data",
    }
    for mockdir in paths.values():
        mockdir.mkdir(parents=True, exist_ok=True)
    paths["baseenv"] = paths["home"] / "baseenv"

    monkeypatch.setenv("XDG_CONFIG_HOME", str(paths["confighome"]))
    monkeypatch.setenv("XDG_CACHE_HOME", str(paths["cachehome"]))
    monkeypatch.setenv("XDG_DATA_HOME", str(paths["datahome"]))
    monkeypatch.setenv("BINSTAR_CONFIG_DIR", str(paths["binstar"]))

    yield paths

    if ON_CI:
        if ON_WIN:
            system_conda_dir = Path("C:/ProgramData/conda/")
        else:
            system_conda_dir = Path("/etc/conda/")
        if system_conda_dir.exists():
            rmtree(system_conda_dir)


def create_env(
    prefix: Path | None = None, name: str = "env", packages: list[str] | None = None
):
    packages = packages or []
    if prefix:
        run_conda("create", "-y", "-p", str(prefix), "-c", CONDA_CHANNEL, *packages)
    else:
        run_conda("create", "-y", "-n", name, "-c", CONDA_CHANNEL, *packages)


def test_uninstallation(
    mock_system_paths: dict[str, Path],
):
    second_env = mock_system_paths["home"] / "testenv"
    environments_txt = mock_system_paths["home"] / ".conda" / "environments.txt"
    create_env(prefix=mock_system_paths["baseenv"])
    create_env(prefix=second_env)
    assert environments_txt.exists()
    environments = environments_txt.read_text().splitlines()
    assert (
        str(mock_system_paths["baseenv"]) in environments
        and str(second_env) in environments
    )
    run_conda("uninstall", mock_system_paths["baseenv"])
    assert not mock_system_paths["baseenv"].exists()
    assert mock_system_paths
    environments = environments_txt.read_text().splitlines()
    assert (
        str(mock_system_paths["baseenv"]) not in environments
        and str(second_env) in environments
    )


@pytest.mark.parametrize(
    "remove", (True, False), ids=("remove directory", "keep directory")
)
def test_uninstallation_envs_dirs(
    mock_system_paths: dict[str, Path],
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
    create_env(name=testenv_name)
    assert envs_dir.exists()
    assert envs_dir / ".conda_envs_dir_test"
    assert testenv_dir.exists()
    # conda-standalone should not remove the environments directory
    # if it finds other files than the magic file.
    if not remove:
        (envs_dir / "some_other_file").touch()
    run_conda("uninstall", envs_dir)
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
    monkeypatch,
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
            if sys.platform == "win32" and target_path.endswith(".ps1"):
                directory = win_path_to_unix(content)
                if directory.startswith("/cygdrive"):
                    directory = directory[9:]
            return directory in content

    # Patch out make_install_plan since it won't be used for uninstallation
    # and breaks for conda-standalone
    monkeypatch.setattr("conda.core.initialize.make_install_plan", lambda _: [])
    if not for_user and not ON_CI:
        pytest.skip("CI only - interacts with system files")
    create_env(prefix=mock_system_paths["baseenv"])
    anaconda_prompt = False
    if reverse:
        init_env = str(mock_system_paths["baseenv"])
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
    run_plan(initialize_plan)
    for plan in initialize_plan:
        assert _find_in_config(init_env, plan["kwargs"]["target_path"])
    run_conda("uninstall", str(mock_system_paths["baseenv"]))
    for plan in initialize_plan:
        target_path = plan["kwargs"]["target_path"]
        assert _find_in_config(init_env, target_path) != reverse
        if not reverse:
            continue
        parent = Path(target_path).parent
        if parent.name in (".config", ".conda", "conda", "xonsh"):
            assert not parent.exists()


def test_uninstallation_menuinst(
    mock_system_paths: dict[str, Path],
    monkeypatch,
):
    def _shortcuts_found(shortcut_env: Path) -> list:
        variables = {
            "base": mock_system_paths["baseenv"].name,
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
                (folder / package[1][sys.platform].format(**variables)).is_file()
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
    monkeypatch.setenv("CONDA_ROOT_PREFIX", str(mock_system_paths["baseenv"]))
    create_env(prefix=mock_system_paths["baseenv"])
    (mock_system_paths["baseenv"] / ".nonadmin").touch()
    shortcut_env = mock_system_paths["baseenv"] / "envs" / "shortcutenv"
    shortcuts = [package[0] for package in menuinst_pkg_specs]
    create_env(prefix=shortcut_env, packages=shortcuts)
    assert _shortcuts_found(shortcut_env) == shortcuts
    run_conda("uninstall", str(mock_system_paths["baseenv"]))
    assert _shortcuts_found(shortcut_env) == []


@pytest.mark.parametrize(
    "shared_pkgs",
    (True, False),
    ids=("shared pkgs", "remove pkgs"),
)
def test_uninstallation_conda_clean(
    mock_system_paths: dict[str, Path],
    shared_pkgs: bool,
):
    yaml = YAML()
    pkgs_dir = mock_system_paths["home"] / "pkgs"
    condarc = {
        "channels": [CONDA_CHANNEL],
        "pkgs_dirs": [str(pkgs_dir)],
    }
    with open(mock_system_paths["home"] / ".condarc", "w") as crc:
        yaml.dump(condarc, crc)

    create_env(prefix=mock_system_paths["baseenv"], packages=["constructor"])
    if shared_pkgs:
        create_env(prefix=(mock_system_paths["home"] / "otherenv"), packages=["python"])
    assert pkgs_dir.exists()
    assert list(pkgs_dir.glob("constructor*")) != []
    assert list(pkgs_dir.glob("python*")) != []
    run_conda("uninstall", str(mock_system_paths["baseenv"]), "--conda-clean")
    assert pkgs_dir.exists() == shared_pkgs
    if shared_pkgs:
        assert list(pkgs_dir.glob("constructor*")) == []
        assert list(pkgs_dir.glob("python*")) != []


def test_uninstallation_remove_caches(
    mock_system_paths: dict[str, Path],
):
    if ON_WIN:
        try:
            import ctypes

            if not hasattr(ctypes, "windll"):
                pytest.skip("Test requires windll.ctypes for mocked locations to work.")
        except ImportError:
            pytest.skip("Test requires ctypes for mocked locations to work.")
        notices_dir = Path(
            mock_system_paths["cachehome"], "conda", "conda", "Cache", "notices"
        )
    else:
        notices_dir = Path(mock_system_paths["cachehome"], "conda", "notices")
    notices_dir.mkdir(parents=True, exist_ok=True)
    (notices_dir / "notices.cache").touch()

    binstar_dir = mock_system_paths["binstar"] / "data"
    binstar_dir.mkdir(parents=True, exist_ok=True)
    (binstar_dir / "token").touch()

    create_env(prefix=mock_system_paths["baseenv"])
    dot_conda_dir = mock_system_paths["home"] / ".conda"
    assert dot_conda_dir.exists()
    run_conda("uninstall", str(mock_system_paths["baseenv"]), "--remove-caches")
    assert not dot_conda_dir.exists()
    assert not mock_system_paths["binstar"].exists()
    assert not notices_dir.exists()


@pytest.mark.parametrize("remove", ("user", "system", "all"))
@pytest.mark.skipif(not ON_CI, reason="CI only - Writes to system files")
def test_uninstallation_remove_condarcs(
    mock_system_paths: dict[str, Path],
    remove: str,
):
    yaml = YAML()
    remove_system = remove != "user"
    remove_user = remove != "system"
    condarc = {
        "channels": [CONDA_CHANNEL],
    }
    if ON_WIN:
        system_condarc = Path("C:/ProgramData/conda/.condarc")
    else:
        system_condarc = Path("/etc/conda/.condarc")
    user_condarc = mock_system_paths["confighome"] / "conda" / ".condarc"
    for condarc_file in (system_condarc, user_condarc):
        condarc_file.parent.mkdir()
        with open(condarc_file, "w") as crc:
            yaml.dump(condarc, crc)
    create_env(prefix=mock_system_paths["baseenv"])
    run_conda(
        "uninstall", str(mock_system_paths["baseenv"]), f"--remove-condarcs={remove}"
    )
    assert system_condarc.exists() != remove_system
    assert user_condarc.exists() != remove_user


def test_uninstallation_invalid_directory(tmp_path: Path):
    with pytest.raises(SubprocessError):
        run_conda("uninstall", str(tmp_path), check=True)
