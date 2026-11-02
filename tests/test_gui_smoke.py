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
    """设置持久化：主题/last_page 写盘并可回读；旧 key 'theme' 自动迁移。"""
    from netwright.lib.settings import load_settings, save_settings
    data = {"theme_mode": "dark", "theme_hue": "紫", "last_page": "cheat"}
    assert save_settings(data, str(tmp_path))
    loaded = load_settings(str(tmp_path))
    assert loaded["theme_mode"] == "dark" and loaded["theme_hue"] == "紫"
    assert loaded["last_page"] == "cheat"
    # 旧版本遗留的 theme 字段 → 迁移成 theme_mode，且不再出现在结果里
    assert save_settings({"theme": "浅色 · 亮", "rest_port": 8899}, str(tmp_path))
    migrated = load_settings(str(tmp_path))
    assert "theme" not in migrated and migrated["theme_mode"] == "light"


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


def test_smoke_auto_refresh_toggle(app):
    """自动刷新：开/关都要能改状态并留下/取消定时任务；手动 F5 走同一入口。"""
    app.show("dashboard")
    assert app.refresh_current(silent=False) is True
    assert app.var_updated.get(), "刷新后应记录上次刷新时间"

    app.var_auto.set(False)
    app.toggle_auto_refresh()
    assert app.auto_refresh is False and app._auto_job is None

    app.var_auto.set(True)
    app.toggle_auto_refresh()
    assert app.auto_refresh is True and app._auto_job is not None


def test_smoke_lifecycle_runs_tab(app):
    """意图页 Dry-Run 会生成运行档案，运行档案页能列出并渲染详情。"""
    from netwright.lib.inventory import Device

    app.inventory.devices = []
    app.inventory.add(Device(host="192.0.2.1", vendor="huawei", hostname="A"))
    page = app.pages["controller"]
    page.nb.select(1)
    page._render_fields()
    page.cmb_target.current(1)
    page.field_vars["vlans"].set("10,20")
    page.dry_run()

    page.nb.select(3)          # 运行档案
    page._runs_refresh()
    children = page.runs_tree.get_children()
    assert children, "Dry-Run 应生成至少一条运行档案"
    page.runs_tree.selection_set(children[0])
    page._render_run_detail()
    detail = page.run_detail.get("1.0", "end")
    assert "状态历史" in detail and "已预演" in detail
    assert "undo vlan 10" in detail, "详情里应能看到反向命令"


def test_smoke_settings_page_save(app, tmp_path):
    """设置页：改端口/保留份数并保存，写入设置文件且不影响运行。"""
    from netwright.lib.settings import load_settings

    page = app.pages["settings"]
    old_base = app.base_dir
    app.base_dir = str(tmp_path)
    try:
        page.refresh()
        page.var_rest.set("8898")
        page.var_syslog.set("5514")
        page.var_trap.set("1163")
        page.var_keep.set("20")
        page.var_auto.set(True)
        page.save()
        data = load_settings(str(tmp_path))
        assert data["rest_port"] == 8898
        assert data["syslog_port"] == 5514 and data["trap_port"] == 1163
        assert data["backup_keep"] == 20
    finally:
        app.base_dir = old_base


def test_smoke_backup_history_dialog(app, tmp_path):
    """备份历史对话框：两份快照能直接看到 unified diff。"""
    from netwright.pages.inventory import BackupHistoryDialog
    from netwright.sdn.backup import ConfigBackup

    backup = ConfigBackup(str(tmp_path))
    backup.save("核心A", "sysname A\nvlan 10\n")
    backup.save("核心A", "sysname A\nvlan 10\nvlan 20\n")
    original = app.controller_store.backups
    app.controller_store.backups = backup
    try:
        dialog = BackupHistoryDialog(app, "核心A")
        text = dialog.diff_text.get("1.0", "end")
        assert "+vlan 20" in text
        assert dialog.listbox.size() == 2
        dialog.destroy()
    finally:
        app.controller_store.backups = original


def test_smoke_inventory_refresh_skips_when_unchanged(app):
    """性能回归：设备没变化时，10 秒自动刷新不应重建整棵表格。"""
    from netwright.lib.inventory import Device

    app.inventory.devices = []
    app.inventory.add(Device(host="192.0.2.1", hostname="A"))
    page = app.pages["inventory"]
    page.refresh()
    calls = []
    original = page.tree.delete
    page.tree.delete = lambda *a, **k: calls.append(1) or original(*a, **k)
    try:
        page.refresh()
        assert calls == [], "签名未变时不应重建表格"
        app.inventory.add(Device(host="192.0.2.2", hostname="B"))
        page.refresh()
        assert calls, "设备新增后必须重建"
    finally:
        page.tree.delete = original


