"""GUI 冒烟共享夹具：单 App 实例 + 数据目录隔离（不污染仓库）。"""
from __future__ import annotations

import os
import sys

import tkinter as tk

import pytest

pytest.importorskip("tkinter")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)


@pytest.fixture(scope="module")
def app():
    """模块级单实例：构建一次主窗口，所有冒烟用例共用（避免反复创建 Tk）。

    无显示环境（如 Linux CI 无 X server）自动跳过整个模块。
    """
    try:
        from netwright.app import NetWrightApp
    except tk.TclError as e:
        pytest.skip(f"GUI 不可用（无显示环境）: {e}")
    try:
        app = NetWrightApp()
    except tk.TclError as e:
        pytest.skip(f"GUI 不可用（无显示环境）: {e}")
    app.withdraw()
    yield app
    app.destroy()


@pytest.fixture(autouse=True)
def isolated_data(tmp_path, monkeypatch):
    """把清单/审计等数据目录重定向到 tmp，保证用例互不影响、不写仓库。"""
    monkeypatch.setattr("netwright.lib.inventory._base_dir", lambda: str(tmp_path))
    monkeypatch.setattr("netwright.lib.controller.deploy._base_dir", lambda: str(tmp_path))
