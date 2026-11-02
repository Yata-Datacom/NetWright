"""GUI 冒烟共享夹具：单 App 实例 + 数据目录隔离（不污染仓库）。"""
from __future__ import annotations

import os
import sys
import time

import tkinter as tk

import pytest

pytest.importorskip("tkinter")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

# ── Windows 环境加固：Tcl/Tk 初始化重试 ──────────────────────────────
# 实测（2026-11-02，本机）：杀软实时扫描对 uv 版 Python 的 tcl/tk 库目录存在读竞态，
# 测试进程连续快速创建 Tk root 时小概率抛 "couldn't read file …/tk8.6/xxx.tcl:
# no such file or directory"（文件实际存在，是扫描窗口期的读取失败）。
# 在 Tk.__init__ 层做带退避的重试：竞态窗口过去后即可正常初始化；
# 若 Tcl/Tk 真的损坏，重试 5 次后仍会如实抛错，不会被掩盖。
_tk_init = tk.Tk.__init__


def _retried_tk_init(self, *args, **kwargs):
    for attempt in range(5):
        try:
            _tk_init(self, *args, **kwargs)
            return
        except tk.TclError:
            if attempt == 4:
                raise
            time.sleep(0.05 * (attempt + 1))


tk.Tk.__init__ = _retried_tk_init


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
    """把清单/审计/设置等数据目录重定向到 tmp，保证用例互不影响、不写仓库。

    app.BASE_DIR 一并重定向：NetWrightApp 的设置文件（last_page 等）落到 tmp，
    用例行为不随开发者本机的设置文件漂移（R11 的惰性构建断言依赖"冷启动落在
    dashboard"这一确定性）。
    """
    monkeypatch.setattr("netwright.lib.inventory._base_dir", lambda: str(tmp_path))
    monkeypatch.setattr("netwright.lib.controller.deploy._base_dir", lambda: str(tmp_path))
    monkeypatch.setattr("netwright.app.BASE_DIR", str(tmp_path))
