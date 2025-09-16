from __future__ import annotations

from typing import TYPE_CHECKING

from conda.plugins.hookspec import hookimpl
from conda.plugins.types import CondaSubcommand

from .cli import configure_parser, execute

if TYPE_CHECKING:
    from collections.abc import Iterator


@hookimpl
def conda_subcommands() -> Iterator[CondaSubcommand]:
    """Return a list of subcommands for the plugin."""
    yield CondaSubcommand(
        name="constructor",
        action=execute,
        summary="A subcommand to provide installer helper functions to `constructor`.",
        configure_parser=configure_parser,
    )
