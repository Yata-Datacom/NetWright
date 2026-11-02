"""概览工作区 —— 控制台首页。

DLUX 式首页只回答三个问题：**控制器健康吗 / 网络长什么样 / 刚刚发生了什么**。
因此这一页只有四块：KPI 磁贴、控制器状态、最近事件、快捷入口。
"""
from __future__ import annotations

import time
import tkinter as tk

from netwright import __version__
from netwright.lib import HAS_SSH
from netwright.theme import FONT_SMALL, VENDOR_COLORS, theme
from netwright.widgets import (KeyValue, Page, SectionCard, StatTile, WButton,
                               page_header, toast)

SEVERITY_COLOR = {"info": "info", "warning": "warn", "critical": "err"}


def _human_uptime(seconds: int) -> str:
    if seconds < 60:
        return f"{seconds} 秒"
    if seconds < 3600:
        return f"{seconds // 60} 分钟"
    return f"{seconds // 3600} 小时 {(seconds % 3600) // 60} 分"


class DashboardPage(Page):
    """控制器总览。"""

    def __init__(self, master, app):
        super().__init__(master, app)
        hdr = page_header(self, "概览", "控制器健康、拓扑规模与最近事件一览", "控制器 / 概览")
        WButton(hdr.actions, text="◈ 打开拓扑", command=lambda: self.app.show("topology")).pack(
            side=tk.LEFT, padx=(0, 6))
        WButton(hdr.actions, text="刷新", command=self.refresh).pack(side=tk.LEFT)

        tiles = tk.Frame(self, bg=theme.bg)
        tiles.pack(fill=tk.X, padx=20)
        self.tile_nodes = StatTile(tiles, "拓扑节点", "0", "来自清单与发现", "accent")
        self.tile_links = StatTile(tiles, "链路", "0", "LLDP + 台账", "info")
        self.tile_devices = StatTile(tiles, "纳管设备", "0", "清单中有凭据", "ok")
        self.tile_policies = StatTile(tiles, "策略", "0", "本会话编译", "warning")
        self.tile_events = StatTile(tiles, "未处理告警", "0", "事件总线", "err")
        for tile in (self.tile_nodes, self.tile_links, self.tile_devices,
                     self.tile_policies, self.tile_events):
            tile.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 10))

        body = tk.Frame(self, bg=theme.bg)
        self._body = body
        body.pack(fill=tk.BOTH, expand=True, padx=20, pady=(12, 18))
        body.columnconfigure(0, weight=2)
        body.columnconfigure(1, weight=1, minsize=330)
        body.rowconfigure(0, weight=1)

        # 第一次使用：设备清单为空时给一条最短路径（有设备后自动隐藏）
        self.onboard = SectionCard(self, title="第一次使用？从这里开始",
                                   desc="不用先读文档，三条路任选一条")
        row0 = tk.Frame(self.onboard.body, bg=theme.panel)
        row0.pack(fill=tk.X)
        WButton(row0, text="① 载入演示数据（30 秒看懂）", bg=theme.accent,
                command=self._load_demo).pack(side=tk.LEFT, padx=(0, 8))
        WButton(row0, text="② 添加我的第一台设备", command=self._add_device).pack(
            side=tk.LEFT, padx=(0, 8))
        WButton(row0, text="③ 看 5 分钟引导", command=lambda: self.app.open_help()).pack(
            side=tk.LEFT)
        self.onboard.pack(fill=tk.X, padx=20, pady=(0, 12), before=body)

        left = tk.Frame(body, bg=theme.bg)
        self._left = left
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 12))
        left.rowconfigure(0, weight=1)
        left.columnconfigure(0, weight=1)

        events_card = SectionCard(left, title="最近事件",
                                  desc="拓扑变更 / 策略编译 / 南向异常")
        self.events_card = events_card
        events_card.grid(row=0, column=0, sticky="nsew", pady=(0, 12))
        self.events_box = tk.Frame(events_card.body, bg=theme.panel)
        self.events_box.pack(fill=tk.BOTH, expand=True)

        bottom = tk.Frame(left, bg=theme.bg)
        bottom.grid(row=1, column=0, sticky="ew")
        actions = SectionCard(bottom, title="快捷入口")
        actions.pack(fill=tk.X)
        row = tk.Frame(actions.body, bg=theme.panel)
        row.pack(fill=tk.X)
        for label, key in (("◈ 拓扑视图", "topology"), ("⌘ 意图编译", "controller"),
                           ("▤ 设备清单", "inventory"), ("◎ 资产盘点", "discovery"),
                           ("✓ 批量巡检", "inspect")):
            WButton(row, text=label, command=lambda k=key: self.app.show(k)).pack(
                side=tk.LEFT, padx=(0, 8))
        # 载入与清除成对出现：演示数据要能一键进、也能一键清
        WButton(row, text="🧹 清除演示数据", command=self._clear_demo).pack(
            side=tk.LEFT, padx=(0, 8))

        right_col = tk.Frame(body, bg=theme.bg)
        right_col.grid(row=0, column=1, sticky="nsew")
        right = SectionCard(right_col, title="控制器状态", desc=f"NetWright {__version__}")
        right.pack(fill=tk.BOTH, expand=True)

        self.kv_rest = KeyValue(right.body, "REST", "", width=7)
        self.kv_south = KeyValue(right.body, "南向", "", width=7)
        self.kv_uptime = KeyValue(right.body, "运行", "", width=7)
        self.kv_ssh = KeyValue(right.body, "SSH", "", width=7)
        self.kv_topology = KeyValue(right.body, "拓扑来源", "", width=7)
        for kv in (self.kv_rest, self.kv_south, self.kv_uptime,
                   self.kv_ssh, self.kv_topology):
            kv.pack(fill=tk.X, pady=2)

        tk.Frame(right.body, bg=theme.line, height=1).pack(fill=tk.X, pady=10)
        tk.Label(right.body, text="厂商分布", bg=theme.panel, fg=theme.muted,
                 font=FONT_SMALL).pack(anchor="w")
        self.vendor_box = tk.Frame(right.body, bg=theme.panel)
        self.vendor_box.pack(fill=tk.X, pady=(6, 0))

        self.refresh()

    # ── 刷新 ──
    def _load_demo(self):
        from netwright import demo

        devices, links = demo.seed(self.app.inventory)
        self.app.controller_store.graph.clear()
        self.app.controller_store.sync_inventory()
        self.refresh()
        self.app.event_bus.publish("demo.loaded",
                                   f"已载入演示数据：{devices} 台设备 / {links} 条链路",
                                   source="dashboard")
        self.app.set_status("演示数据已载入，去「拓扑」看看效果")
        self.app.show("topology")

    def _clear_demo(self):
        from netwright import demo

        if not demo.is_demo_loaded(self.app.inventory):
            toast(self.app, "当前没有演示数据", "info")
            return
        removed = self.app.clear_demo_data()
        toast(self.app, f"已清除 {removed} 台演示设备与相关链路", "info")
        self.refresh()

    def _add_device(self):
        self.app.show("inventory")
        page = self.app.pages.get("inventory")
        if page is not None and hasattr(page, "add_dialog"):
            page.add_dialog()

    def _toggle_onboard(self):
        has_devices = bool(getattr(self.app.inventory, "devices", []))
        shown = bool(self.onboard.winfo_manager())
        if has_devices:
            if shown:
                self.onboard.pack_forget()
                self.events_card.grid()
                self._left.rowconfigure(0, weight=1)
        else:
            if not shown:
                self.onboard.pack(fill=tk.X, padx=20, pady=(0, 12), before=self._body)
            # 还没设备时事件区没有内容可看，把空间让给引导
            self.events_card.grid_remove()
            self._left.rowconfigure(0, weight=0)

    def refresh(self):
        store = getattr(self.app, "controller_store", None)
        if store is None:
            return
        self._toggle_onboard()
        stats = store.summary()
        bus = self.app.event_bus
        counts = bus.counts()

        self.tile_nodes.set(stats["nodes"])
        self.tile_links.set(stats["links"])
        self.tile_devices.set(stats["managed"])
        self.tile_policies.set(stats["policies"])
        pending = counts.get("warning", 0) + counts.get("critical", 0)
        self.tile_events.set(pending, tone="err" if counts.get("critical") else "warning")

        self.kv_rest.set(f"127.0.0.1:{self.app.controller_api.port}  ·  /api/v2")
        ready = sum(1 for a in store.registry.describe() if a["available"])
        self.kv_south.set(f"{ready}/{len(store.registry)} 通道就绪")
        self.kv_uptime.set(_human_uptime(stats["uptime_s"]))
        self.kv_ssh.set("paramiko 已安装" if HAS_SSH else "未安装 paramiko（仅 CLI/Telnet）")
        source = stats["by_source"]
        self.kv_topology.set(f"LLDP {source.get('lldp', 0)} · 台账 {source.get('ledger', 0)}")

        self._render_events(bus)
        self._render_vendors(stats["by_vendor"])

    def _render_events(self, bus):
        for child in self.events_box.winfo_children():
            child.destroy()
        events = bus.snapshot(limit=8)
        # 10 秒刷新：事件没变就跳过重建（否则每 10 秒销毁重建 8 行控件）
        signature = (len(events), events[0].id if events else 0)
        if signature == getattr(self, "_events_sig", None) and self.events_box.winfo_children():
            return
        self._events_sig = signature
        for child in self.events_box.winfo_children():
            child.destroy()
        if not events:
            tk.Label(self.events_box, text="暂无事件", bg=theme.panel, fg=theme.faint,
                     font=FONT_SMALL, anchor="w").pack(fill=tk.X, pady=6)
            return
        for event in events:
            row = tk.Frame(self.events_box, bg=theme.panel)
            row.pack(fill=tk.X, pady=2)
            color = getattr(theme, SEVERITY_COLOR.get(event.severity, "accent"))
            dot = tk.Canvas(row, width=8, height=8, bg=theme.panel, highlightthickness=0)
            dot.pack(side=tk.LEFT, padx=(0, 8))
            dot.create_oval(0, 0, 8, 8, fill=color, outline="")
            stamp = time.strftime("%H:%M:%S", time.localtime(event.ts))
            tk.Label(row, text=stamp, bg=theme.panel, fg=theme.faint,
                     font=("Consolas", 8)).pack(side=tk.LEFT)
            tk.Label(row, text=event.message, bg=theme.panel, fg=theme.fg,
                     font=FONT_SMALL, anchor="w").pack(side=tk.LEFT, padx=(8, 0),
                                                       fill=tk.X, expand=True)

    def _render_vendors(self, by_vendor: dict):
        for child in self.vendor_box.winfo_children():
            child.destroy()
        if not by_vendor:
            tk.Label(self.vendor_box, text="尚无设备", bg=theme.panel, fg=theme.faint,
                     font=FONT_SMALL, anchor="w").pack(fill=tk.X)
            return
        total = max(1, sum(by_vendor.values()))
        items = sorted(by_vendor.items(), key=lambda kv: -kv[1])
        if len(items) > 4:      # 控制台习惯：只列前四，其余并入「其他」
            head, tail = items[:4], items[4:]
            items = head + [("其他", sum(c for _v, c in tail))]
        for vendor, count in items:
            row = tk.Frame(self.vendor_box, bg=theme.panel)
            row.pack(fill=tk.X, pady=0)
            color = VENDOR_COLORS.get(vendor, VENDOR_COLORS["generic"])
            bar = tk.Canvas(row, width=54, height=6, bg=theme.panel, highlightthickness=0)
            bar.pack(side=tk.LEFT)
            bar.create_rectangle(0, 0, max(3, int(54 * count / total)), 6,
                                 fill=color, outline="")
            tk.Label(row, text=f" {vendor}", bg=theme.panel, fg=theme.fg,
                     font=FONT_SMALL, anchor="w").pack(side=tk.LEFT)
            tk.Label(row, text=str(count), bg=theme.panel, fg=theme.muted,
                     font=FONT_SMALL).pack(side=tk.RIGHT)
