# -*- mode: python ; coding: utf-8 -*-
import os
import site
import sys

import conda.plugins.manager
from menuinst.platforms.base import SCHEMA_VERSION
from PyInstaller.utils.hooks import collect_data_files, collect_submodules, copy_metadata

from PyInstaller.utils.hooks import collect_submodules, copy_metadata

# __file__ is not defined in the pyinstaller context,
# so we will get it from sys.argv instead
for arg in sys.argv:
    if arg.endswith("conda.exe.spec"):
        HERE = os.path.abspath(os.path.dirname(arg))
        break
else:
    HERE = os.path.join(os.path.getcwd(), "src")

block_cipher = None
sitepackages = os.environ.get(
    "SP_DIR",  # site-packages in conda-build's host environment
    # if not defined, get running Python's site-packages
    # Windows puts sys.prefix in this list first
    next(
        path for path in site.getsitepackages()
        if path.endswith("site-packages")
    )
)

extra_exe_kwargs = {}
# Non imported files need to be added manually via datas or binaries:
# Datas are not analyzed, just copied over. Binaries go through some
# linkage analysis to also bring necessary libs. This includes plain
# text files like JSON, modules never imported, or standalone binaries
# Shared objects and DLLs should have been caught by pyinstaller import hooks,
# but if not, add them.
# Format: a list of tuples like (file-path, target-DIRECTORY)
binaries = []
datas = [
    # put a dummy file in archspec/cpu so directory is created and relative paths can be resolved at runtime
    (os.path.join(sitepackages, 'archspec', 'json', 'COPYRIGHT'), 'archspec/cpu'),
    (os.path.join(sitepackages, 'archspec', 'json', 'COPYRIGHT'), 'archspec/json'),
    (os.path.join(sitepackages, 'archspec', 'json', 'NOTICE'), 'archspec/json'),
    (os.path.join(sitepackages, 'archspec', 'json', 'NOTICE'), 'archspec/json'),
    (os.path.join(sitepackages, 'archspec', 'json', 'LICENSE-APACHE'), 'archspec/json'),
    (os.path.join(sitepackages, 'archspec', 'json', 'LICENSE-MIT'), 'archspec/json'),
    (os.path.join(sitepackages, 'archspec', 'json', 'cpu', 'cpuid.json'), 'archspec/json/cpu'),
    (os.path.join(sitepackages, 'archspec', 'json', 'cpu', 'cpuid_schema.json'), 'archspec/json/cpu'),
    (os.path.join(sitepackages, 'archspec', 'json', 'cpu', 'microarchitectures.json'), 'archspec/json/cpu'),
    (os.path.join(sitepackages, 'archspec', 'json', 'cpu', 'microarchitectures_schema.json'), 'archspec/json/cpu'),
    (os.path.join(sitepackages, 'archspec', 'vendor', 'cpuid', 'LICENSE'), 'archspec/vendor/cpuid'),
    (os.path.join(sitepackages, 'conda', 'shell', 'bin', 'activate'), 'conda/shell/bin'),
    (os.path.join(sitepackages, 'conda', 'shell', 'bin', 'deactivate'), 'conda/shell/bin'),
    (os.path.join(sitepackages, 'conda', 'shell', 'conda.xsh'), 'conda/shell'),
    (os.path.join(sitepackages, 'conda', 'shell', 'condabin', 'conda-hook.ps1'), 'conda/shell/condabin'),
    (os.path.join(sitepackages, 'conda', 'shell', 'condabin', 'Conda.psm1'), 'conda/shell/condabin'),
    (os.path.join(sitepackages, 'conda', 'shell', 'etc', 'fish', 'conf.d', 'conda.fish'), 'conda/shell/etc/fish/conf.d'),
    (os.path.join(sitepackages, 'conda', 'shell', 'etc', 'profile.d', 'conda.csh'), 'conda/shell/etc/profile.d'),
    (os.path.join(sitepackages, 'conda', 'shell', 'etc', 'profile.d', 'conda.sh'), 'conda/shell/etc/profile.d'),
]
if sys.platform == "win32":
    datas += [
        (os.path.join(os.getcwd(), 'entry_point_base.exe'), '.'),
        (os.path.join(sitepackages, 'conda', 'shell', 'cli-32.exe'), 'conda/shell'),
        (os.path.join(sitepackages, 'conda', 'shell', 'cli-64.exe'), 'conda/shell'),
        (os.path.join(sitepackages, 'conda', 'shell', 'conda_icon.ico'), 'conda/shell'),
        (os.path.join(sitepackages, 'conda', 'shell', 'condabin', '_conda_activate.bat'), 'conda/shell/condabin'),
        (os.path.join(sitepackages, 'conda', 'shell', 'condabin', 'activate.bat'), 'conda/shell/condabin'),
        (os.path.join(sitepackages, 'conda', 'shell', 'condabin', 'conda_auto_activate.bat'), 'conda/shell/condabin'),
        (os.path.join(sitepackages, 'conda', 'shell', 'condabin', 'conda_hook.bat'), 'conda/shell/condabin'),
        (os.path.join(sitepackages, 'conda', 'shell', 'condabin', 'deactivate.bat'), 'conda/shell/condabin'),
        (os.path.join(sitepackages, 'conda', 'shell', 'condabin', 'rename_tmp.bat'), 'conda/shell/condabin'),
        (os.path.join(sitepackages, 'conda', 'shell', 'condabin', 'conda.bat'), 'conda/shell/condabin'),
        (os.path.join(sitepackages, 'conda', 'shell', 'Library', 'bin', 'conda.bat'), 'conda/shell/Library/bin'),
        (os.path.join(sitepackages, 'conda', 'shell', 'Scripts', 'activate.bat'), 'conda/shell/Scripts'),
    ]
