import winreg
from pathlib import Path


class WinRegistry:
    """Helper class to manipulate the Windows registry."""

    _HIVE_NAME = {
        winreg.HKEY_LOCAL_MACHINE: "HKEY_LOCAL_MACHINE",
        winreg.HKEY_CURRENT_USER: "HKEY_CURRENT_USER",
        winreg.HKEY_CLASSES_ROOT: "HKEY_CLASSES_ROOT",
        winreg.HKEY_USERS: "HKEY_USERS",
        winreg.HKEY_CURRENT_CONFIG: "HKEY_CURRENT_CONFIG",
    }

    def __init__(self, hive: int):
        self._hive = hive
        self._hive_name = self._HIVE_NAME[self._hive]

    def set(
        self, key: str, named_value: str = "", value: str = "", value_type: int = winreg.REG_SZ
    ):
        """Set value to a registry key or named value.

        If they key does not exist, it will be created first.
        """
        try:
            winreg.CreateKey(self._hive, key)
            with winreg.OpenKey(self._hive, key, access=winreg.KEY_SET_VALUE) as regkey:
                winreg.SetValueEx(regkey, named_value, 0, value_type, value)
        except OSError as e:
            named_value_part = f" to named value `{named_value}`" if named_value else ""
            raise OSError(
                f"Failed to create set `{value}`{named_value_part} in `{self._hive_name}\\{key}`."
            ) from e

    def get(self, key: str, named_value: str = "") -> tuple[str | None, int]:
        """Retrieve the value of a key or named value from the registry.

        Returns None when the key has not been found or cannot be accessed.
        """
        try:
            with winreg.OpenKey(self._hive, key, access=winreg.KEY_QUERY_VALUE) as regkey:
                return winreg.QueryValueEx(regkey, named_value)
        except OSError:
            return None, -1

    def prune_prefix(self, prefix: Path, key: str, dry_run: bool = False) -> int:
        """Delete all the values from the specified registry key that starts with 'prefix'.
        If 'dry_run' is set to True, it prints each matching value instead of deleting.

        Returns an integer equal to the number of entries that matched the specified prefix.
        """

        # Test first that we can open it
        try:
            opened_key = winreg.OpenKey(self._hive, key, 0, winreg.KEY_READ)
        except OSError as e:
            raise OSError(f"Unable to open Registry at {self._hive_name}\\{key}") from e

        # Now iterate through the open key to find all matches to delete
        index = 0
        to_delete = []
        opened_key_as_str = f"{self._hive_name}\\{key}"
        with opened_key:
            prefix_as_str = str(prefix)
            while True:
                try:
                    name, _, _ = winreg.EnumValue(opened_key, index)
                    if name.startswith(prefix_as_str):
                        to_delete.append(name)
                    index += 1
                except OSError:
                    break

            # While the key is open, attempt to delete matching values
            for name in to_delete:
                if dry_run:
                    print(f"dry-run: winreg.DeleteValue({opened_key_as_str}, {name})")
                else:
                    try:
                        winreg.DeleteValue(opened_key, name)
                    except OSError as e:
                        raise OSError(
                            f"Failed to delete '{name}' from Registry at '{opened_key_as_str}'."
                        ) from e
        return len(to_delete)
