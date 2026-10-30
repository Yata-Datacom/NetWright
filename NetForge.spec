# -*- mode: python ; coding: utf-8 -*-
a = Analysis(
    ['netforge.py'],
    pathex=[],
    binaries=[],
    datas=[('assets', 'assets')],
    hiddenimports=[],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, a.binaries, a.datas, [],
    name='NetForge',
    icon='assets/icon.ico',
    console=False,
    runtime_tmpdir=None,
)
