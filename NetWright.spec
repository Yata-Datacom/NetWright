# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['main.py'],
    pathex=['src'],
    binaries=[],
    datas=[('assets', 'assets'), ('templates', 'templates')],
    hiddenimports=['netwright.lib.ssh_client'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
# 裁掉用不到的 PIL AVIF 插件（约 7.7 MB）：界面只需要 PNG/ICO 预览
a.binaries = [b for b in a.binaries if "avif" not in b[0].lower()]

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='NetWright',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,            # UPX 拖慢启动且易被杀软误报（v3.18.2）
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['assets/icon.ico'],
)
