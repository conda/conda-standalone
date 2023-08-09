import os
import subprocess
import sys

import pytest

CONDA_EXE = os.environ.get(
    "CONDA_STANDALONE",
    os.path.join(sys.prefix, "standalone_conda", "conda.exe"),
)


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
