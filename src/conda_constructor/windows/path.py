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

    This must be called after using the other functions in this module to
    manipulate environment variables.
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
    for p, test_path in enumerate(paths):
        if value_type == winreg.REG_EXPAND_SZ:
            test_path = winreg.ExpandEnvironmentStrings(test_path)
        if Path(test_path) == prefix:
            return p
    return -1


def _add_to_path(prefix: Path, user_or_system: str) -> None:
    hive, key = _get_path_hive_key(user_or_system)
    registry = WinRegistry(hive)
    reg_value, value_type = registry.get(key, "Path")
    paths = reg_value.split(os.pathsep) if reg_value else []
    if _find_in_path(prefix, paths, value_type) >= 0:
        return
    paths = [str(prefix), *paths]
    if value_type == -1:
        value_type = winreg.REG_EXPAND_SZ
    registry.set(key, named_value="Path", value=os.pathsep.join(paths), value_type=value_type)
    _broadcast_environment_settings_change()


def _remove_from_path(prefix: Path, user_or_system: str) -> None:
    hive, key = _get_path_hive_key(user_or_system)
    registry = WinRegistry(hive)
    reg_value, value_type = registry.get(key, "Path")
    if not reg_value:
        return
    paths = reg_value.split(os.pathsep)
    p = _find_in_path(prefix, paths, value_type)
    if p == -1:
        return
    del paths[p]
    registry.set(key, named_value="Path", value=os.pathsep.join(paths), value_type=value_type)
    _broadcast_environment_settings_change()


def add_remove_path(prefix: Path, add: str | None = None, remove: str | None = None) -> None:
    if add is not None:
        _add_to_path(prefix, add)
    elif remove is not None:
        _remove_from_path(prefix, remove)
