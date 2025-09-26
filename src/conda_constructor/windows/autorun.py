from __future__ import annotations

import re
import winreg
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

from .registry import WinRegistry

AUTORUN_KEY = r"Software\Microsoft\Command Processor"
AUTORUN_NAMED_VALUE = "AutoRun"


def _get_hive(user_or_system: str) -> int:
    if user_or_system == "user":
        return winreg.HKEY_CURRENT_USER
    elif user_or_system == "system":
        return winreg.HKEY_LOCAL_MACHINE
    else:
        raise ValueError(f"Invalid value: {user_or_system}. Must be `user` or `system`.")


def _add_to_autorun(prefix: Path, user_or_system: str) -> None:
    autorun_regex = re.compile(r"(if +exist)?(\s*?\"[^\"]*?conda[-_]hook\.bat\")", re.IGNORECASE)
    conda_hook = prefix / "condabin" / "conda_hook.bat"
    if not conda_hook.exists():
        raise FileNotFoundError(f"Conda activation script {conda_hook} does not exist.")
    activate_str = f'"{conda_hook}" "{conda_hook}"'
    hive = _get_hive(user_or_system)
    registry = WinRegistry(hive)
    value, value_type = registry.get(AUTORUN_KEY, named_value=AUTORUN_NAMED_VALUE)
    autorun_commands = [v.strip() for v in value.split("&")] if value else []
    new_autorun_commands = []
    for autorun in autorun_commands:
        if activate_str.lower() in autorun_commands:
            return
        elif not autorun_regex.match(autorun):
            new_autorun_commands.append(autorun)
    new_autorun_commands.append(f"if exist {activate_str}")
    if new_autorun_commands != autorun_commands:
        registry.set(
            AUTORUN_KEY,
            named_value=AUTORUN_NAMED_VALUE,
            value=" & ".join(new_autorun_commands),
            value_type=winreg.REG_EXPAND_SZ if value_type < 0 else value_type,
        )


def _remove_from_autorun(
    prefix: Path,
    user_or_system: str,
) -> None:
    conda_hook = prefix / "condabin" / "conda_hook.bat"
    activate_str = f'if exist "{conda_hook}" "{conda_hook}"'.lower()
    hive = _get_hive(user_or_system)
    registry = WinRegistry(hive)
    value, value_type = registry.get(AUTORUN_KEY, named_value=AUTORUN_NAMED_VALUE)
    if not value:
        return
    autorun_commands = [v.strip().lower() for v in value.split("&")]
    ncommands = len(autorun_commands)
    for a, autorun in enumerate(autorun_commands):
        if activate_str in autorun:
            del autorun_commands[a]
            break
    if len(autorun_commands) < ncommands:
        registry.set(
            AUTORUN_KEY,
            named_value=AUTORUN_NAMED_VALUE,
            value="&".join(autorun_commands),
            value_type=value_type,
        )


def add_remove_autorun(
    prefix: Path,
    add: str | None = None,
    remove: str | None = None,
) -> None:
    if add is not None:
        _add_to_autorun(prefix, add)
    elif remove is not None:
        _remove_from_autorun(prefix, remove)
