import os
import subprocess
import sys
from pathlib import Path

import pytest
from utils import run_conda

ON_CI = bool(os.environ.get("CI")) and os.environ.get("CI") != "0"
ON_WIN = sys.platform == "win32"

if not ON_WIN:
    pytest.skip(reason="Windows only", allow_module_level=True)


@pytest.mark.parametrize(
    "extra_flag",
    (None, "--condabin", "--classic"),
    ids=("prefix", "condabin", "classic"),
)
@pytest.mark.parametrize("append_or_prepend", ("append", "prepend"))
@pytest.mark.parametrize("user_or_system", ("user", "system"))
@pytest.mark.skipif(not ON_CI, reason="CI only, changes PATH variable")
def test_windows_add_remove_path(
    tmp_path: Path,
    append_or_prepend: str,
    user_or_system: str,
    extra_flag: str | None,
):
    envvar_map = {
        "system": "Machine",
        "user": "User",
    }
    if extra_flag == "--condabin":
        expected_paths = [tmp_path / "condabin"]
    elif extra_flag == "--classic":
        expected_paths = [
            tmp_path,
            tmp_path / "Library" / "mingw-w64" / "bin",
            tmp_path / "Library" / "usr" / "bin",
            tmp_path / "Library" / "bin",
            tmp_path / "Scripts",
        ]
        if append_or_prepend == "prepend":
            expected_paths.reverse()
    else:
        expected_paths = [tmp_path]
    create_command = [
        "constructor",
        "windows",
        "path",
        f"--{append_or_prepend}={user_or_system}",
        "--prefix",
        tmp_path,
    ]
    if extra_flag:
        create_command.append(extra_flag)
    run_conda(*create_command)
    # Quick way to query the registry for changes.
    # The updated PATH environment variable is only available
    # to a new process, which we cannot spawn within a pytest run.
    pathvar_run = subprocess.run(
        [
            "powershell",
            "-Command",
            f"[Environment]::GetEnvironmentVariable('PATH', '{envvar_map[user_or_system]}')",
        ],
        capture_output=True,
        check=True,
        text=True,
    )
    paths = [Path(p) for p in pathvar_run.stdout.strip().split(os.pathsep) if p]
    assert all(expected_path in paths for expected_path in expected_paths)
    if append_or_prepend == "append":
        assert paths[-len(expected_paths) :] == expected_paths
    else:
        assert paths[: len(expected_paths)] == list(reversed(expected_paths))
    remove_command = [
        "constructor",
        "windows",
        "path",
        f"--remove={user_or_system}",
        "--prefix",
        tmp_path,
    ]
    if extra_flag:
        remove_command.append(extra_flag)
    run_conda(*remove_command)
    # Quick way to query the registry for changes.
    # The updated PATH environment variable is only available
    # to a new process, which we cannot spawn within a pytest run.
    pathvar_run = subprocess.run(
        [
            "powershell",
            "-Command",
            f"[Environment]::GetEnvironmentVariable('PATH', '{envvar_map[user_or_system]}')",
        ],
        capture_output=True,
        check=True,
        text=True,
    )
    paths = [Path(p) for p in pathvar_run.stdout.strip().split(os.pathsep) if p]
    assert all(expected_path not in paths for expected_path in expected_paths)
