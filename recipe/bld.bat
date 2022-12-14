@ECHO on

RENAME "%SP_DIR%\conda\core\path_actions.py" path_actions.py.bak || goto :error
COPY conda_src\conda\core\path_actions.py "%SP_DIR%\conda\core\path_actions.py" || goto :error
RENAME "%SP_DIR%\conda\utils.py" "%SP_DIR%\conda\utils.py.bak" || goto :error
COPY conda_src\conda\utils.py "%SP_DIR%\conda\utils.py" || goto :error

:: we need these for noarch packages with entry points to work on windows
COPY "conda_src\conda\shell\cli-%ARCH%.exe" entry_point_base.exe || goto :error

:: This is ordinarily installed by the installer itself, but since we are building for a
:: standalone and have only an env, not an installation, include it here.
COPY constructor\constructor\nsis\_nsis.py "%PREFIX%\Lib\_nsis.py" || goto :error

cd src
pyinstaller conda.exe.spec || goto :error
MKDIR "%PREFIX%\standalone_conda" || goto :error
MOVE dist\conda.exe "%PREFIX%\standalone_conda\conda.exe" || goto :error

RD /s /q "%PREFIX%\lib" || goto :error

goto :EOF

:error
set "exitcode=%errorlevel%"
echo Failed with error #%exitcode%.
exit /b %exitcode%
