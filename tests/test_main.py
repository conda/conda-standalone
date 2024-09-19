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

# TIP: You can debug the tests with this setup:
# CONDA_STANDALONE=src/entry_point.py pytest ...
CONDA_EXE = os.environ.get(
    "CONDA_STANDALONE",
    os.path.join(sys.prefix, "standalone_conda", "conda.exe"),
)
HERE = Path(__file__).parent


def run_conda(*args, **kwargs) -> subprocess.CompletedProcess:
    check = kwargs.pop("check", False)
    process = subprocess.run([CONDA_EXE, *args], **kwargs)
    if check:
        if kwargs.get("capture_output") and process.returncode:
            print(process.stdout)
            print(process.stderr, file=sys.stderr)
        process.check_returncode()
    return process


def _get_shortcut_dirs():
    if sys.platform == "win32":
        from menuinst.platforms.win_utils.knownfolders import dirs_src as win_locations

        return Path(win_locations["user"]["start"][0]), Path(
            win_locations["system"]["start"][0]
        )
    if sys.platform == "darwin":
        return Path(os.environ["HOME"], "Applications"), Path("/Applications")
    if sys.platform == "linux":
        return Path(os.environ["HOME"], ".local", "share", "applications"), Path(
            "/usr/share/applications"
        )
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


@pytest.mark.parametrize("search_paths", ("all_rcs", "--no-rc", "env_var"))
def test_conda_standalone_config(search_paths, tmp_path, monkeypatch):
    expected_configs = {}
    if recipe_dir := os.environ.get("PYINSTALLER_CONDARC_DIR"):
        recipe_condarc = Path(recipe_dir, ".condarc")
        if recipe_condarc.exists():
            yaml = YAML()
            with open(recipe_condarc) as crc:
                recipe_config = YAML().load(crc)
                expected_configs["recipe"] = recipe_config

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
    if recipe_dir:
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
            conda_configs[filepath] = config
        elif recipe_dir and filepath.startswith(tmp_root):
            conda_configs["recipe"] = config
    if search_paths == "all_rcs":
        # If the search path is restricted, there may be other .condarc
        # files in the final config, so be less strict with assertions
        for filepath, config in expected_configs.items():
            assert (
                conda_configs.get(filepath) == config
            ), f"Incorrect config for {filepath}"
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
        chmod_bits = stat.S_IMODE(mode)  # we only want the chmod bits (last three octal digits)
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
            {"win32": "{base}/{base} Prompt ({name}).lnk"},
        ),
    )
_pkg_specs_params = pytest.mark.parametrize("pkg_spec, shortcut_path", _pkg_specs)


@_pkg_specs_params
def test_menuinst_conda(tmp_path: Path, pkg_spec: str, shortcut_path: str):
    "Check 'regular' conda can process menuinst JSONs"
    env = os.environ.copy()
    env["CONDA_ROOT_PREFIX"] = sys.prefix
    # The shortcut will take 'root_prefix' as the base, but conda-standalone
    # sets that to its temporary 'sys.prefix' as provided by the pyinstaller
    # self-extraction. We override it via 'CONDA_ROOT_PREFIX' in the same
    # way 'constructor' will do it.
    variables = {"base": Path(sys.prefix).name, "name": tmp_path.name}
    process = run_conda(
        "create",
        "-vvv",
        "-p",
        tmp_path,
        "-y",
        pkg_spec,
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
    assert any(
        (folder / shortcut_path[sys.platform].format(**variables)).is_file()
        for folder in _get_shortcut_dirs()
    )
    process = run_conda(
        "remove",
        "-vvv",
        "-p",
        tmp_path,
        "-y",
        pkg_spec.split("::")[-1],
        env=env,
        capture_output=True,
        text=True,
        check=True,
    )
    print(process.stdout)
    print(process.stderr, file=sys.stderr)
    assert all(
        not (folder / shortcut_path[sys.platform].format(**variables)).is_file()
        for folder in _get_shortcut_dirs()
    )


@_pkg_specs_params
def test_menuinst_constructor(tmp_path: Path, pkg_spec: str, shortcut_path: str):
    "The constructor helper should also be able to process menuinst JSONs"
    run_kwargs = dict(capture_output=True, text=True, check=True)
    variables = {"base": Path(sys.prefix).name, "name": tmp_path.name}
    process = run_conda(
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
    assert any(
        (folder / shortcut_path[sys.platform].format(**variables)).is_file()
        for folder in _get_shortcut_dirs()
    )

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
    assert all(
        not (folder / shortcut_path[sys.platform].format(**variables)).is_file()
        for folder in _get_shortcut_dirs()
    )


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
