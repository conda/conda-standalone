from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from .extract import DEFAULT_NUM_PROCESSORS, ExtractType, _NumProcessorsAction, extract
from .uninstall import uninstall

if TYPE_CHECKING:
    from argparse import ArgumentParser, Namespace
    from collections.abc import Callable


def _add_prefix(parser: ArgumentParser) -> None:
    # Prefix must be string or it will break conda's context initializer
    parser.add_argument(
        "--prefix",
        action="store",
        type=str,
        required=True,
        help="path to the conda environment to operate on",
    )


def _add_extract(parser: ArgumentParser) -> None:
    extract_group = parser.add_mutually_exclusive_group(required=True)
    extract_group.add_argument(
        "--conda-pkgs",
        action="store_const",
        const=ExtractType.PACKAGES,
        dest="pkg_format",
        help="extract conda packages found in prefix/pkgs",
    )
    extract_group.add_argument(
        "--tar-from-stdin",
        action="store_const",
        const=ExtractType.TAR,
        dest="pkg_format",
        help="extract tarball from stdin",
    )
    parser.add_argument(
        "--num-processors",
        default=DEFAULT_NUM_PROCESSORS,
        metavar="N",
        action=_NumProcessorsAction,
        help="Number of processors to use with --extract-conda-pkgs. "
        "Value must be int between 0 (auto) and the number of processors. "
        f"Defaults to {DEFAULT_NUM_PROCESSORS}.",
    )


def _add_uninstall(parser: ArgumentParser) -> None:
    parser.add_argument(
        "--remove-caches",
        action="store_true",
        required=False,
        help=(
            "Removes the notices cache and runs conda --clean --all to clean package caches"
            " outside the installation directory."
            " This is especially useful when pkgs_dirs is set in a .condarc file."
            " Not recommended with multiple conda installations when softlinks are enabled."
        ),
    )
    parser.add_argument(
        "--remove-config-files",
        choices=["user", "system", "all"],
        default=None,
        required=False,
        help=(
            "Removes all .condarc files."
            " `user` removes the files inside the current user's"
            " home directory and `system` removes all files outside of that directory."
            " Not recommended when multiple conda installations are on the system"
            " or when running on an environments directory."
        ),
    )
    parser.add_argument(
        "--remove-user-data",
        action="store_true",
        required=False,
        help=(
            "Removes the ~/.conda directory."
            " Not recommended when multiple conda installations are on the system"
            " or when running on an environments directory."
        ),
    )


def configure_parser(parser: ArgumentParser) -> None:
    subparsers = parser.add_subparsers(
        title="subcommand",
        description="The following subcommands are available.",
        dest="cmd",
        required=False,
    )

    extract_parser = subparsers.add_parser(
        "extract",
        description="Extracts tarballs or conda packages.",
    )
    _add_prefix(extract_parser)
    _add_extract(extract_parser)

    uninstall_parser = subparsers.add_parser(
        "uninstall",
        description="Uninstalls a conda directory and all environments inside the directory.",
    )
    _add_prefix(uninstall_parser)
    _add_uninstall(uninstall_parser)


def execute(args: Namespace) -> None | int:
    action: Callable
    kwargs = {}
    if args.cmd == "extract":
        action = extract
        kwargs.update(
            {
                "package_format": args.pkg_format,
                "max_workers": args.num_processors,
            }
        )
    elif args.cmd == "uninstall":
        action = uninstall
        kwargs.update(
            {
                "remove_caches": args.remove_caches,
                "remove_config_files": args.remove_config_files,
                "remove_user_data": args.remove_user_data,
            }
        )
    else:
        raise NotImplementedError(f"No action available for subcommand '{args.cmd}'.")
    return action(
        prefix=Path(args.prefix).expanduser().resolve(),
        **kwargs,
    )
