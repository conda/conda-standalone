"""Test update-bootstrapper subcommand for the constructor plug-in.

A true integration test would require an updated conda-standalone to be
available in a channel. If a later version is built and tested, however,
there is nothing to update to.

Some individual pieces can be tested as unit tests using the built-in
Python interpreter in conda-standalone, which allows mocking some components.
Python commands/scripts are written as functions to allow for type checking
and linting.
"""

from __future__ import annotations

import inspect
import os
import sys
from textwrap import dedent
from typing import TYPE_CHECKING

import pytest
from utils import run_conda

if TYPE_CHECKING:
    from pathlib import Path

ON_WIN = sys.platform == "win32"
if os.environ.get("PYINSTALLER_BUILD_VARIANT") == "onedir":
    pytest.skip("Not implemented for onedir builds.", allow_module_level=True)


def _run_script(func, **kwargs):
    """Run a function as a script inside conda-standalone's Python."""
    # Remove the function definition line and dedent the body
    source = inspect.getsourcelines(func)[0][1:]
    body = dedent("\n".join(source))
    # Inject kwargs as variables at the top
    injections = "\n".join(f"{k} = {v!r}" for k, v in kwargs.items())
    script = f"{injections}\n{body}" if injections else body

    process = run_conda("python", "-c", script, capture_output=True, text=True)
    print(process.stdout)
    print(process.stderr, file=sys.stderr)
    return process


# ---------------------------------------------------------------------------
# Script functions to run inside conda-standalone
# ---------------------------------------------------------------------------


def _script_find_update():
    from conda.base.context import reset_context

    from conda_constructor.update_bootstrapper import _find_update

    os.environ["CONDA_RESTRICT_SEARCH_PATH"] = "1"
    reset_context()

    match = _find_update("1.0.0")
    assert match is not None
    assert match.name == "conda-standalone"
    print("PASS")


def _script_find_update_already_up_to_date():
    from conda.base.context import reset_context

    from conda_constructor.update_bootstrapper import _find_update

    os.environ["CONDA_RESTRICT_SEARCH_PATH"] = "1"
    reset_context()

    match = _find_update("999.999.999")
    assert match is None
    print("PASS")


def _script_apply_update(prefix_str: str, conda_exe: str):
    import subprocess
    import sys
    import time
    from pathlib import Path

    from conda_constructor.update_bootstrapper import RELOCATED_NAME_SUFFIX, _apply_update

    prefix = Path(prefix_str)
    old_exe = prefix / "old_conda.exe"
    new_exe = Path(conda_exe)

    old_exe.write_text("old content")

    original_popen = subprocess.Popen

    def patched_popen(args, _conda_exe=conda_exe, _original_popen=original_popen, **kwargs):
        # Replace the fake executable with the real conda-standalone
        args = [_conda_exe] + args[1:]
        return _original_popen(args, **kwargs)

    # Patch Popen to use real conda-standalone for cleanup subprocess
    subprocess.Popen = patched_popen
    try:
        _apply_update(new_exe, old_exe)
    finally:
        subprocess.Popen = original_popen

    # Verify update succeeded
    assert old_exe.read_bytes() == new_exe.read_bytes()

    relocated = old_exe.with_stem(f"{old_exe.stem}{RELOCATED_NAME_SUFFIX}")
    if sys.platform == "win32":
        for _ in range(600):
            if not relocated.exists():
                break
            time.sleep(0.1)
    assert not relocated.exists()
    print("PASS")


def _script_apply_update_rollback(prefix_str: str):
    import sys
    from pathlib import Path
    from unittest.mock import patch

    from conda_constructor.update_bootstrapper import UpdateError, _apply_update

    prefix = Path(prefix_str)
    old_exe = prefix / "old_conda.exe"
    new_exe_parent = prefix / "new_standalone"
    new_exe = new_exe_parent / "conda.exe"

    old_exe.write_text("old content")
    new_exe_parent.mkdir()
    new_exe.write_text("new content")

    with patch("shutil.copy2", side_effect=OSError("Copy failed")):
        try:
            _apply_update(new_exe, old_exe)
            print("FAIL: should have raised")
            sys.exit(1)
        except UpdateError as e:
            if "rolled back" not in str(e):
                print(f"FAIL: wrong message: {e}")
                sys.exit(1)

    assert old_exe.read_text() == "old content"
    print("PASS")


def _script_apply_update_cleans_stale(prefix_str: str, conda_exe: str):
    import subprocess
    import sys
    import time
    from pathlib import Path

    from conda_constructor.update_bootstrapper import RELOCATED_NAME_SUFFIX, _apply_update

    prefix = Path(prefix_str)
    old_exe = prefix / "old_conda.exe"
    new_exe = Path(conda_exe)
    stale_relocated = old_exe.with_stem(f"{old_exe.stem}{RELOCATED_NAME_SUFFIX}")

    old_exe.write_text("old content")
    stale_relocated.write_text("stale content")

    original_popen = subprocess.Popen

    def patched_popen(args, _conda_exe=conda_exe, _original_popen=original_popen, **kwargs):
        # Replace the fake executable with the real conda-standalone
        args = [_conda_exe] + args[1:]
        return _original_popen(args, **kwargs)

    # Patch Popen to use real conda-standalone for cleanup subprocess
    subprocess.Popen = patched_popen
    try:
        _apply_update(new_exe, old_exe)
    finally:
        subprocess.Popen = original_popen

    # Verify update succeeded
    assert old_exe.read_bytes() == new_exe.read_bytes()

    relocated = old_exe.with_stem(f"{old_exe.stem}{RELOCATED_NAME_SUFFIX}")
    if sys.platform == "win32":
        for _ in range(600):
            if not relocated.exists():
                break
            time.sleep(0.1)
    assert not relocated.exists()
    print("PASS")


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_update_bootstrapper_help():
    run_conda("constructor", "update-bootstrapper", "--help", check=True)


def test_find_update():
    """Test _find_update finds a newer version when one exists."""
    process = _run_script(_script_find_update)
    assert process.returncode == 0
    assert "PASS" in process.stdout


def test_find_update_already_up_to_date():
    """Test _find_update returns None when already at the latest version."""
    process = _run_script(_script_find_update_already_up_to_date)
    assert process.returncode == 0
    assert "PASS" in process.stdout


def test_apply_update(tmp_path: Path):
    """Test _apply_update replaces the executable and cleans up."""
    from utils import CONDA_EXE

    process = _run_script(_script_apply_update, prefix_str=str(tmp_path), conda_exe=CONDA_EXE)
    assert process.returncode == 0
    assert "PASS" in process.stdout


def test_apply_update_rollback_on_failure(tmp_path: Path):
    """Test _apply_update rolls back on copy failure."""
    process = _run_script(_script_apply_update_rollback, prefix_str=str(tmp_path))
    assert process.returncode == 0
    assert "PASS" in process.stdout


def test_apply_update_cleans_stale_relocated(tmp_path: Path):
    """Test _apply_update removes stale relocated files before updating."""
    from utils import CONDA_EXE

    process = _run_script(
        _script_apply_update_cleans_stale, prefix_str=str(tmp_path), conda_exe=CONDA_EXE
    )
    assert process.returncode == 0
    assert "PASS" in process.stdout
