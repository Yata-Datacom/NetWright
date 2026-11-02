"""事件工作区 —— 控制器事件流 + 南向通道 + 下发审计。

三块内容对应控制器的三种可观测性：
  * 事件流（EventBus）：拓扑变更、策略编译、南向命令失败等实时事件；
  * 南向通道（AdapterRegistry）：每种协议的能力位与依赖就绪状态；
  * 下发审计（deploy.audit_tail）：真实下发过的命令记录（不含密码）。

事件来自后台线程：回调只把事件塞进待处理队列，再由 Tk 主线程合并刷新，
避免每条事件都触发一次 Treeview 更新。
"""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from netwright.lib.controller import deploy as deploy_mod
from netwright.theme import FONT_SMALL, theme
from netwright.widgets import (Page, SectionCard, StatTile, Tag, WButton,
                               make_table, page_header, zebra)

SEVERITY_TEXT = {"info": "ℹ 信息", "warning": "▲ 告警", "critical": "✖ 严重"}
SEVERITY_TAG = {"info": "info", "warning": "warn", "critical": "err"}


class EventsPage(Page):
    def __init__(self, master, app):
        super().__init__(master, app)
        hdr = page_header(self, "事件", "控制器事件流、南向通道状态与下发审计", "控制器 / 事件")
        self.var_filter = tk.StringVar(value="全部级别")
        cmb = ttk.Combobox(hdr.actions, textvariable=self.var_filter, width=10,
                           state="readonly", values=["全部级别", "仅告警", "仅严重"])
        cmb.pack(side=tk.LEFT, padx=(0, 6))
        cmb.bind("<<ComboboxSelected>>", lambda _e: self.refresh())
        WButton(hdr.actions, text="刷新", command=self.refresh).pack(side=tk.LEFT, padx=(0, 6))
        WButton(hdr.actions, text="清空事件", command=self.clear).pack(side=tk.LEFT)

        tiles = tk.Frame(self, bg=theme.bg)
        tiles.pack(fill=tk.X, padx=20)
        self.tile_total = StatTile(tiles, "事件总数", "0", "本次会话", "info")
        self.tile_warn = StatTile(tiles, "告警", "0", "需关注", "warn")
        self.tile_crit = StatTile(tiles, "严重", "0", "需立即处置", "err")
        for tile in (self.tile_total, self.tile_warn, self.tile_crit):
            tile.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 10))

        body = tk.Frame(self, bg=theme.bg)
        body.pack(fill=tk.BOTH, expand=True, padx=20, pady=(12, 18))
        body.columnconfigure(0, weight=3)
        body.columnconfigure(1, weight=1, minsize=300)
        body.rowconfigure(0, weight=1)

        card = SectionCard(body, title="事件流", desc="最新在上，保留最近 500 条")
        card.grid(row=0, column=0, sticky="nsew", padx=(0, 12))
        wrap, self.tree = make_table(
            card.body,
            columns=["time", "sev", "topic", "source", "message"],
            headings={"time": "时间", "sev": "级别", "topic": "主题",
                      "source": "来源", "message": "消息"},
            widths={"time": 68, "sev": 60, "topic": 138, "source": 64, "message": 280},
            height=16)
        wrap.pack(fill=tk.BOTH, expand=True)
        self.tree.tag_configure("err", foreground=theme.err)
        self.tree.tag_configure("warn", foreground=theme.warn)
        self.tree.tag_configure("info", foreground=theme.fg)

        side = tk.Frame(body, bg=theme.bg)
        side.grid(row=0, column=1, sticky="nsew")

        south = SectionCard(side, title="南向通道", desc="能力位与依赖状态")
        south.pack(fill=tk.X, pady=(0, 12))
        self.south_box = tk.Frame(south.body, bg=theme.panel)
        self.south_box.pack(fill=tk.X)

        sources = SectionCard(side, title="事件源", desc="syslog / SNMP trap 接进来才算“网络状态”")
        sources.pack(fill=tk.X, pady=(0, 12))
        self.var_syslog = tk.StringVar(value="Syslog：未启动")
        self.var_trap = tk.StringVar(value="SNMP Trap：未启动")
        tk.Label(sources.body, textvariable=self.var_syslog, bg=theme.panel,
                 fg=theme.muted, font=FONT_SMALL).pack(anchor="w")
        tk.Label(sources.body, textvariable=self.var_trap, bg=theme.panel,
                 fg=theme.muted, font=FONT_SMALL).pack(anchor="w", pady=(2, 6))
        row = tk.Frame(sources.body, bg=theme.panel)
        row.pack(fill=tk.X)
        WButton(row, text="启动监听", command=self.start_sources).pack(side=tk.LEFT)
        WButton(row, text="停止", command=self.stop_sources).pack(side=tk.LEFT, padx=(6, 0))

        audit = SectionCard(side, title="下发审计", desc="真实下发记录（无密码）")
        audit.pack(fill=tk.BOTH, expand=True)
        self.audit_text = tk.Text(audit.body, height=12, bg=theme.panel, fg=theme.fg,
                                  relief=tk.FLAT, font=("Consolas", 9), wrap="none",
                                  highlightthickness=0, bd=0)
        self.audit_text.pack(fill=tk.BOTH, expand=True)

        self._subscribed = True
        self._unsub = app.event_bus.subscribe(self._on_event)
        self.refresh()

    # ── 事件订阅（后台线程安全：只入队，主线程刷新）──
    def _on_event(self, event):
        """事件可能来自 REST 线程 / syslog 线程。

        非主线程**绝不碰 Tk**（createcommand 在主循环未运行时可能挂死）；
        只置脏标记，交给 10 秒自动刷新或下一次手动刷新。
        """
        import threading

        if threading.current_thread() is not threading.main_thread():
            self._dirty = True
            return
        try:
            self.after(50, self.refresh)
        except (RuntimeError, tk.TclError):
            self._dirty = True

    def destroy(self):  # noqa: D102
        try:
            if self._unsub:
                self._unsub()
                self._unsub = None
        except Exception:      # noqa: BLE001
            pass
        super().destroy()

    # ── 刷新 ──
    def _min_severity(self) -> str | None:
        label = self.var_filter.get()
        if label == "仅严重":
            return "critical"
        if label == "仅告警":
            return "warning"
        return None

    def refresh(self):
        bus = self.app.event_bus
        counts = bus.counts()
        self.tile_total.set(counts.get("total", 0))
        self.tile_warn.set(counts.get("warning", 0))
        self.tile_crit.set(counts.get("critical", 0))

        events = bus.snapshot(limit=200, min_severity=self._min_severity())
        self.tree.delete(*self.tree.get_children())
        if not events:
            self.tree.insert("", "end", values=(
                "—", "ℹ 提示", "—", "—",
                "暂无事件：可在下方「事件源」启动监听，或在拓扑页做一次发现"))
        for i, event in enumerate(events):
            data = event.to_dict()
            iid = self.tree.insert("", "end", values=(
                data["time"], SEVERITY_TEXT.get(event.severity, event.severity),
                event.topic, event.source or "—", event.message))
            self.tree.item(iid, tags=(SEVERITY_TAG.get(event.severity, "info"),))
            zebra(self.tree, iid, i)
        self._render_southbound()
        self._render_audit()

    def _render_southbound(self):
        for child in self.south_box.winfo_children():
            child.destroy()
        for adapter in self.app.controller_store.registry.describe():
            row = tk.Frame(self.south_box, bg=theme.panel)
            row.pack(fill=tk.X, pady=3)
            Tag(row, text="就绪" if adapter["available"] else "缺依赖",
                kind="ok" if adapter["available"] else "warn").pack(side=tk.LEFT)
            tk.Label(row, text=adapter["name"], bg=theme.panel, fg=theme.fg,
                     font=FONT_SMALL).pack(side=tk.LEFT, padx=(8, 4))
            tk.Label(row, text=f"{len(adapter['capabilities'])} 项能力", bg=theme.panel,
                     fg=theme.faint, font=FONT_SMALL).pack(side=tk.RIGHT)
        self._render_sources()

    def _render_sources(self):
        status = self.app.controller_store.listener_status()
        syslog = status["syslog"]
        trap = status["snmp_trap"]
        self.var_syslog.set(
            f"Syslog：{'运行中 UDP ' + str(syslog['port']) if syslog['running'] else '未启动'}"
            f"（已收 {syslog['received']} 条）")
        self.var_trap.set(
            f"SNMP Trap：{'运行中 UDP ' + str(trap['port']) if trap['running'] else '未启动'}"
            f"（已收 {trap['received']} 条）")

    def start_sources(self):
        store = self.app.controller_store
        try:
            if not store.syslog.running:
                store.start_syslog()
            if not store.snmp_trap.running:
                store.start_snmp_trap()
        except OSError as exc:
            self.app.set_status(f"监听启动失败（端口被占用？）：{exc}")
            return
        self.app.set_status("Syslog / SNMP Trap 监听已启动，设备指向本机即可看到事件")
        self.refresh()

    def stop_sources(self):
        self.app.controller_store.stop_listeners()
        self.app.set_status("事件源监听已停止")
        self.refresh()

    def _render_audit(self):
        entries = deploy_mod.audit_tail(40)
        lines = []
        for entry in reversed(entries):
            lines.append(f"{entry.get('time', '')}  {entry.get('action', '')}  "
                         f"{entry.get('device', '')}  {entry.get('status', '')}")
        self.audit_text.delete("1.0", "end")
        self.audit_text.insert("1.0", "\n".join(lines) or "暂无下发记录")

    def clear(self):
        self.app.event_bus.clear()
        self.app.event_bus.publish("events.cleared", "事件历史已清空", source="ui")
        self.refresh()
