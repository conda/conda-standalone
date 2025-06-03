import itertools
import os
import shutil
import sys
from pathlib import Path

import pytest
from utils import _get_shortcut_dirs


@pytest.fixture
def menuinst_pkg_specs():
    specs = [
        (
            "conda-test/label/menuinst-tests::package_1",
            {
                "win32": "Package 1/A.lnk",
                "darwin": "A.app",
                "linux": "package-1_a.desktop",
            },
        ),
    ]
    if os.name == "nt":
        specs.append(
            (
                "conda-forge::miniforge_console_shortcut",
                {"win32": "{base}/{base} Prompt ({name}).lnk"},
            ),
        )
    return specs


# If the test app already exists, tests will fail,
# so clean up before and after the run.
def _clean_macos_apps(shortcuts: dict[str, list[Path]]):
    if not sys.platform == "darwin":
        return
    for shortcut in itertools.chain.from_iterable(shortcuts.values()):
        if shortcut.exists():
            shutil.rmtree(shortcut)


@pytest.fixture
def clean_shortcuts(tmp_path: Path, menuinst_pkg_specs: list[tuple[str, dict[str, str]]]):
    # The shortcut will take 'root_prefix' as the base, but conda-standalone
    # sets that to its temporary 'sys.prefix' as provided by the pyinstaller
    # self-extraction. We override it via 'CONDA_ROOT_PREFIX' in the same
    # way 'constructor' will do it.
    variables = {"base": Path(sys.prefix).name, "name": tmp_path.name}
    shortcuts = {}
    for package, spec in menuinst_pkg_specs:
        shortcuts[package] = [
            folder / spec[sys.platform].format(**variables) for folder in _get_shortcut_dirs()
        ]
    _clean_macos_apps(shortcuts)
    yield shortcuts
    _clean_macos_apps(shortcuts)
