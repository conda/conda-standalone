from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import TYPE_CHECKING

from conda.base.context import context, reset_context
from conda.core.subdir_data import SubdirData
from conda.gateways.connection.download import download
from conda.models.match_spec import MatchSpec
from conda.models.version import VersionOrder
from conda_package_handling import api as cph_api

from conda_constructor._version import __version__

if TYPE_CHECKING:
    from conda.models.records import PackageRecord

RELOCATED_NAME_SUFFIX = ".__relocated__"


class UpdateError(RuntimeError):
    pass


def _find_update(min_version: str) -> PackageRecord | None:
    """Find the latest conda-standalone version if older than the current binary."""
    version = f">={min_version}"
    spec = MatchSpec(name="conda-standalone", version=version)
    matches = sorted(
        SubdirData.query_all(spec, context.channels, context.subdirs),
        key=lambda rec: (VersionOrder(rec.version), rec.build_number),
        reverse=True,
    )
    if not matches:
        return None
    return matches[0]


_CLEANUP_SCRIPT = """\
import os
import time

relocated_exe = r'{relocated_exe}'

for _ in range(600):
    try:
        os.remove(relocated_exe)
    except OSError:
        time.sleep(0.1)
    else:
        break
"""


def _schedule_cleanup_after_exit(
    executable: Path,
    relocated_exe: Path,
) -> None:
    """Schedule the old binary for deletion.

    Since Windows does not allow deleting files with open file handles,
    spawn a detached process that waits until the file handle is freed,
    then delete the relocated file.
    """
    script = _CLEANUP_SCRIPT.format(relocated_exe=relocated_exe)

    # Remove PyInstaller-related environment variables or the relocated
    # executable will inherit them and extract into the same prefix.
    env = {key: val for key, val in os.environ.items() if not key.startswith("_PYI_")}
    subprocess.Popen(
        [executable, "python", "-c", script],
        creationflags=subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP,
        close_fds=True,
        env=env,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def _apply_update(
    new_conda_exe: Path,
    conda_exe: Path,
) -> None:
    """Update conda.exe in place with rollback on failure."""
    relocated_exe = conda_exe.with_stem(f"{conda_exe.stem}{RELOCATED_NAME_SUFFIX}")
    if relocated_exe.exists():
        relocated_exe.unlink()

    os.rename(conda_exe, relocated_exe)
    try:
        shutil.copy2(new_conda_exe, conda_exe)
    except Exception as exc:
        os.rename(relocated_exe, conda_exe)
        os.unlink(new_conda_exe)
        raise UpdateError(f"Update failed, rolled back to previous version: {exc}") from exc

    if sys.platform == "win32":
        _schedule_cleanup_after_exit(conda_exe, relocated_exe)
    else:
        relocated_exe.unlink()


def update_bootstrapper() -> None:
    # Only use the bundled .condarc file so that conda-standalone
    # is not downloaded from a different channel
    os.environ["CONDA_RESTRICT_SEARCH_PATH"] = "1"
    reset_context()

    match = _find_update(__version__)
    if match is None:
        print("Already up-to-date.")
        return

    with TemporaryDirectory() as tmp_path:
        tmp = Path(tmp_path)
        package = tmp / match.fn
        if not package.name.lower().endswith((".conda", ".tar.bz2")):
            raise UpdateError(f"Can't extract unknown package type: '{package.name}'.")

        download(match.url, package, sha256=match.sha256)
        cph_api.extract(str(package), dest_dir=str(tmp))
        new_conda_exe = tmp / "standalone_conda" / "conda.exe"

        if not new_conda_exe.exists():
            raise UpdateError(f"Expected executable not found in package: {new_conda_exe}")

        conda_exe = Path(sys.executable)
        _apply_update(new_conda_exe, conda_exe)
        print(f"Updated conda-standalone to {match.version} (build {match.build}).")
