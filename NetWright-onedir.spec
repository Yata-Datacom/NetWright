# -*- mode: python ; coding: utf-8 -*-
"""onedir 打包（推荐）：启动比 onefile 快很多。

onefile 每次启动都要把 24 MB 解压到 %TEMP%，再叠加 UPX 解压 + 杀软扫描，
双击后要等 2-4 秒才出窗口——这就是"exe 卡卡"的主要来源。
onedir 只解压一次（构建时），平时启动直接读文件，通常 < 1 秒。

用法：
    pyinstaller NetWright-onedir.spec --noconfirm
产物：
    dist/NetWright/NetWright.exe   （整个 dist/NetWright 目录一起分发）

注意：CI 里的 build.yml 仍然用 onefile 的 NetWright.spec（发布单文件），
这个 spec 是给"自己用/公司内分发"的低延迟版本。
"""

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
    [],
    exclude_binaries=True,
    name='NetWright',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,              # UPX 会让启动更慢、还容易被杀软误报
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['assets/icon.ico'],
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name='NetWright',
)