def test_smoke_topology_grid_layer_is_reused(app):
    """性能回归：网格层只在尺寸变化时重建，重复绘制不新增网格线。"""
    app.show("topology")
    page = app.pages["topology"]
    page.refresh()
    page._draw()
    first = len(page.canvas.find_withtag("grid"))
    page._draw()
    assert len(page.canvas.find_withtag("grid")) == first
    assert page._grid_size == (page.canvas.winfo_width(), page.canvas.winfo_height())


def test_smoke_help_dialog_and_demo_data(app):
    """引导面板可打开，一键演示数据能填满清单并跳到拓扑。"""
    from netwright.pages.help import show_help

    dialog = show_help(app)
    assert dialog.winfo_exists()
    dialog._load_demo()
    assert len(app.inventory.devices) >= 7
    assert app._active_key == "topology"
    assert app.controller_store.graph.stats()["nodes"] >= 7

    # 清干净，避免污染后面的用例
    dialog2 = show_help(app)
    dialog2._clear_demo()
    assert not any(d.note.startswith("演示数据") for d in app.inventory.devices)
    dialog2.close()

def test_smoke_demo_can_be_cleared(app):
    """演示数据要能一键进、也能一键清（含链路与图）。"""
    from netwright import demo

    if demo.is_demo_loaded(app.inventory):
        app.clear_demo_data()
    demo.seed(app.inventory)
    app.controller_store.graph.clear()
    app.controller_store.sync_inventory()
    assert demo.is_demo_loaded(app.inventory)

    removed = app.clear_demo_data()
    assert removed == len(demo.DEMO_DEVICES)
    assert not demo.is_demo_loaded(app.inventory)
    assert not any(d.note == demo.DEMO_NOTE for d in app.inventory.devices)
    assert "Core-SW-01" not in [d.hostname for d in app.inventory.devices]
    remaining = {n.name for n in app.controller_store.graph.nodes.values()}
    assert not (remaining & {d.hostname for d in demo.DEMO_DEVICES})
    # 入口存在：概览与设备清单各有清除按钮
    assert hasattr(app.pages["dashboard"], "_clear_demo")
    assert hasattr(app.pages["inventory"], "clear_demo")


def test_smoke_dashboard_clear_demo_click_path(app):
    """回归：概览「清除演示数据」按钮的真实点击路径。

    v3.18.4 漏 import ``toast``，无数据时点击即 NameError——点击路径必须有测试。
    """
    from netwright import demo

    page = app.pages["dashboard"]
    if demo.is_demo_loaded(app.inventory):
        app.clear_demo_data()
    page.refresh()                       # 无数据 → 提示分支（此前 NameError）
    page._clear_demo()
    assert not demo.is_demo_loaded(app.inventory)

    demo.seed(app.inventory)             # 有数据 → 清除成功分支
    app.controller_store.graph.clear()
    app.controller_store.sync_inventory()
    page._clear_demo()
    assert not demo.is_demo_loaded(app.inventory)
    assert not any(d.note == demo.DEMO_NOTE for d in app.inventory.devices)


def test_smoke_timeline_linkage_event(app):
    """R2：点时间线事件行 → 跳到事件页并定位该事件。"""
    app.event_bus.publish("linkage.test", "时间线联动定位测试事件", source="test")
    page = app.pages["timeline"]
    page.refresh()
    event_items = [i for i in page.items if i.kind == "event"]
    assert event_items, "时间线里应有事件条目"
    page._open(event_items[0])
    assert app._active_key == "events"
    assert app.pending_focus is None, "pending_focus 应被事件页消费"
    sel = app.pages["events"].tree.selection()
    assert sel, "事件页应选中定位到的事件行"


def test_smoke_timeline_linkage_backup(app, tmp_path):
    """R2：点时间线快照行 → 打开该设备的备份历史对话框。"""
    import tkinter as tk

    from netwright.sdn.backup import ConfigBackup

    backup = ConfigBackup(str(tmp_path))
    backup.save("联动测试设备", "sysname X\nvlan 10\n")
    original = app.controller_store.backups
    app.controller_store.backups = backup
    try:
        page = app.pages["timeline"]
        page.refresh()
        backup_items = [i for i in page.items if i.kind == "backup"]
        assert backup_items, "时间线里应有快照条目"
        page._open(backup_items[0])
        dialogs = [w for w in app.winfo_children() if isinstance(w, tk.Toplevel)
                   and "备份历史" in str(w.title())]
        assert dialogs, "应打开备份历史对话框"
        for d in dialogs:
            d.destroy()
    finally:
        app.controller_store.backups = original


