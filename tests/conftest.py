import os
import subprocess
import sys
from pathlib import Path

# TIP: You can debug the tests with this setup:
# CONDA_STANDALONE=src/entry_point.py pytest ...
CONDA_EXE = os.environ.get(
    "CONDA_STANDALONE",
    os.path.join(sys.prefix, "standalone_conda", "conda.exe"),
)


menuinst_pkg_specs = [
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
    menuinst_pkg_specs.append(
        (
            "conda-forge::miniforge_console_shortcut",
            {"win32": "{base}/{base} Prompt ({name}).lnk"},
        ),
    )


def run_conda(*args, **kwargs) -> subprocess.CompletedProcess:
    check = kwargs.pop("check", False)
    sudo = None
    if "needs_sudo" in kwargs:
        if kwargs["needs_sudo"]:
            if sys.platform == "win32":
                raise NotImplementedError(
                    "Calling run_conda with elevated privileged is not available on Windows"
                )
            sudo = ["sudo"]
        del kwargs["needs_sudo"]
    cmd = [*sudo, CONDA_EXE] if sudo else [CONDA_EXE]

    process = subprocess.run([*cmd, *args], **kwargs)
    if check:
        if kwargs.get("capture_output"):
            print(process.stdout)
            print(process.stderr, file=sys.stderr)
        process.check_returncode()
    return process


def _get_shortcut_dirs() -> list[Path]:
    if sys.platform == "win32":
        from menuinst.platforms.win_utils.knownfolders import dirs_src as win_locations

        return [
            Path(win_locations["user"]["start"][0]),
            Path(win_locations["system"]["start"][0]),
        ]
    if sys.platform == "darwin":
        return [
            Path(os.environ["HOME"], "Applications"),
            Path("/Applications"),
        ]
    if sys.platform == "linux":
        return [
            Path(os.environ["HOME"], ".local", "share", "applications"),
            Path("/usr/share/applications"),
        ]
    raise NotImplementedError(sys.platform)
