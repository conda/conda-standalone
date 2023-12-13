import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

CONDA_EXE = os.environ.get(
    "CONDA_STANDALONE",
    os.path.join(sys.prefix, "standalone_conda", "conda.exe"),
)
HERE = Path(__file__).parent


def run_conda(*args, **kwargs) -> subprocess.CompletedProcess:
    check = kwargs.pop("check", False)
    p = subprocess.run([CONDA_EXE, *args], **kwargs)
    if check:
        if kwargs.get("capture_output") and p.returncode:
            print(p.stdout)
            print(p.stderr, file=sys.stderr)
        p.check_returncode()
    return p


def _get_shortcut_dir(prefix=None):
    from menuinst.utils import needs_admin

    user_mode = (
        "system" if needs_admin(prefix or sys.prefix, sys.prefix) else "user"
    )
    if sys.platform == "win32":
        from menuinst.platforms.win_utils.knownfolders import (
            dirs_src as win_locations,
        )
        return Path(win_locations[user_mode]["start"][0])
    if sys.platform == "darwin":
        if user_mode == "user":
            return Path(os.environ["HOME"], "Applications")
        return Path("/Applications")
    if sys.platform == "linux":
        if user_mode == "user":
            return Path(os.environ["HOME"], ".local", "share", "applications")
        return Path("/usr/share/applications")
    raise NotImplementedError(sys.platform)


@pytest.mark.parametrize("solver", ["classic", "libmamba"])
def test_new_environment(tmp_path, solver):
    env = os.environ.copy()
    env["CONDA_SOLVER"] = solver
    run_conda(
        "create",
        "-p",
        tmp_path / "env",
        "-y",
        "-c",
        "conda-forge",
        "libzlib",
        env=env,
        check=True,
    )
    assert list((tmp_path / "env" / "conda-meta").glob("libzlib-*.json"))


def test_constructor():
    run_conda("constructor", "--help", check=True)


def test_extract_conda_pkgs(tmp_path: Path):
    shutil.copytree(HERE / "data", tmp_path / "pkgs")
    run_conda("constructor", "--prefix", tmp_path, "--extract-conda-pkgs", check=True)


def test_extract_conda_pkgs_num_processors(tmp_path: Path):
    shutil.copytree(HERE / "data", tmp_path / "pkgs")
    run_conda(
        "constructor",
        "--prefix",
        tmp_path,
        "--extract-conda-pkgs",
        "--num-processors=2",
        check=True,
    )


_pkg_specs = [
    (
        "conda-test/label/menuinst-tests::package_1",
        {
            "win32": "Package 1/A.lnk",
            "darwin": "A.app/Contents/MacOS/a",
            "linux": "package-1_a.desktop",
        },
    ),
]
if os.name == "nt":
    _pkg_specs.append(
        (
            "conda-forge::miniforge_console_shortcut",
            {"win32": "Anaconda3 (64-bit)/Anaconda Prompt ({prefix}).lnk"},
        ),
    )
_pkg_specs_params = pytest.mark.parametrize("pkg_spec, shortcut_path", _pkg_specs)


@_pkg_specs_params
def test_menuinst_conda(tmp_path: Path, pkg_spec: str, shortcut_path: str):
    "Check 'regular' conda can process menuinst JSONs"
    (tmp_path / ".nonadmin").touch()  # prevent elevation
    p = run_conda(
        "create",
        "-vvv",
        "-p",
        tmp_path,
        "-y",
        pkg_spec,
        "--no-deps",
        capture_output=True,
        text=True,
        check=True,
    )
    print(p.stdout)
    print(p.stderr, file=sys.stderr)
    assert "menuinst Exception" not in p.stdout
    assert list(tmp_path.glob("Menu/*.json"))
    created_shortcut = _get_shortcut_dir(tmp_path) / shortcut_path[sys.platform].format(
        prefix=tmp_path
    )
    assert created_shortcut.is_file()

    p = run_conda(
        "remove",
        "-vvv",
        "-p",
        tmp_path,
        "-y",
        pkg_spec.split("::")[-1],
        capture_output=True,
        text=True,
        check=True,
    )
    print(p.stdout)
    print(p.stderr, file=sys.stderr)
    assert not created_shortcut.is_file()


@_pkg_specs_params
def test_menuinst_constructor(tmp_path: Path, pkg_spec: str, shortcut_path: str):
    "The constructor helper should also be able to process menuinst JSONs"
    run_kwargs = dict(capture_output=True, text=True, check=True)
    (tmp_path / ".nonadmin").touch()  # prevent elevation
    p = run_conda(
        "create",
        "-vvv",
        "-p",
        tmp_path,
        "-y",
        pkg_spec,
        "--no-deps",
        "--no-shortcuts",
        **run_kwargs,
    )
    print(p.stdout)
    print(p.stderr, file=sys.stderr)
    assert list(tmp_path.glob("Menu/*.json"))

    p = run_conda("constructor", "--prefix", tmp_path, "--make-menus", **run_kwargs)
    print(p.stdout)
    print(p.stderr, file=sys.stderr)
    created_shortcut = _get_shortcut_dir(tmp_path) / shortcut_path[sys.platform].format(
        prefix=tmp_path
    )
    assert created_shortcut.is_file()

    p = run_conda("constructor", "--prefix", tmp_path, "--rm-menus", **run_kwargs)
    print(p.stdout)
    print(p.stderr, file=sys.stderr)
    assert not created_shortcut.is_file()


def test_python():
    p = run_conda("python", "-V", check=True, capture_output=True, text=True)
    assert p.stdout.startswith("Python 3.")

    p = run_conda(
        "python",
        "-m",
        "calendar",
        "2023",
        "12",
        check=True,
        capture_output=True,
        text=True,
    )
    assert "2023" in p.stdout

    p = run_conda(
        "python",
        "-c",
        "import sys; print(sys.argv)",
        "extra-arg",
        check=True,
        capture_output=True,
        text=True,
    )
    assert eval(p.stdout) == ["-c", "extra-arg"]
