COPY conda_src\conda\core\path_actions.py "%SP_DIR%\conda\core\path_actions.py"
COPY conda_src\conda\utils.py "%SP_DIR%\conda\utils.py"

:: we need these for noarch packages with entry points to work on windows
COPY conda_src\conda\shell\cli-%ARCH%.exe entry_point_base.exe

:: This is ordinarily installed by the installer itself, but since we are building for a
:: standalone and have only an env, not an installation, include it here.
COPY constructor\constructor\nsis\_nsis.py "%PREFIX%\Lib\_nsis.py"

pyinstaller conda.exe.spec
MKDIR "%PREFIX%\standalone_conda"
MOVE dist\conda.exe "%PREFIX%\standalone_conda\conda.exe"

RD /s /q "%PREFIX%\lib"