elif sys.platform == "darwin":
    datas += [
        (os.path.join(sitepackages, 'menuinst', 'data', 'osx_launcher_arm64'), 'menuinst/data'),
        (os.path.join(sitepackages, 'menuinst', 'data', 'osx_launcher_x86_64'), 'menuinst/data'),
        (os.path.join(sitepackages, 'menuinst', 'data', 'appkit_launcher_arm64'), 'menuinst/data'),
        (os.path.join(sitepackages, 'menuinst', 'data', 'appkit_launcher_x86_64'), 'menuinst/data'),
    ]
    extra_exe_kwargs["entitlements_file"] = os.path.join(HERE, "entitlements.plist")

hiddenimports = []
packages = [
    "conda",
    "conda_package_handling",
    "conda_package_streaming",
    "menuinst",
    "conda_env",
    "libmambapy",
]
for package in packages:
    # collect_submodules does not look at __init__
    hiddenimports.append(f"{package}.__init__")
    hiddenimports.extend(collect_submodules(package))

# Add .condarc file to bundle to configure channels
# during the package building stage
if "PYINSTALLER_CONDARC_DIR" in os.environ:
    condarc = os.path.join(os.environ["PYINSTALLER_CONDARC_DIR"], ".condarc")
    if os.path.exists(condarc):
        datas.append((condarc, "."))

# Add external conda plug-ins
conda_plugin_manager = conda.plugins.manager.get_plugin_manager()
for name, module in conda_plugin_manager.list_name_plugin():
    if not hasattr(module, "__name__"):
        print(f"WARNING: could not load plug-in {name}: not a module.", file=sys.stderr)
        continue
    # conda plug-ins are already loaded with conda
    if module.__name__.startswith("conda."):
        continue
    package_name = module.__name__.split(".")[0]
    hiddenimports.extend(collect_submodules(package_name))
    # collect_submodules does not look at __init__
    hiddenimports.append(f"{package_name}.__init__")
    datas.extend(collect_data_files(package_name))
    # metadata is needed for conda to find the plug-in
    datas.extend(copy_metadata(package_name))

a = Analysis(['entry_point.py'],
             pathex=['.'],
             binaries=binaries,
             datas=datas,
             hiddenimports=hiddenimports,
             hookspath=[],
             runtime_hooks=[],
             excludes=['test', 'pkg_resources'],
             win_no_prefer_redirects=False,
             win_private_assemblies=False,
             cipher=block_cipher,
             noarchive=False)
pyz = PYZ(a.pure, a.zipped_data,
             cipher=block_cipher)

if os.environ.get("variant", "") == "onedir":
    variant_args = ()
    extra_exe_kwargs["exclude_binaries"] = True
else:
    variant_args = (a.binaries, a.zipfiles, a.datas, [])

exe = EXE(pyz,
          a.scripts,
          *variant_args,
          name='conda.exe',
          icon=os.path.join(HERE, "icon.ico"),
          debug=False,
          bootloader_ignore_signals=False,
          strip=(sys.platform!="win32"),
          upx=True,
          upx_exclude=[],
          runtime_tmpdir=None,
          console=True,
          **extra_exe_kwargs)

if os.environ.get("variant", "") == "onedir":

    coll = COLLECT(exe,
               a.binaries,
               a.zipfiles,
               a.datas,
               strip=(sys.platform!="win32"),
               upx=True,
               name='conda.exe')
