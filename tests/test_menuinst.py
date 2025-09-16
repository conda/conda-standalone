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
