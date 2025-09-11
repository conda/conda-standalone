"""Obtain all changed conda source files from a set of patches.

PyInstaller bundles modules from the `site-packages` directory. For `conda-standalone` to work,
`conda` needs to be patched. These patches are applied to the downloaded `conda` source
code during the `conda-build` process. For PyInstaller to use the patched version of `conda`,
the patched files need to be copied to the `conda` package in the `site-packages` directory.
"""

import argparse
import shutil
from pathlib import Path


def get_files_from_patch(patch_file: Path) -> list[str]:
    """Parse patch file to obtain changed files.

    Parameters
    ----------
    patch_file: Path
        Path to the patch file to parse.

    Returns
    -------
    file: list[str]
        A list of patched files relative to the `conda` root directory.
    """
    files = []
    patch = patch_file.read_text().split("\n")
    nlines = len(patch)
    for lineno in range(nlines - 1):
        line = patch[lineno]
        if not line.startswith("--- ") or not patch[lineno + 1].startswith("+++ "):
            continue
        patched_file = Path(line.strip().split()[-1])
        if len(patched_file.parts) < 3 or patched_file.parts[1] != "conda":
            continue
        files.append("/".join(patched_file.parts[2:]))
    return files


def copy_patches(patch_source: Path, site_packages: Path, conda_source: Path) -> None:
    """Copy patched conda files to site-packages.

    Parameters
    ----------
    patch_source: Path
        Directory to the patch files.
    site_packages: Path
        Path to the site-packages directory.
    conda_source: Path
        Path to the patched conda source directory.
    """
    patched_files = set()
    for patch_file in patch_source.iterdir():
        if patch_file.suffix != ".patch":
            continue
        patched_files.update(get_files_from_patch(patch_file))
    for file in patched_files:
        source = conda_source / "conda" / file
        destination = site_packages / "conda" / file
        shutil.copy(source, destination)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Copy patched conda files to site-packages.")
    parser.add_argument(
        "--patch-source",
        help="Directory containing patch files.",
        required=True,
    )
    parser.add_argument(
        "--site-packages", help="Path to the site-pakckages directory.", required=True
    )
    parser.add_argument(
        "--conda-source",
        help="Path to the patched conda source code.",
        required=True,
    )
    args = parser.parse_args()
    copy_patches(Path(args.patch_source), Path(args.site_packages), Path(args.conda_source))
