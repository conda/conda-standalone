import winreg


class WinRegistry:
    """Helper class to manipulate the Windows registry."""

    def __init__(self, hive: int):
        self._hive = hive

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
            hive_name = (
                "HKEY_CURRENT_USER"
                if self._hive == winreg.HKEY_CURRENT_USER
                else "HKEY_LOCAL_MACHINE"
            )
            named_value_part = f" to named value `{named_value}`" if named_value else ""
            raise OSError(
                f"Failed to create set `{value}`{named_value_part} in `{hive_name}\\{key}`."
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
