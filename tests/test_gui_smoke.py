# -*- coding: utf-8 -*-
"""GUI 冒烟测试（多轮）：全页循环 ×2 + 各业务路径 + REST 生命周期。"""

from __future__ import annotations

from netforge.pages import PAGE_REGISTRY


def test_smoke_pass1_all_pages_cycle(app):
    """第 1 轮：七个工作区逐个进入。"""
    for key in PAGE_REGISTRY:
        app.show(key)


def test_smoke_pass2_all_pages_cycle_again(app):
    """第 2 轮：再进一轮（验证可重复进入、无状态残留崩溃）。"""
    for key in reversed(list(PAGE_REGISTRY)):
        app.show(key)


def test_smoke_generate_page_templates_and_filter(app):
    """生成页：模板下拉已填充、厂商过滤联动。"""
    page = app.pages["generate"]
    assert len(page.all_templates) >= 105
    assert len(page.cmb_tpl["values"]) == len(page.tpl_map)
    page.cmb_vendor.set("华为")
    page._apply_vendor_filter()
    assert page.tpl_map and all(t["vendor"] == "huawei" for t in page.tpl_map.values())
    page.cmb_vendor.set("全部")
    page._apply_vendor_filter()
    assert len(page.tpl_map) >= 105


def test_smoke_inspect_page_schemes(app):
    """巡检页：9 套方案可选，切换到高级方案不崩。"""
    page = app.pages["inspect"]
    assert len(page.cmb_scheme["values"]) >= 9
    for name in ("VXLAN+EVPN", "MPLS/SR 骨干", "堆叠与M-LAG", "RoCEv2 无损", "IPv6 与过渡"):
        page.cmb_scheme.set(name)


def test_smoke_toolbox_subnet_and_password(app):
    """工具箱：子网计算与密码生成真实执行。"""
    page = app.pages["toolbox"]
    page.ent.delete(0, "end")
    page.ent.insert(0, "10.0.0.0/8")
    page.calc()
    assert "10.0.0.0" in page.out.get("1.0", "end")
    page.w_len.delete(0, "end")
    page.w_len.insert(0, "20")
    page.gen_pwd()
    assert len(page.w_out.get()) == 20


def test_smoke_controller_dry_run(app):
    """控制器：意图 Dry-Run 渲染预览（先加设备，不连任何真实主机）。"""
    from netforge.lib.inventory import Device

    app.inventory.devices = []
    app.inventory.add(Device(host="192.0.2.1", vendor="huawei", hostname="A"))
    page = app.pages["controller"]
    page.nb.select(1)
    page._render_fields()
    page.cmb_target.current(1)
    page.field_vars["vlans"].set("10,20")     # 填必填参数，避免 UI 警告框阻塞
    page.dry_run()
    text = page.preview.get("1.0", "end")
    assert "Dry-Run" in text and "vlan batch" in text


def test_smoke_rest_api_lifecycle(app):
    """REST 北向：启动 → /api/health → 停止。"""
    import json
    import urllib.request

    api = app.controller_api
    api.port = 0  # 随机端口
    api.host = "127.0.0.1"
    api.stop()
    api.start()
    assert api.running
    url = f"http://127.0.0.1:{api._server.server_address[1]}/api/health"
    with urllib.request.urlopen(url, timeout=5) as r:
        assert json.loads(r.read().decode())["ok"] is True
    api.stop()
    assert not api.running