def test_smoke_timeline_linkage_intent(app):
    """R2：点时间线意图运行行 → 跳到控制器运行档案并选中该档案。"""
    from netwright.lib.inventory import Device

    app.inventory.devices = []
    app.inventory.add(Device(host="192.0.2.1", vendor="huawei", hostname="A"))
    page = app.pages["controller"]
    page.nb.select(1)
    page._render_fields()
    page.cmb_target.current(1)
    page.field_vars["vlans"].set("10,20")
    page.dry_run()

    timeline = app.pages["timeline"]
    timeline.refresh()
    intent_items = [i for i in timeline.items if i.kind == "intent"]
    assert intent_items, "时间线里应有意图运行条目"
    run_id = intent_items[0].payload["run_id"]
    timeline._open(intent_items[0])
    assert app._active_key == "controller"
    assert app.pending_focus is None
    assert page.runs_tree.selection() == (str(run_id),), "运行档案应被定位选中"


def test_smoke_timeline_linkage_fallbacks(app):
    """R2：缺 payload / 未知类型不崩，落回对应页面首页。"""
    import time as _time

    from netwright.sdn.timeline import TimelineItem

    page = app.pages["timeline"]
    page._open(TimelineItem(ts=_time.time(), kind="event", device="",
                            title="裸事件（无 payload）"))
    assert app._active_key == "events"
    page._open(TimelineItem(ts=_time.time(), kind="mystery", device="",
                            title="未知类型"))
    assert app._active_key == "dashboard"


def test_smoke_restore_backup_dialog_flow(app, tmp_path, monkeypatch):
    """R3 GUI：恢复对话框确认文案 + 后台恢复 + 完成弹窗（弹窗全部 mock）。"""
    import time

    from netwright.pages.inventory import BackupHistoryDialog
    from netwright.sdn.backup import ConfigBackup
    from netwright.sdn.southbound import CommandOutput

    class FakeRestoreAdapter:
        protocol = "cli"

        def __init__(self):
            self.sent = []

        def read_config(self, device, timeout=15.0):
            return "sysname LIVE\nvlan 1\n"

        def run_commands(self, device, commands, timeout=15.0):
            self.sent.append(list(commands))
            return [CommandOutput(c, "ok", "") for c in commands]

    adapter = FakeRestoreAdapter()
    app.controller_store.registry.for_device = lambda _d: adapter

    from netwright.lib.inventory import Device

    app.inventory.devices = []
    app.inventory.add(Device(host="192.0.2.1", vendor="huawei",
                             hostname="恢复联动设备"))

    boxes = {"ask": [], "info": [], "error": []}
    monkeypatch.setattr("netwright.pages.inventory.messagebox.askyesno",
                        lambda *a, **k: boxes["ask"].append(a) or True)
    monkeypatch.setattr("netwright.pages.inventory.messagebox.showinfo",
                        lambda *a, **k: boxes["info"].append(a))
    monkeypatch.setattr("netwright.pages.inventory.messagebox.showerror",
                        lambda *a, **k: boxes["error"].append(a))

    backup = ConfigBackup(str(tmp_path / "bk"))
    backup.save("恢复联动设备", "sysname OLD\nvlan 9\nvlan 10\n")   # 待恢复的快照
    original = app.controller_store.backups
    app.controller_store.backups = backup
    try:
        dialog = BackupHistoryDialog(app, "恢复联动设备")
        dialog.listbox.selection_set(0)
        dialog._restore_selected()
        # worker 线程 + after 轮询：手动泵事件循环直到完成弹窗出现
        for _ in range(200):
            app.update()
            if boxes["info"]:
                break
            time.sleep(0.05)
        app.update()
        assert boxes["ask"], "必须先弹二次确认"
        confirm_text = boxes["ask"][0][1]
        assert "将覆盖 3 行配置" in confirm_text, "确认弹窗要写明影响行数"
        assert "自动备份" in confirm_text
        assert adapter.sent == [["sysname OLD", "vlan 9", "vlan 10"]]
        assert boxes["info"], "完成后要有结果弹窗"
        done_text = boxes["info"][0][1]
        assert "已自动备份为" in done_text and ".cfg" in done_text
        dialog.destroy()
    finally:
        app.controller_store.backups = original


