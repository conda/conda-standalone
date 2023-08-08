import os
import subprocess
import sys

import pytest


CONDA_EXE = os.environ.get(
    "CONDA_STANDALONE",
    os.path.join(sys.prefix, "standalone_conda", "conda.exe")
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
