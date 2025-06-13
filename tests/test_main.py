import io
import json
import os
import shutil
import stat
import subprocess
import sys
import tarfile
from pathlib import Path

import pytest
from ruamel.yaml import YAML
from utils import CONDA_EXE, run_conda

HERE = Path(__file__).parent


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


@pytest.mark.parametrize(
    "args",
    (
        pytest.param(["--prefix", "path"], id="missing command"),
        pytest.param(["--extract-conda-pkgs"], id="missing prefix"),
    ),
)
def test_constructor_missing_arguments(args: list[str]):
    with pytest.raises(subprocess.CalledProcessError):
        run_conda("constructor", *args, check=True)


@pytest.mark.parametrize("search_paths", ("all_rcs", "--no-rc", "env_var"))
def test_conda_standalone_config(search_paths, tmp_path, monkeypatch):
    variant = os.environ.get("PYINSTALLER_BUILD_VARIANT", "single-binary")
    expected_configs = {}
    yaml = YAML()
    if rc_dir := os.environ.get("PYINSTALLER_CONDARC_DIR"):
        condarc = Path(rc_dir, ".condarc")
        if condarc.exists():
            with open(condarc) as crc:
                config = YAML().load(crc)
                if variant == "single-binary":
                    expected_configs["standalone"] = config.copy()
                elif variant == "onedir":
                    condarc_path = Path(
                        os.environ["PREFIX"],
                        "standalone_conda",
                        "_internal",
                        ".condarc",
                    )
                    expected_configs[str(condarc_path)] = config.copy()
                else:
                    pytest.skip(f"Unknown build variant {variant}.")

    config_args = ["--show-sources", "--json"]
    if search_paths == "env_var":
        monkeypatch.setenv("CONDA_RESTRICT_RC_SEARCH_PATH", "1")
    elif search_paths == "--no-rc":
        config_args.append("--no-rc")
    else:
        config_path = str(tmp_path / ".condarc")
        expected_configs[config_path] = {
            "channels": [
                "defaults",
            ]
        }
        with open(config_path, "w") as crc:
            yaml.dump(expected_configs[config_path], crc)
        monkeypatch.setenv("CONDA_ROOT", str(tmp_path))
    env = os.environ.copy()

    proc = run_conda(
        "config",
        *config_args,
        check=True,
        capture_output=True,
        text=True,
        env=env,
    )
    condarcs = json.loads(proc.stdout)

    tmp_root = None
    if rc_dir and variant == "single-binary":
        # Quick way to get the location conda-standalone is extracted into
        proc = run_conda(
            "python",
            "-c",
            "import sys; print(sys.prefix)",
            check=True,
            capture_output=True,
            text=True,
            env=env,
        )
        tmp_root = str(Path(proc.stdout).parent)

    conda_configs = {}
    for filepath, config in condarcs.items():
        if Path(filepath).exists():
            conda_configs[filepath] = config.copy()
        elif tmp_root and filepath.startswith(tmp_root):
            conda_configs["standalone"] = config.copy()
    if search_paths == "all_rcs":
        # If the search path is restricted, there may be other .condarc
        # files in the final config, so be less strict with assertions
        for filepath, config in expected_configs.items():
            assert conda_configs.get(filepath) == config, f"Incorrect config for {filepath}"
    else:
        assert expected_configs == conda_configs


def test_extract_conda_pkgs(tmp_path: Path):
    shutil.copytree(HERE / "data", tmp_path / "pkgs")
    run_conda("constructor", "--prefix", tmp_path, "--extract-conda-pkgs", check=True)


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


def test_menuinst_conda(tmp_path: Path, clean_shortcuts: dict[str, list[Path]]):
    "Check 'regular' conda can process menuinst JSONs"

    env = os.environ.copy()
    env["CONDA_ROOT_PREFIX"] = sys.prefix
    process = run_conda(
        "create",
        "-vvv",
        "-p",
        tmp_path,
        "-y",
        *clean_shortcuts.keys(),
        "--no-deps",
        env=env,
        capture_output=True,
        text=True,
        check=True,
    )
    print(process.stdout)
    print(process.stderr, file=sys.stderr)
    assert "menuinst Exception" not in process.stdout
    assert list(tmp_path.glob("Menu/*.json"))
    shortcuts_found = [
        package
        for package, shortcuts in clean_shortcuts.items()
        if any(shortcut.exists() for shortcut in shortcuts)
    ]
    assert sorted(shortcuts_found) == sorted(clean_shortcuts.keys())
    process = run_conda(
        "remove",
        "-vvv",
        "-p",
        tmp_path,
        "-y",
        *[pkg_spec.split("::")[-1] for pkg_spec in clean_shortcuts.keys()],
        env=env,
        capture_output=True,
        text=True,
        check=True,
    )
    print(process.stdout)
    print(process.stderr, file=sys.stderr)
    shortcuts_found = [
        package
        for package, shortcuts in clean_shortcuts.items()
        if any(shortcut.exists() for shortcut in shortcuts)
    ]
    assert shortcuts_found == []


def test_menuinst_constructor(tmp_path: Path, clean_shortcuts: dict[str, list[Path]]):
    "The constructor helper should also be able to process menuinst JSONs"
    run_kwargs = dict(capture_output=True, text=True, check=True)
    process = run_conda(
        "create",
        "-vvv",
        "-p",
        tmp_path,
        "-y",
        *clean_shortcuts.keys(),
        "--no-deps",
        "--no-shortcuts",
        **run_kwargs,
    )
    print(process.stdout)
    print(process.stderr, file=sys.stderr)
    assert list(tmp_path.glob("Menu/*.json"))

    env = os.environ.copy()
    env["CONDA_ROOT_PREFIX"] = sys.prefix
    process = run_conda(
        "constructor",
        # Not supported in micromamba's interface yet
        # use CONDA_ROOT_PREFIX instead
        # "--root-prefix",
        # sys.prefix,
        "--prefix",
        tmp_path,
        "--make-menus",
        **run_kwargs,
        env=env,
    )
    print(process.stdout)
    print(process.stderr, file=sys.stderr)
    shortcuts_found = [
        package
        for package, shortcuts in clean_shortcuts.items()
        if any(shortcut.exists() for shortcut in shortcuts)
    ]
    assert sorted(shortcuts_found) == sorted(clean_shortcuts.keys())

    process = run_conda(
        "constructor",
        # Not supported in micromamba's interface yet
        # use CONDA_ROOT_PREFIX instead
        # "--root-prefix",
        # sys.prefix,
        "--prefix",
        tmp_path,
        "--rm-menus",
        **run_kwargs,
        env=env,
    )
    print(process.stdout)
    print(process.stderr, file=sys.stderr)
    shortcuts_found = [
        package
        for package, shortcuts in clean_shortcuts.items()
        if any(shortcut.exists() for shortcut in shortcuts)
    ]
    assert shortcuts_found == []


def test_python():
    process = run_conda("python", "-V", check=True, capture_output=True, text=True)
    assert process.stdout.startswith("Python 3.")

    process = run_conda(
        "python",
        "-m",
        "calendar",
        "2023",
        "12",
        check=True,
        capture_output=True,
        text=True,
    )
    assert "2023" in process.stdout

    process = run_conda(
        "python",
        "-c",
        "import sys; print(sys.argv)",
        "extra-arg",
        check=True,
        capture_output=True,
        text=True,
    )
    assert eval(process.stdout) == ["-c", "extra-arg"]
