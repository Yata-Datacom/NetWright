# -*- coding: utf-8 -*-
"""GUI 冒烟测试：完整构建主窗口（不进入 mainloop），抓启动期崩溃。"""

from __future__ import annotations

import os
import sys

import pytest

pytest.importorskip("tkinter")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


def test_app_builds_all_pages():
    import netforge

    app = netforge.NetForgeApp()
    try:
        app.withdraw()
        # 六个工作区全部构建成功且可切换
        for key in netforge.NetForgeApp.PAGES:
            app.show(key[0])
        # 生成页模板下拉已填充
        gen_page = app.pages["generate"]
        assert gen_page.all_templates, "模板库为空"
        assert gen_page.cmb_tpl["values"], "生成页模板下拉未填充"
        # 巡检页方案下拉覆盖 8 套
        insp = app.pages["inspect"]
        assert len(insp.cmb_scheme["values"]) >= 8
    finally:
        app.destroy()
