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


_pkg_specs = ["napari-menu"]
if os.name == "nt":
    _pkg_specs.append("miniforge_console_shortcut")
_pkg_specs_params = pytest.mark.parametrize("pkg_spec", _pkg_specs)


@_pkg_specs_params
def test_menuinst_conda(tmp_path: Path, pkg_spec: str):
    "Check 'regular' conda can process menuinst JSONs"
    (tmp_path / ".nonadmin").touch()  # prevent elevation
    p = run_conda(
        "create",
        "-p",
        tmp_path,
        "-y",
        f"conda-forge::{pkg_spec}",
        "--no-deps",
        capture_output=True,
        text=True,
        check=True,
    )
    assert "menuinst Exception" not in p.stdout
    assert list(tmp_path.glob("Menu/*.json"))


@_pkg_specs_params
def test_menuinst_constructor(tmp_path: Path, pkg_spec: str):
    "The constructor helper should also be able to process menuinst JSONs"
    run_kwargs = dict(capture_output=True, text=True, check=True)
    (tmp_path / ".nonadmin").touch()  # prevent elevation

    # --no-shortcuts on non-Windows needs https://github.com/conda/conda/pull/11882
    env = os.environ.copy()
    env["CONDA_SHORTCUTS"] = "false"
    run_conda(
        "create",
        "-p",
        tmp_path,
        "-y",
        f"conda-forge::{pkg_spec}",
        "--no-deps",
        env=env,
        **run_kwargs,
    )
    assert list(tmp_path.glob("Menu/*.json"))
    run_conda("constructor", "--prefix", tmp_path, "--make-menus", **run_kwargs)
    run_conda("constructor", "--prefix", tmp_path, "--rm-menus", **run_kwargs)


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
