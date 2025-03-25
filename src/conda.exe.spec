# -*- mode: python ; coding: utf-8 -*-
import os
import site
import sys

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
    (os.path.join(sitepackages, 'menuinst', 'data', 'menuinst.default.json'), 'menuinst/data'),
    (os.path.join(sitepackages, 'menuinst', 'data', 'menuinst.schema.json'), 'menuinst/data'),
]
if sys.platform == "win32":
    datas += [
        (os.path.join(os.getcwd(), 'constructor_src', 'constructor', 'nsis', '_nsis.py'), 'Lib'),
        (os.path.join(os.getcwd(), 'entry_point_base.exe'), '.'),
    ]
elif sys.platform == "darwin":
    datas += [
        (os.path.join(sitepackages, 'menuinst', 'data', 'osx_launcher_arm64'), 'menuinst/data'),
        (os.path.join(sitepackages, 'menuinst', 'data', 'osx_launcher_x86_64'), 'menuinst/data'),
        (os.path.join(sitepackages, 'menuinst', 'data', 'appkit_launcher_arm64'), 'menuinst/data'),
        (os.path.join(sitepackages, 'menuinst', 'data', 'appkit_launcher_x86_64'), 'menuinst/data'),
    ]
    extra_exe_kwargs["entitlements_file"] = os.path.join(HERE, "entitlements.plist")

# Add .condarc file to bundle to configure channels
# during the package building stage
if "PYINSTALLER_CONDARC_DIR" in os.environ:
    condarc = os.path.join(os.environ["PYINSTALLER_CONDARC_DIR"], ".condarc")
    if os.path.exists(condarc):
        datas.append((condarc, "."))

a = Analysis(['entry_point.py', 'imports.py'],
             pathex=['.'],
             binaries=binaries,
             datas=datas,
             hookspath=[],
             runtime_hooks=[],
             excludes=['test'],
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
