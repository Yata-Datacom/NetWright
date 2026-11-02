"""时间线工作区：事件 + 配置快照 + 意图运行，一条按时间排序的排障视图。"""
from __future__ import annotations

import tkinter as tk

from netwright.sdn.timeline import build_timeline
from netwright.theme import FONT_SMALL, theme
from netwright.widgets import DataTable, Page, SectionCard, WButton, page_header

# 未知/缺 payload 的条目落回的页面首页（R2：绝不因跳转目标缺失而崩）
FOCUS_FALLBACK = {"event": "events", "backup": "inventory", "intent": "controller"}


class TimelinePage(Page):
    def __init__(self, master, app):
        super().__init__(master, app)
        hdr = page_header(self, "时间线",
                          "事件 / 配置快照 / 意图运行合成一条时间轴，排障先看这里",
                          "系统 / 时间线")
        WButton(hdr.actions, text="刷新", command=self.refresh).pack(side=tk.LEFT)

        self.var_stat = tk.StringVar(value="")
        card = SectionCard(self, title="最近 120 条",
                           desc="按时间倒序；点行看详情，双击跳到对应页面定位")
        card.pack(fill=tk.BOTH, expand=True, padx=20, pady=(0, 18))
        self.table = DataTable(
            card.body,
            columns=["time", "kind", "device", "title", "detail"],
            headings={"time": "时间", "kind": "类型", "device": "设备",
                      "title": "内容", "detail": "详情"},
            widths={"time": 110, "kind": 80, "device": 130, "title": 380, "detail": 160},
            height=18)
        self.table.pack(fill=tk.BOTH, expand=True)
        self.tree = self.table.tree
        self.tree.tag_configure("warning", foreground=theme.warn)
        self.tree.tag_configure("critical", foreground=theme.err)
        self.tree.tag_configure("info", foreground=theme.fg)
        self.tree.bind("<<TreeviewSelect>>", lambda _e: self._show_detail())
        self.tree.bind("<Double-1>", self._on_double)
        self.detail = tk.Label(card.body, textvariable=self.var_stat, bg=theme.panel,
                               fg=theme.muted, font=FONT_SMALL, anchor="w")
        self.detail.pack(fill=tk.X, pady=(6, 0))
        self.items: list = []
        self.refresh()

    def refresh(self):
        store = getattr(self.app, "controller_store", None)
        if store is None or not hasattr(self, "tree"):
            return
        self.items = build_timeline(store)
        # 数据未变就跳过重建：10 秒刷新下这是最大的一笔开销
        signature = (len(self.items), self.items[0].to_dict()["ts"] if self.items else 0)
        if signature == getattr(self, "_refresh_sig", None) and self.tree.get_children():
            return
        self._refresh_sig = signature
        with self.table.preserve_selection():
            if not self.items:
                self.table.set_rows([(
                    "—", "提示", "—",
                    "还没有可展示的记录：载入演示数据或跑一次备份/意图", "")])
                self.var_stat.set("时间线为空")
                return
            self.table.set_rows(
                [(item.time_text, item.kind_label, item.device or "—",
                  item.title, item.detail) for item in self.items],
                [(item.severity,) for item in self.items])
        self.var_stat.set(f"{len(self.items)} 条记录（最新在上）")

    def _show_detail(self):
        selection = self.tree.selection()
        if not selection or not self.items:
            return
        index = self.tree.index(selection[0])
        if index < len(self.items):
            item = self.items[index]
            self.var_stat.set(
                f"{item.time_text} · {item.kind_label} · {item.device or '—'} · "
                f"{item.title}" + (f" · {item.detail}" if item.detail else ""))

    # ── R2 联动：点行跳转到对应页面并定位 ──
    def _on_double(self, _ev=None):
        selection = self.tree.selection()
        if not selection or not self.items:
            return
        index = self.tree.index(selection[0])
        if 0 <= index < len(self.items):
            self._open(self.items[index])

    def _open(self, item):
        """时间线联动入口：事件→事件页、快照→备份历史、意图→运行档案。

        缺 payload / 未知类型时退回对应页面首页，绝不崩。
        """
        kind = getattr(item, "kind", "")
        payload = getattr(item, "payload", None) or {}
        if kind == "backup" and (payload.get("device") or item.device):
            from netwright.pages.inventory import BackupHistoryDialog

            dialog = BackupHistoryDialog(self.app,
                                         payload.get("device") or item.device)
            dialog.focus_force()
            return
        if kind == "intent" and payload.get("run_id"):
            self.app.pending_focus = {"key": "controller",
                                      "payload": {"run_id": payload["run_id"]}}
            self.app.show("controller")
            return
        if kind == "event":
            self.app.pending_focus = {"key": "events",
                                      "payload": {"event_id": payload.get("event_id")}}
            self.app.show("events")
            return
        self.app.show(FOCUS_FALLBACK.get(kind, "dashboard"))
