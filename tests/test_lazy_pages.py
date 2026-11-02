"""R11 的 TDD 骨架：页面惰性构建。

**实现前整文件 skip**（基线保持 227 passed / 1 skipped）；实现
`NetWrightApp._ensure_page` 与 `LazyPages` 后自动生效，必须全过。

契约见 docs/DEV_SPEC_3.19.md 的 R11：
- 新建 app 只构建当前页（<= 2 个）
- show 某页只多构建一个，且重复 show 返回同一对象
- apply_theme 只重建已构建的页面
- 全部 show 一遍后页面数 == PAGE_REGISTRY 数量
"""
from __future__ import annotations

import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from netwright.app import NetWrightApp
from netwright.pages import PAGE_REGISTRY

if not hasattr(NetWrightApp, "_ensure_page"):
    pytest.skip("R11 尚未实现 _ensure_page / LazyPages（TDD 骨架，实现后自动生效）",
                allow_module_level=True)


@pytest.fixture()
def app2():
    try:
        instance = NetWrightApp()
    except Exception as exc:      # noqa: BLE001  Tk 不可用时跳过
        pytest.skip(f"GUI 不可用：{exc}")
    instance.withdraw()
    yield instance
    try:
        instance.controller_api.stop()
    except Exception:             # noqa: BLE001
        pass
    try:
        instance.destroy()
    except Exception:             # noqa: BLE001
        pass


def test_construct_builds_only_current_page(app2):
    """冷启动不应把 12 个页面全建出来。"""
    assert len(app2.pages) <= 2, f"启动就建了 {len(app2.pages)} 个页面"
    assert len(app2.pages) < len(PAGE_REGISTRY)


def test_show_builds_exactly_one_new_page(app2):
    before = len(app2.pages)
    app2.show("topology")
    assert "topology" in app2.pages
    assert len(app2.pages) == before + 1


def test_repeated_show_reuses_same_page_object(app2):
    app2.show("inventory")
    page = app2.pages["inventory"]
    app2.show("dashboard")
    app2.show("inventory")
    assert app2.pages["inventory"] is page, "重复进入不应重建页面"


def test_apply_theme_rebuilds_only_visited_pages(app2):
    app2.show("dashboard")
    app2.show("topology")
    visited = set(app2.pages)
    app2.apply_theme("light", "蓝")
    assert set(app2.pages) <= visited | set(PAGE_REGISTRY), "出现未知页面"
    assert len(app2.pages) <= len(visited) + 1
    app2.show("topology")
    assert "topology" in app2.pages


def test_visiting_all_pages_builds_all(app2):
    for key in PAGE_REGISTRY:
        app2.show(key)
    assert len(app2.pages) == len(PAGE_REGISTRY)
