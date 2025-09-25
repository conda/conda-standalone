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


@pytest.mark.parametrize("user_or_system", ("user", "system"))
@pytest.mark.skipif(not ON_CI, reason="CI only, changes PATH variable")
def test_windows_add_remove_path(tmp_path: Path, user_or_system: str):
    envvar_map = {
        "system": "Machine",
        "user": "User",
    }
    run_conda("constructor", "windows", "path", f"--add={user_or_system}", "--prefix", tmp_path)
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
    assert tmp_path in paths
    run_conda("constructor", "windows", "path", f"--remove={user_or_system}", "--prefix", tmp_path)
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
    assert tmp_path not in paths
