# -*- coding: utf-8 -*-
"""GUI 冒烟测试（多轮）：全页循环 ×2 + 各业务路径 + REST 生命周期。"""

from __future__ import annotations

from netforge.pages import PAGE_REGISTRY


def theme_current():
    from netforge.theme import theme
    return theme.name


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

def test_smoke_theme_switch_all_schemes(app):
    """主题系统：6 套配色逐个切换（界面整体重建），令牌与模式正确。"""
    from netforge.theme import THEMES

    for name, tokens in THEMES.items():
        app.apply_theme(name)
        assert theme_current() == name
        assert app.cget("bg") == tokens["bg"]
        # 重建后页面字典恢复，可继续切换
        assert len(app.pages) == len(PAGE_REGISTRY)


def test_smoke_theme_light_tokens(app):
    """亮色方案：切到亮色后 bg 为浅色（#f 开头）。"""
    app.apply_theme("晨曦蓝 · 亮")
    from netforge.theme import theme as t
    assert t.mode == "light" and t.bg.startswith("#f")
    app.apply_theme("深空蓝 · 暗")
    from netforge.theme import theme as t2
    assert t2.mode == "dark"


def test_smoke_settings_persistence(app, tmp_path):
    """设置持久化：主题/last_page 写盘并可回读。"""
    from netforge.lib.settings import load_settings, save_settings
    data = {"theme": "暮光紫 · 暗", "rest_port": 8899, "last_page": "cheat"}
    assert save_settings(data, str(tmp_path))
    loaded = load_settings(str(tmp_path))
    assert loaded["theme"] == "暮光紫 · 暗" and loaded["last_page"] == "cheat"


def test_smoke_inventory_alive_check(app, monkeypatch):
    """清单在线检测：mock ping，状态回填树表。"""
    from netforge.lib.inventory import Device

    app.inventory.devices = []
    app.inventory.add(Device(host="192.0.2.1", vendor="huawei", hostname="A"))
    app.inventory.add(Device(host="192.0.2.2", vendor="cisco", hostname="B"))

    import netforge.pages.inventory as inv_page
    calls = {"n": 0}

    class FakePing:
        def __init__(self, alive):
            self.alive = alive

    def fake_ping(host, timeout_ms=800):
        calls["n"] += 1
        return FakePing(host == "192.0.2.1")

    monkeypatch.setattr(inv_page.portscan, "ping_host", fake_ping)
    page = app.pages["inventory"]
    page.alive_check()
    # worker 是线程（无 mainloop）：轮询结果后手动触发刷新
    import time
    for _ in range(60):
        if calls["n"] >= 2 and all(d._alive is not None
                                   for d in app.inventory.devices):
            break
        time.sleep(0.1)
    page.refresh()
    assert page.tree.set("0", "alive") == "在线"
    assert page.tree.set("1", "alive") == "离线"


def test_smoke_controller_audit_viewer(app):
    """控制器审计查看：写入审计后刷新展示。"""
    from netforge.lib.controller import deploy

    deploy._audit({"action": "intent.apply", "intent": "vlan_deploy",
                   "device": "192.0.2.1", "status": "OK"})
    page = app.pages["controller"]
    page.refresh_audit()
    text = page.audit_text.get("1.0", "end")
    assert "intent.apply" in text
