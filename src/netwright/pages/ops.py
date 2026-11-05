"""运维中心：把 v3.30 的合规检查 / 路径追踪 / 漂移扫描接到界面上。

设计取舍：
  * 一个页面放三件事，避免在设备清单/拓扑/设置里各塞一个按钮，改动面最小；
  * 所有结论都来自 ``lib/compliance``、``sdn/pathtrace``、``sdn/schedule``，
    页面只做装配与展示（与项目"页面只做装配"的约定一致）；
  * 漂移扫描可能耗时，走后台线程，结果回主线程再刷表格（禁止后台碰 Tk）。
"""
from __future__ import annotations

import threading
import tkinter as tk
from tkinter import ttk

from netwright.lib.compliance import report as compliance_report
from netwright.sdn.schedule import drift_scan
from netwright.sdn.pathtrace import describe_path, shortest_path
from netwright.theme import FONT_SMALL, theme
from netwright.widgets import (DataTable, Page, SectionCard, WButton,
                               page_header, toast)


class OpsPage(Page):
    def __init__(self, master, app):
        super().__init__(master, app)
        hdr = page_header(self, "运维中心", "合规检查 · 路径追踪 · 配置漂移",
                          "系统 / 运维中心")
        WButton(hdr.actions, text="刷新", command=self.refresh).pack(side=tk.LEFT)

        body = tk.Frame(self, bg=theme.bg)
        body.pack(fill=tk.BOTH, expand=True, padx=20, pady=(0, 18))
        body.rowconfigure(1, weight=1)
        body.columnconfigure(0, weight=3)
        body.columnconfigure(1, weight=2)

        # ── 合规检查 ──
        self.card_compliance = SectionCard(
            body, title="配置合规检查",
            desc="对最近一次备份快照跑规则集；命中项带行号与证据")
        self.card_compliance.grid(row=0, column=0, rowspan=2, sticky="nsew",
                                  padx=(0, 12), pady=(0, 12))
        bar = tk.Frame(self.card_compliance.body, bg=theme.panel)
        bar.pack(fill=tk.X, pady=(0, 8))
        self.var_device = tk.StringVar()
        self.cmb_device = ttk.Combobox(bar, textvariable=self.var_device,
                                       state="readonly", width=24)
        self.cmb_device.pack(side=tk.LEFT, padx=(0, 8))
        WButton(bar, text="检查", command=self.run_compliance).pack(side=tk.LEFT, padx=(0, 8))
        WButton(bar, text="检查全部", command=lambda: self.run_compliance(all_devices=True)).pack(
            side=tk.LEFT)
        self.var_score = tk.StringVar(value="未检查")
        tk.Label(self.card_compliance.body, textvariable=self.var_score, bg=theme.panel,
                 fg=theme.muted, font=FONT_SMALL, anchor="w").pack(fill=tk.X)

        self.table = DataTable(
            self.card_compliance.body,
            columns=["device", "score", "severity", "rule", "evidence"],
            headings={"device": "设备", "score": "得分", "severity": "级别",
                      "rule": "规则", "evidence": "证据"},
            widths={"device": 120, "score": 60, "severity": 70, "rule": 200,
                    "evidence": 260},
            height=14)
        self.table.pack(fill=tk.BOTH, expand=True, pady=(8, 0))

        # ── 路径追踪 ──
        card_path = SectionCard(body, title="路径追踪",
                                desc="拓扑上算源到目的经过哪些设备（只读）")
        card_path.grid(row=0, column=1, sticky="nsew", pady=(0, 12))
        row = tk.Frame(card_path.body, bg=theme.panel)
        row.pack(fill=tk.X, pady=(0, 6))
        tk.Label(row, text="源", bg=theme.panel, fg=theme.muted).pack(side=tk.LEFT)
        self.var_src = tk.StringVar()
        self.cmb_src = ttk.Combobox(row, textvariable=self.var_src, width=14)
        self.cmb_src.pack(side=tk.LEFT, padx=(4, 8))
        tk.Label(row, text="目的", bg=theme.panel, fg=theme.muted).pack(side=tk.LEFT)
        self.var_dst = tk.StringVar()
        self.cmb_dst = ttk.Combobox(row, textvariable=self.var_dst, width=14)
        self.cmb_dst.pack(side=tk.LEFT, padx=(4, 8))
        WButton(row, text="追踪", command=self.run_path).pack(side=tk.LEFT)
        self.var_path = tk.StringVar(value="输入起点与终点后点「追踪」")
        tk.Label(card_path.body, textvariable=self.var_path, bg=theme.panel,
                 fg=theme.fg, font=FONT_SMALL, anchor="w", justify=tk.LEFT,
                 wraplength=320).pack(fill=tk.X)

        # ── 漂移扫描 ──
        card_drift = SectionCard(body, title="配置漂移",
                                 desc="与最近快照对比现网，只报有变化的设备")
        card_drift.grid(row=1, column=1, sticky="nsew")
        self.btn_drift = WButton(card_drift.body, text="立即扫描",
                                 command=self.run_drift)
        self.btn_drift.pack(anchor="w", pady=(0, 6))
        self.var_drift = tk.StringVar(value="尚未扫描")
        tk.Label(card_drift.body, textvariable=self.var_drift, bg=theme.panel,
                 fg=theme.muted, font=FONT_SMALL, anchor="w", justify=tk.LEFT,
                 wraplength=320).pack(fill=tk.X)

        self._drift_busy = False
        self.refresh()

    # ── 数据 ──
    def refresh(self):
        hosts = [d.host for d in self.app.inventory.devices]
        if hasattr(self, "cmb_device"):
            values = [f"{getattr(d, 'display_name', '') or d.host} ({d.host})"
                      for d in self.app.inventory.devices]
            self.cmb_device["values"] = values
            if values and not self.var_device.get():
                self.var_device.set(values[0])
        if hasattr(self, "var_src"):
            names = sorted(self.app.controller_store.graph.nodes)
            self.cmb_src["values"] = names
            self.cmb_dst["values"] = names
        return hosts

    def _selected_host(self) -> str:
        text = self.var_device.get()
        if "(" in text and text.endswith(")"):
            return text.rsplit("(", 1)[1][:-1]
        return text.strip()

    def run_compliance(self, all_devices: bool = False):
        store = self.app.controller_store
        backups = getattr(store, "backups", None)
        if backups is None:
            toast(self.app, "未配置备份目录，无法做合规检查", "warn")
            return
        hosts = [d.host for d in self.app.inventory.devices] if all_devices else [
            self._selected_host()]
        hosts = [h for h in hosts if h]
        if not hosts:
            toast(self.app, "清单里没有设备", "info")
            return
        rows, tags = [], []
        scores = []
        for host in hosts[:50]:
            entry = backups.latest(host)
            if entry is None:
                rows.append((host, "—", "提示", "没有配置快照", ""))
                tags.append(("info",))
                continue
            result = compliance_report(backups.read(entry), host)
            scores.append(result["score"])
            if not result["findings"]:
                rows.append((host, str(result["score"]), "OK", "未发现违规", ""))
                tags.append(("ok",))
                continue
            for finding in result["findings"]:
                rows.append((host, str(result["score"]), finding["severity"],
                             finding["title"],
                             f"第{finding['line_no']}行 {finding['evidence']}".strip()))
                tags.append((finding["severity"],))
        self.table.set_rows(rows, tags_by_row=tags)
        if scores:
            self.var_score.set(
                f"已检查 {len(scores)} 台，平均 {sum(scores) // len(scores)} 分，"
                f"最低 {min(scores)} 分")
        else:
            self.var_score.set("没有可用快照：先到「设备清单」做一次备份")

    def run_path(self):
        src = self.var_src.get().strip()
        dst = self.var_dst.get().strip()
        if not src or not dst:
            toast(self.app, "请填写起点与终点", "info")
            return
        result = shortest_path(self.app.controller_store.graph, src, dst)
        self.var_path.set(describe_path(result))

    def run_drift(self):
        if self._drift_busy:
            return
        self._drift_busy = True
        self.btn_drift.set_loading(True)
        self.var_drift.set("扫描中…")
        store = self.app.controller_store

        def worker():
            try:
                result = drift_scan(store)
            except Exception as exc:      # noqa: BLE001
                result = {"error": str(exc)}
            self.app.after(0, lambda r=result: self._drift_done(r))

        threading.Thread(target=worker, daemon=True).start()

    def _drift_done(self, result: dict):
        self._drift_busy = False
        self.btn_drift.set_loading(False)
        if "error" in result:
            self.var_drift.set(f"扫描失败：{result['error']}")
            toast(self.app, "漂移扫描失败", "warn")
            return
        drifted = result.get("drifted", [])
        errors = result.get("errors", [])
        if drifted:
            names = "、".join(d["hostname"] or d["device"] for d in drifted[:5])
            self.var_drift.set(f"发现 {len(drifted)} 台漂移：{names}")
            toast(self.app, f"{len(drifted)} 台设备配置有变化", "warn")
            for item in drifted:
                self.app.event_bus.publish(
                    "config.drift", f"配置漂移：{item['hostname'] or item['device']}",
                    severity="warning", device=item["device"])
        else:
            self.var_drift.set(f"已扫描 {result.get('scanned', 0)} 台，配置一致")
        if errors:
            self.var_drift.set(self.var_drift.get() + f"；{len(errors)} 台连接失败")
