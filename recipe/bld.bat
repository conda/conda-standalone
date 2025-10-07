@ECHO on

"%PYTHON%" "%RECIPE_DIR%\copy_patches.py" ^
  --patch-source "%SRC_DIR%\src\conda_patches" ^
  --site-packages "%SP_DIR%" ^
  --conda-source conda_src || goto :error

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
"%PYTHON%" src\licenses.py ^
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
