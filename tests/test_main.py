import os
import subprocess
import sys

CONDA_EXE = os.environ.get(
    "CONDA_STANDALONE", os.path.join(sys.prefix, "standalone_conda", "conda.exe")
)


def run_conda(*args, **kwargs):
    return subprocess.run([CONDA_EXE, *args], **kwargs)


def test_new_environment(tmp_path):
    env = os.environ.copy()
    env["CONDA_SOLVER"] = "classic"
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

    p = run_conda("python", "-m", "this", check=True, capture_output=True, text=True)
    assert "The Zen of Python, by Tim Peters" in p.stdout

    p = run_conda(
        "python",
        "-c",
        "import sys; print(sys.argv)",
        check=True,
        capture_output=True,
        text=True,
    )
    assert "python" not in p.stdout
