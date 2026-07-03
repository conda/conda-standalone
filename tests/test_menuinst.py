import os
import sys
from pathlib import Path

import pytest
from utils import run_conda


@pytest.mark.parametrize(
    "args_install,args_remove",
    (
        pytest.param(("menuinst", "--install"), ("menuinst", "--remove"), id="menuinst"),
        pytest.param(("constructor", "--make-menus"), ("constructor", "--rm-menus"), id="legacy"),
    ),
)
def test_menuinst_conda_standalone(
    tmp_path: Path,
    args_install: tuple[str, ...],
    args_remove: tuple[str, ...],
    clean_shortcuts: dict[str, list[Path]],
):
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
        *args_install,
        # Not supported in micromamba's interface yet
        # use CONDA_ROOT_PREFIX instead
        # "--root-prefix",
        # sys.prefix,
        "--prefix",
        tmp_path,
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
        *args_remove,
        # Not supported in micromamba's interface yet
        # use CONDA_ROOT_PREFIX instead
        # "--root-prefix",
        # sys.prefix,
        "--prefix",
        tmp_path,
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


@pytest.mark.skipif(sys.platform != "darwin", reason="macOS only")
def test_macos_launchers_shipped_unmodified(tmp_path: Path):
    """
    The frozen menuinst launcher templates must keep their original load
    commands. PyInstaller's binary processing used to rewrite their rpaths,
    stripping /usr/lib/swift from appkit_launcher_*, which broke Swift
    runtime resolution on x86_64 (conda/menuinst#507).
    """
    script = (
        "import glob, os, shutil, sys, menuinst; "
        "data_dir = os.path.join(os.path.dirname(menuinst.__file__), 'data'); "
        "[shutil.copy(path, sys.argv[1]) "
        "for path in glob.glob(os.path.join(data_dir, 'appkit_launcher_*'))]"
    )
    run_conda(
        "python",
        "-c",
        script,
        str(tmp_path),
        capture_output=True,
        text=True,
        check=True,
    )
    launchers = list(tmp_path.glob("appkit_launcher_*"))
    assert launchers, "no appkit launcher templates found in frozen menuinst"
    for launcher in launchers:
        assert b"/usr/lib/swift" in launcher.read_bytes(), (
            f"{launcher.name} lost its /usr/lib/swift rpath"
        )