def test_smoke_restore_backup_dialog_requires_selection(app, tmp_path, monkeypatch):
    """R3 GUI：没选中快照时点恢复 → 提示且不弹确认（防止误操作）。"""
    from netwright.lib.inventory import Device
    from netwright.pages.inventory import BackupHistoryDialog
    from netwright.sdn.backup import ConfigBackup

    app.inventory.devices = []
    app.inventory.add(Device(host="192.0.2.2", vendor="huawei",
                             hostname="恢复联动设备B"))
    backup = ConfigBackup(str(tmp_path / "bk2"))
    backup.save("恢复联动设备B", "sysname B\n")
    original = app.controller_store.backups
    app.controller_store.backups = backup
    try:
        dialog = BackupHistoryDialog(app, "恢复联动设备B")
        asked = []
        monkeypatch.setattr("netwright.pages.inventory.messagebox.askyesno",
                            lambda *a, **k: asked.append(a) or True)
        dialog._restore_selected()          # 未选中任何行
        assert not asked, "未选中快照时不应进入确认"
        dialog.listbox.selection_set(0)
        dialog._restore_selected()
        assert asked, "选中后应弹二次确认"
        dialog.destroy()
    finally:
        app.controller_store.backups = original


def test_smoke_inspect_cancel_button_states(app, monkeypatch):
    """R7 GUI：巡检中「取消」可用、开始按钮变灰；取消后可再次开始。"""
    import time

    import netwright.lib.inspector as insp
    from netwright.lib.inventory import Device

    def slow_run(device, scheme_commands, timeout=15.0, port=None):
        time.sleep(0.05)
        cmds = [insp.CommandResult(title="巡检", command=c, output="ok")
                for c in scheme_commands]
        return insp.DeviceResult(host=device.host, vendor=device.vendor,
                                 status="OK", commands=cmds, cost_ms=1)

    monkeypatch.setattr(insp, "run_device", slow_run)
    app.inventory.devices = []
    app.inventory.add(Device(host="192.0.2.1", vendor="huawei", hostname="INS-1"))
    page = app.pages["inspect"]
    page.refresh_devices()
    page.cmb_scheme.current(0)
    page.cmb_workers.set("5")

    page.start()
    assert str(page.btn_run.cget("state")) == "disabled"
    assert str(page.btn_cancel.cget("state")) == "normal"

    page.cancel_run()                       # 立即变灰
    assert str(page.btn_cancel.cget("state")) == "disabled"
    for _ in range(100):                    # 泵事件循环等结果收尾
        app.update()
        if str(page.btn_run.cget("state")) == "normal":
            break
        time.sleep(0.05)
    app.update()
    assert str(page.btn_run.cget("state")) == "normal", "取消后应能再次开始"
    assert str(page.btn_cancel.cget("state")) == "disabled"

    page.start()                            # 可再次开始
    page.cancel_run()
    for _ in range(100):
        app.update()
        if str(page.btn_run.cget("state")) == "normal":
            break
        time.sleep(0.05)
    app.update()
    assert str(page.btn_run.cget("state")) == "normal"


def test_smoke_generate_page_compile_to_policies(app, monkeypatch):
    """R13 GUI：生成页「编译为策略」→ 运行档案出现模板策略且已预演。"""
    from netwright.lib.inventory import Device

    page = app.pages["generate"]
    huawei_tpl = next((name for name, t in page.tpl_map.items()
                       if t["vendor"] == "huawei" and t["vars"]), None)
    if huawei_tpl is None:
        huawei_tpl = next(name for name, t in page.tpl_map.items() if t["vars"])
    app.inventory.devices = []
    app.inventory.add(Device(host="192.0.2.1", vendor="huawei", hostname="TPL-SW"))
    page.cmb_tpl.set(huawei_tpl)
    page._load_template()
    tpl = page.tpl_map[huawei_tpl]
    cols = list(tpl["vars"])
    rows = [",".join(cols)]
    row = {c: ("TPL-SW" if c in ("hostname", "name", "device") else f"V_{c}")
           for c in cols}
    rows.append(",".join(row[c] for c in cols))
    page.table_text.delete("1.0", "end")
    page.table_text.insert("1.0", "\n".join(rows))

    monkeypatch.setattr("netwright.pages.generation.messagebox.askyesno",
                        lambda *a, **k: True)
    before = len(app.controller_store.lifecycle.runs)
    page.compile_to_policies()
    assert app._active_key == "controller", "编译后应跳到控制器页"
    runs = app.controller_store.lifecycle.recent(50)
    assert len(runs) >= before + 1
    new_runs = [r for r in runs if r.policy.intent_key == "template_deploy"]
    assert new_runs, "运行档案里应有 template_deploy 条目"
    assert new_runs[0].state == "planned", "编译后应完成静态预演"
    assert new_runs[0].policy.params["template"]["file"], "档案应能追溯到模板文件"
