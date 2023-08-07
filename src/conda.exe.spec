# -*- mode: python ; coding: utf-8 -*-
import os
import sys

for arg in sys.argv:
    if arg.endswith("conda.exe.spec"):
        HERE = os.path.abspath(os.path.dirname(arg))
        break
else:
    HERE = os.path.join(os.path.getcwd(), "src")

block_cipher = None

extra_exe_kwargs = {}
datas = []
if sys.platform == "win32":
    datas = [(os.path.join(os.getcwd(), 'constructor_src', 'constructor', 'nsis', '_nsis.py'), 'Lib'),
             (os.path.join(os.getcwd(), 'entry_point_base.exe'), '.')]
elif sys.platform == "darwin":
    extra_exe_kwargs["entitlements_file"] = os.path.join(HERE, "entitlements.plist")

a = Analysis(['entry_point.py', 'imports.py'],
             pathex=['.'],
             binaries=[],
             datas=datas,
             hiddenimports=['pkg_resources.py2_warn'],
             hookspath=[],
             runtime_hooks=[],
             excludes=['test'],
             win_no_prefer_redirects=False,
             win_private_assemblies=False,
             cipher=block_cipher,
             noarchive=False)
pyz = PYZ(a.pure, a.zipped_data,
             cipher=block_cipher)
exe = EXE(pyz,
          a.scripts,
          a.binaries,
          a.zipfiles,
          a.datas,
          [],
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
