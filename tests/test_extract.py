import io
import shutil
import stat
import subprocess
import sys
import tarfile
from pathlib import Path

from utils import CONDA_EXE, run_conda

HERE = Path(__file__).parent


def test_extract_conda_pkgs(tmp_path: Path):
    shutil.copytree(HERE / "data", tmp_path / "pkgs")
    run_conda("constructor", "--prefix", tmp_path, "--extract-conda-pkgs", check=True)


def test_extract_tarball_no_raise_deprecation_warning(tmp_path: Path):
    # See https://github.com/conda/conda-standalone/issues/143
    tarbytes = (HERE / "data" / "futures-compat-1.0-py3_0.tar.bz2").read_bytes()
    process = run_conda(
        "constructor",
        "--prefix",
        tmp_path,
        "--extract-tarball",
        input=tarbytes,
        capture_output=True,
        check=True,
    )
    assert b"DeprecationWarning: Python" not in process.stderr
    # warnings should be send to stderr but check stdout for completeness
    assert b"DeprecationWarning: Python" not in process.stdout


def test_extract_tarball_umask(tmp_path: Path):
    "Ported from https://github.com/conda/conda-package-streaming/pull/65"

    def empty_tarfile_bytes(name, mode=0o644):
        """
        Return BytesIO containing a tarfile with one empty file named :name
        """
        tar = io.BytesIO()
        t = tarfile.TarFile(mode="w", fileobj=tar)
        tarinfo = tarfile.TarInfo(name=name)
        tarinfo.mode = mode
        t.addfile(tarinfo, io.BytesIO())
        t.close()
        tar.seek(0)
        return tar

    naughty_mode = 0o777
    umask = 0o022
    tarbytes = empty_tarfile_bytes(name="naughty_umask", mode=naughty_mode)
    process = subprocess.Popen(
        [CONDA_EXE, "constructor", "--prefix", tmp_path, "--extract-tarball"],
        stdin=subprocess.PIPE,
        umask=umask,
    )
    process.communicate(tarbytes.getvalue())
    rc = process.wait()
    assert rc == 0
    if sys.platform != "win32":
        mode = (tmp_path / "naughty_umask").stat().st_mode
        # we only want the chmod bits (last three octal digits)
        chmod_bits = stat.S_IMODE(mode)
        expected_bits = naughty_mode & ~umask
        assert chmod_bits == expected_bits == 0o755, f"{expected_bits:o}"


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
