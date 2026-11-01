# -*- coding: utf-8 -*-
"""GUI 冒烟测试（多轮）：全页循环 ×2 + 各业务路径 + REST 生命周期。"""

from __future__ import annotations

import os

from netwright.pages import PAGE_REGISTRY


from netwright.theme import theme


def theme_current():
    from netwright.theme import theme
    return theme.mode


def test_smoke_pass1_all_pages_cycle(app):
    """第 1 轮：七个工作区逐个进入（选中态必须跟随切换）。"""
    for key in PAGE_REGISTRY:
        app.show(key)
        assert app._active_key == key, f"高亮未跟随切换: {key}"


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
    from netwright.lib.inventory import Device

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
    """主题冒烟：明暗双模式 + 4 主色逐个切换（界面重建不崩）。"""
    for mode in ("light", "dark"):
        for hue in ("蓝", "绿", "紫", "橙"):
            app.apply_theme(mode, hue)
            assert theme_current() == mode
    for key in PAGE_REGISTRY:
        app.show(key)


def test_smoke_theme_switch_no_layout_leak(app):
    """回归：多次切换配色后，根级框架数量恒定（旧 main 不残留 → 页面不下沉）。"""
    before = len(app.winfo_children())
    for _ in range(3):
        app.apply_theme("晴空 · 亮")
        app.apply_theme("深空蓝 · 暗")
    after = len(app.winfo_children())
    assert before == after, f"根级框架泄漏: {before} → {after}"


def test_smoke_theme_light_tokens(app):
    """亮色方案：切到亮色后 bg 为浅色（#f 开头）。"""
    app.apply_theme("light", "蓝")
    from netwright.theme import theme as t
    assert t.mode == "light" and t.bg == "#F5F7FA" and t.accent == "#2570F2"
    app.apply_theme("dark", "蓝")
    from netwright.theme import theme as t2
    assert t2.mode == "dark"


def test_smoke_settings_persistence(app, tmp_path):
    """设置持久化：主题/last_page 写盘并可回读。"""
    from netwright.lib.settings import load_settings, save_settings
    data = {"theme": "暮光紫 · 暗", "rest_port": 8899, "last_page": "cheat"}
    assert save_settings(data, str(tmp_path))
    loaded = load_settings(str(tmp_path))
    assert loaded["theme"] == "暮光紫 · 暗" and loaded["last_page"] == "cheat"


def test_smoke_inventory_alive_check(app, monkeypatch):
    """清单在线检测：mock ping，状态回填树表。"""
    from netwright.lib.inventory import Device

    app.inventory.devices = []
    app.inventory.add(Device(host="192.0.2.1", vendor="huawei", hostname="A"))
    app.inventory.add(Device(host="192.0.2.2", vendor="cisco", hostname="B"))

    import netwright.pages.inventory as inv_page
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
    assert "在线" in page.tree.set("0", "alive")
    assert "离线" in page.tree.set("1", "alive")


def test_smoke_controller_audit_viewer(app):
    """控制器审计查看：写入审计后刷新展示。"""
    from netwright.lib.controller import deploy

    deploy._audit({"action": "intent.apply", "intent": "vlan_deploy",
                   "device": "192.0.2.1", "status": "OK"})
    page = app.pages["controller"]
    page.refresh_audit()
    text = page.audit_text.get("1.0", "end")
    assert "intent.apply" in text

def test_header_contrast_all_themes():
    """可读性回归（扁平顶栏）：明暗两模式下 fg/header1 与 white/accent_deep ≥ 4.5:1。"""

    def luminance(hex_color: str) -> float:
        r, g, b = (int(hex_color[i:i+2], 16) / 255 for i in (1, 3, 5))
        lin = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
               for c in (r, g, b)]
        return 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]

    def contrast(a: str, b: str) -> float:
        la, lb = luminance(a), luminance(b)
        hi, lo = max(la, lb), min(la, lb)
        return (hi + 0.05) / (lo + 0.05)

    from netwright.theme import Theme
    for mode in ("light", "dark"):
        tokens = Theme(mode).tokens
        ratio_top = contrast(tokens["fg"], tokens["header1"])
        assert ratio_top >= 4.5, f"{mode} 顶栏文字对比度 {ratio_top:.2f} < 4.5"
        ratio_deep = contrast("#ffffff", tokens["accent_deep"])
        assert ratio_deep >= 4.5, f"{mode}/accent_deep 白字对比度 {ratio_deep:.2f} < 4.5"


def test_smoke_wbutton_press_feedback(app):
    """按钮反馈逻辑：hover/press 色预计算正确、_feedback 生效、绑定已注册。"""
    from netwright.widgets import WButton

    btn = WButton(app, text="测试", bg=theme.accent)
    normal = btn.cget("bg")
    assert btn._c_hover != normal and btn._c_press != normal
    assert btn._c_press != btn._c_hover
    assert btn.bind("<ButtonPress-1>") and btn.bind("<Enter>") and btn.bind("<Leave>")
    # 状态机：_feedback 真实改变底色，Leave 恢复
    btn._feedback(btn._c_press, btn._fg_press)
    assert btn.cget("bg") == btn._c_press
    btn._feedback(btn._c_normal, btn._fg_normal)
    assert btn.cget("bg") == normal
    btn.destroy()


def test_smoke_wbutton_ghost_press(app):
    """ghost 按钮同样具备按压反馈逻辑与绑定。"""
    from netwright.widgets import WButton

    btn = WButton(app, text="ghost")
    normal = btn.cget("bg")
    assert btn._c_hover != normal and btn._c_press != normal
    assert btn.bind("<ButtonPress-1>")
    btn._feedback(btn._c_press, btn._fg_press)
    assert btn.cget("bg") == btn._c_press
    btn._feedback(btn._c_normal, btn._fg_normal)
    btn.destroy()


def test_smoke_export_all_templates(app, tmp_path):
    """批量模板导出：116 个 .cfg 按目录结构落盘。"""
    from netwright.lib import generator as gen

    out = tmp_path / "tpl-export"
    tpls = gen.list_builtin_templates()
    for t in tpls:
        rel = t["file"].replace("/", os.sep)
        dest = out / "templates" / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(t["text"], encoding="utf-8")
    cfgs = list(out.rglob("*.cfg"))
    assert len(cfgs) >= 105
    assert (out / "templates" / "cli" / "vxlan_evpn" / "huawei.cfg").is_file()
