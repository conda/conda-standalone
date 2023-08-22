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


def run_conda(*args, **kwargs):
    return subprocess.run([CONDA_EXE, *args], **kwargs)


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


def test_menuinst(tmp_path: Path):
    # Check 'regular' conda can process menuinst JSONs
    prefix1 = tmp_path / "prefix1"
    p = run_conda(
        "create",
        "-p",
        prefix1,
        "miniforge_console_shortcut",
        check=True,
        capture_output=True,
        text=True,
    )
    assert "menuinst Exception" not in p.stdout
    assert list(prefix1.glob("Menu/*.json"))

    # The constructor helper should also be able to process them
    prefix2 = tmp_path / "prefix2"
    p = run_conda(
        "create",
        "-p",
        prefix2,
        "--no-shortcuts",
        "miniforge_console_shortcut",
        check=True,
    )
    p = run_conda("constructor", "--prefix", prefix2, "--make-menus", check=True)


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
