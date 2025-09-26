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


@pytest.mark.parametrize("user_or_system", ("user", "system"))
@pytest.mark.skipif(not ON_CI, reason="CI only, changes PATH variable")
def test_autorun(tmp_path: Path, user_or_system: str):
    def _get_autorun(user_or_system: str) -> list[str]:
        hive = "HKCU" if user_or_system == "user" else "HKLM"
        autorun_path = rf"{hive}:\Software\Microsoft\Command Processor"
        powershell_cmd = f"(Get-ItemProperty -Path '{autorun_path}' -Name AutoRun).AutoRun"
        try:
            result = subprocess.run(
                ["powershell", "-Command", powershell_cmd],
                capture_output=True,
                check=True,
                text=True,
            )
            return [cmd.strip() for cmd in result.stdout.split("&")]
        except subprocess.CalledProcessError as e:
            print(e)
            # Get-ItemProperty fails if the registry entry does not exist
            return []

    # Set up file structure
    prefix = tmp_path / "env"
    conda_hook = prefix / "condabin" / "conda_hook.bat"
    conda_hook.parent.mkdir(parents=True)
    conda_hook.touch()
    activate_str = f'if exist "{conda_hook}" "{conda_hook}"'

    prefix_override = tmp_path / "env_override"
    conda_hook_override = prefix_override / "condabin" / "conda_hook.bat"
    conda_hook_override.parent.mkdir(parents=True)
    conda_hook_override.touch()
    activate_str_override = f'if exist "{conda_hook_override}" "{conda_hook_override}"'

    run_conda(
        "constructor",
        "windows",
        "autorun",
        f"--add={user_or_system}",
        "--prefix",
        prefix,
        check=True,
    )
    autorun = _get_autorun(user_or_system)
    assert activate_str in autorun
    assert activate_str_override not in autorun

    # Test that overriding the AutoRun entry
    run_conda(
        "constructor",
        "windows",
        "autorun",
        f"--add={user_or_system}",
        "--prefix",
        prefix_override,
        check=True,
    )
    autorun = _get_autorun(user_or_system)
    assert activate_str not in autorun
    assert activate_str_override in autorun

    # Ensure that removing from AutoRun is selective
    run_conda(
        "constructor",
        "windows",
        "autorun",
        f"--remove={user_or_system}",
        "--prefix",
        prefix,
        check=True,
    )
    autorun = _get_autorun(user_or_system)
    assert activate_str not in autorun
    assert activate_str_override in autorun

    run_conda(
        "constructor",
        "windows",
        "autorun",
        f"--remove={user_or_system}",
        "--prefix",
        prefix_override,
        check=True,
    )
    autorun = _get_autorun(user_or_system)
    assert activate_str not in autorun
    assert activate_str_override not in autorun


def test_autorun_error(tmp_path: Path):
    with pytest.raises(subprocess.SubprocessError):
        run_conda(
            "constructor",
            "windows",
            "autorun",
            "--add=user",
            "--prefix",
            tmp_path,
            check=True,
        )
