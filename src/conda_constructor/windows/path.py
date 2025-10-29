import ctypes
import os
import winreg
from ctypes import wintypes
from pathlib import Path

from .registry import WinRegistry

HWND_BROADCAST = 0xFFFF
WM_SETTINGCHANGE = 0x001A
SMTO_ABORTIFHUNG = 0x0002
SendMessageTimeout = ctypes.windll.user32.SendMessageTimeoutW
SendMessageTimeout.restype = None
SendMessageTimeout.argtypes = [
    wintypes.HWND,
    wintypes.UINT,
    wintypes.WPARAM,
    wintypes.LPCWSTR,
    wintypes.UINT,
    wintypes.UINT,
    ctypes.POINTER(wintypes.DWORD),
]


def _broadcast_environment_settings_change() -> None:
    """Broadcasts to the system indicating that master environment variables have changed.

    This must be called at the end of any function that changes environment variables.
    """
    result = SendMessageTimeout(
        HWND_BROADCAST,
        WM_SETTINGCHANGE,
        0,
        "Environment",
        SMTO_ABORTIFHUNG,
        5000,
        ctypes.pointer(wintypes.DWORD()),
    )
    if result == 0:
        error = ctypes.windll.kernel32.GetLastError()
        raise RuntimeError(f"Could not broadcast environment change: {error}")


def _get_path_hive_key(user_or_system: str) -> tuple[int, str]:
    """Return the registry hive and key path for user and system-wide environment variables."""
    if user_or_system == "user":
        hive = winreg.HKEY_CURRENT_USER
        key = "Environment"
    elif user_or_system == "system":
        hive = winreg.HKEY_LOCAL_MACHINE
        key = r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment"
    else:
        raise ValueError(f"Invalid value: {user_or_system}. Must be `user` or `system`.")
    return hive, key


def _find_in_path(prefix: Path, paths: list[str], value_type: int) -> int:
    """Find the index of a path inside a list of paths from the registry."""
    for p, test_path in enumerate(paths):
        if value_type == winreg.REG_EXPAND_SZ:
            test_path = winreg.ExpandEnvironmentStrings(test_path)
        if Path(test_path) == prefix:
            return p
    return -1


def _add_to_path(prefixes: Iterable[Path], user_or_system: Literal["user", "system"], append: bool) -> None:
    """Append or prepend a prefix to the PATH environment variable.

    If the prefix already exists in PATH, move the prefix to the beginning/end of PATH.

    """
    hive, key = _get_path_hive_key(user_or_system)
    registry = WinRegistry(hive)
    reg_value, value_type = registry.get(key, "Path")
    paths = reg_value.split(os.pathsep) if reg_value else []
    for prefix in prefixes:
        p = _find_in_path(prefix, paths, value_type)
        if p >= 0:
            del paths[p]
        if append:
            paths = [*paths, str(prefix)]
        else:
            paths = [str(prefix), *paths]
        if value_type == -1:
            value_type = winreg.REG_EXPAND_SZ
    registry.set(key, named_value="Path", value=os.pathsep.join(paths), value_type=value_type)
    _broadcast_environment_settings_change()


def _remove_from_path(prefixes: list[Path], user_or_system: Literal["user", "system"]) -> None:
    """Remove a prefix to the PATH environment variable."""
    hive, key = _get_path_hive_key(user_or_system)
    registry = WinRegistry(hive)
    reg_value, value_type = registry.get(key, "Path")
    if not reg_value:
        return
    paths = reg_value.split(os.pathsep)
    for prefix in prefixes:
        p = _find_in_path(prefix, paths, value_type)
        if p == -1:
            return
        del paths[p]
    registry.set(key, named_value="Path", value=os.pathsep.join(paths), value_type=value_type)
    _broadcast_environment_settings_change()


def add_remove_path(
    prefix: Path,
    add: str | None = None,
    remove: str | None = None,
    append: bool = False,
    condabin: bool = False,
    classic: bool = False,
) -> None:
    """Entry point for manipulating the PATH environment variable."""
    if condabin:
        prefixes = [prefix / "condabin"]
    elif condalibs:
        prefixes = [
            prefix,
            prefix / "Library" / "mingw-w64" / "bin",
            prefix / "Library" / "usr" / "bin",
            prefix / "Library" / "bin",
            prefix / "Scripts",
        ]
    else:
        prefixes = [prefix]
    if add is not None:
        _add_to_path(prefixes, add, append)
    elif remove is not None:
        _remove_from_path(prefixes, remove)
