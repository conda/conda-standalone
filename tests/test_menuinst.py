import os
import sys
from pathlib import Path

from utils import run_conda


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
