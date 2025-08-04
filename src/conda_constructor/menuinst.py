from pathlib import Path

from menuinst import install


def install_shortcut(
    prefix: Path,
    pkg_names: list[str] | None = None,
    root_prefix: Path | None = None,
    remove: bool = False,
):
    for json_path in (prefix / "Menu").glob("*.json"):
        if pkg_names and json_path.stem not in pkg_names:
            continue
        install(str(json_path), remove=remove, prefix=str(prefix), root_prefix=str(root_prefix))
