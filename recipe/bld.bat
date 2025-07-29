@ECHO on

RENAME "%SP_DIR%\conda\core\path_actions.py" path_actions.py.bak || goto :error
COPY conda_src\conda\core\path_actions.py "%SP_DIR%\conda\core\path_actions.py" || goto :error
RENAME "%SP_DIR%\conda\utils.py" utils.py.bak || goto :error
COPY conda_src\conda\utils.py "%SP_DIR%\conda\utils.py" || goto :error
RENAME "%SP_DIR%\conda\deprecations.py" deprecations.py.bak || goto :error
COPY conda_src\conda\deprecations.py "%SP_DIR%\conda\deprecations.py" || goto :error
RENAME "%SP_DIR%\conda\base\constants.py" constants.py.bak || goto :error
COPY conda_src\conda\base\constants.py "%SP_DIR%\conda\base\constants.py" || goto :error

:: we need these for noarch packages with entry points to work on windows
COPY "conda_src\conda\shell\cli-%ARCH%.exe" entry_point_base.exe || goto :error

pyinstaller --clean --log-level=DEBUG src\conda.exe.spec || goto :error
set "variant=%variant%"
if "%variant%" == "onedir" (
  MKDIR "%PREFIX%"
) else (
  MKDIR "%PREFIX%\standalone_conda"
)
MOVE dist\conda.exe "%PREFIX%\standalone_conda" || goto :error

:: Collect licenses
%PYTHON% src\licenses.py ^
  --prefix "%BUILD_PREFIX%" ^
  --include-text ^
  --text-errors replace ^
  --output "%SRC_DIR%\3rd-party-licenses.json" || goto :error

RD /s /q "%PREFIX%\lib" || goto :error

goto :EOF

:error
set "exitcode=%errorlevel%"
echo Failed with error #%exitcode%.
exit /b %exitcode%
