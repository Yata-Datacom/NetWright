"""paths.py — 区分「只读资源」与「可写数据」的路径解析。

这是打包后最容易踩的坑：
  * **onefile** 把 `datas` 解压到 ``sys._MEIPASS``（临时目录），而 ``sys.executable``
    仍然是用户双击的那个 exe。如果模板/图标按 exe 同级目录找，打包后就找不到；
  * **可写数据**（设备清单、设置、审计、备份）却必须放在 exe 同级，
    否则用户每次升级都丢数据，或者写到临时目录里被清掉。

因此这里把两类路径显式分开：
  ``data_dir()``     可写数据 → exe 同级（源码运行则是仓库根）
  ``resource_dir()`` 只读资源 → 优先 exe 同级（允许用户自带模板），
                     其次 ``sys._MEIPASS``（打包内置），最后源码树
"""
from __future__ import annotations

import os
import sys


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def repo_root() -> str:
    """源码运行时的仓库根目录。"""
    return os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


def data_dir() -> str:
    """可写数据目录：打包后是 exe 所在目录，源码运行是仓库根。"""
    if is_frozen():
        return os.path.dirname(os.path.abspath(sys.executable))
    return repo_root()


def bundled_root() -> str | None:
    """PyInstaller 解压目录（onefile/onedir 都是 ``_MEIPASS``）。"""
    return getattr(sys, "_MEIPASS", None)


def resource_dir(name: str, prefer_local: bool = False) -> str:
    """只读资源目录（如 ``templates`` / ``assets``）。

    :param prefer_local: True 时优先 exe 同级目录（**模板**需要，用户可自带），
                         False 时优先打包内置（**图标**需要，避免旧 assets 盖住新图标）。

    查找顺序：
      1. ``sys._MEIPASS``（打包内置）或 exe 同级（取决于 prefer_local）
      2. 另一个
      3. 源码树（开发/测试）
    """
    local = os.path.join(data_dir(), name)
    meipass = bundled_root()
    bundled = os.path.join(meipass, name) if meipass else None
    candidates = [local, bundled] if prefer_local else [bundled, local]
    candidates = [c for c in candidates if c]
    candidates.append(os.path.join(repo_root(), name))
    for candidate in candidates:
        if os.path.isdir(candidate):
            return candidate
    return candidates[0]
