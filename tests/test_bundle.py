"""Tests for the libraries bundled inside the frozen conda executable."""

from __future__ import annotations

import os
import re
import sys
from typing import TYPE_CHECKING

import pytest
from utils import run_conda

if TYPE_CHECKING:
    from pathlib import Path

_GLIBC_VERSION = re.compile(r"GLIBC_(\d+)\.(\d+)(?:\.(\d+))?")

_COPY_SHARED_LIBRARIES = """
import pathlib
import shutil
import sys

source = pathlib.Path(sys._MEIPASS)
destination = pathlib.Path(sys.argv[1])

for path in source.rglob("*"):
    if path.is_file() and ".so" in path.name:
        target = destination / path.relative_to(source)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)
"""


@pytest.fixture
def glibc_floor() -> tuple[int, ...] | None:
    value = os.environ.get("CONDA_STDLIB_VERSION")
    if value is None:
        return None
    components = tuple(int(component) for component in value.split("."))
    if len(components) not in (2, 3):
        return None
    return components


def _required_glibc_versions(path: Path) -> set[tuple[int, ...]]:
    from elftools.elf.elffile import ELFFile

    versions = set()
    with path.open("rb") as stream:
        section = ELFFile(stream).get_section_by_name(".gnu.version_r")
        if section is None:
            return versions
        for _, auxiliaries in section.iter_versions():
            for auxiliary in auxiliaries:
                if match := _GLIBC_VERSION.fullmatch(auxiliary.name):
                    versions.add(tuple(int(part) for part in match.groups() if part is not None))
    return versions


@pytest.mark.skipif(sys.platform != "linux", reason="GLIBC symbol versions are Linux-specific")
def test_bundled_shared_libraries_meet_glibc_floor(
    tmp_path: Path,
    glibc_floor: tuple[int, ...] | None,
):
    if glibc_floor is None:
        pytest.skip(
            "No minimum GLIBC version defined or version specification invalid. "
            "Set minimum GLIBC version using the CONDA_STDLIB_VERSION environment variable."
        )
    run_conda("python", "-c", _COPY_SHARED_LIBRARIES, str(tmp_path), check=True)

    violations = {}
    for path in sorted(tmp_path.rglob("*.so*")):
        if not path.is_file():
            continue
        too_new = {version for version in _required_glibc_versions(path) if version > glibc_floor}
        if too_new:
            violations[str(path.relative_to(tmp_path))] = sorted(too_new)

    assert not violations, (
        f"bundled shared libraries require GLIBC newer than {glibc_floor}: {violations}"
    )
