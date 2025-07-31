from pathlib import Path

from menuinst import install


def install_shortcut(prefix, pkg_names=None, root_prefix=None, remove=False):
    for json_path in Path(prefix, "Menu").glob("*.json"):
        if pkg_names and json_path.stem not in pkg_names:
            continue
        install(json_path, remove=remove, prefix=prefix, root_prefix=root_prefix)
