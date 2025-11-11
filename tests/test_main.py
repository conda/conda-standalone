import json
import os
import re
import subprocess
import sys
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


def test_install_conda(tmp_path):
    # Use regex to avoid matching with conda plug-ins or other packages
    # starting with "conda-"
    conda_json_regex = re.compile(r"conda-[\d]+\.[\d]+\.[\d]-.*\.json$")
    run_conda(
        "create",
        "-p",
        tmp_path / "env",
        "-y",
        "conda",
        check=True,
    )
    assert any(
        conda_json_regex.search(str(file))
        for file in (tmp_path / "env" / "conda-meta").glob("conda-*.json")
    )


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
    # Unset `CONDARC` to detect .condarc file of conda-standalone
    monkeypatch.delenv("CONDARC", raising=False)
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


def test_conda_run():
    env = os.environ.copy()
    for key in os.environ:
        if key.startswith(("CONDA", "_CONDA_", "__CONDA", "_CE_")):
            env.pop(key, None)

    process = run_conda(
        "run",
        "-p",
        sys.prefix,
        "python",
        "-c",
        "import sys;print(sys.executable)",
        check=True,
        text=True,
        capture_output=True,
        env=env,
    )
    assert os.path.realpath(process.stdout.strip()) == os.path.realpath(sys.executable)
    if sys.platform.startswith("win") and os.environ.get("CI"):
        # on CI, setup-miniconda registers `test` as auto-activate for every CMD
        # which adds some unnecessary stderr output; I couldn't find a way to prevent this
        # (tried conda init --reverse) so we'll have to live with this skipped check;
        # in a local setup it does work
        pass
    else:
        assert not process.stderr


@pytest.mark.parametrize("with_log", (True, False), ids=("with log", "no log"))
def test_conda_run_conda_exe(tmp_path: Path, with_log: bool):
    env = os.environ.copy()
    log_file = tmp_path / "conda_run.log"
    for key in os.environ:
        if key.startswith(("CONDA", "_CONDA_", "__CONDA", "_CE_")):
            env.pop(key, None)

    process = run_conda(
        "run",
        "-p",
        sys.prefix,
        "python",
        "-c",
        "import sys,os;print(os.environ['CONDA_EXE'])",
        *(("--log-file", str(log_file)) if with_log else ()),
        check=True,
        text=True,
        capture_output=True,
        env=env,
    )
    assert os.path.realpath(process.stdout.strip()) == os.path.realpath(CONDA_EXE)
    if with_log:
        assert log_file.exists()
        log_text = log_file.read_text().strip()
        if sys.platform.startswith("win") and os.environ.get("CI"):
            # on CI, setup-miniconda registers `test` as auto-activate for every CMD
            # which adds some unnecessary stderr output; so, only read the first line
            log_text = log_text.split("\n")[0]
        assert os.path.realpath(log_text.strip()) == os.path.realpath(CONDA_EXE)
