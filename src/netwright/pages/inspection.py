"""批量巡检工作区页面。"""
from __future__ import annotations

import threading
import tkinter as tk
from datetime import datetime
from tkinter import filedialog, messagebox, ttk

from netwright.lib import HAS_SSH, inspector
from netwright.lib.inventory import VENDORS
from netwright.theme import FONT_MONO, theme
from netwright.lib import history as hist
from netwright.widgets import DataTable, Page, page_header, WButton, toast, draw_line_chart


def header(title, desc, page):
    page_header(page, title, desc, "运维 / 批量巡检")


class InspectPage(Page):
    def __init__(self, master, app):
        super().__init__(master, app)
        header("SSH 批量巡检", "从设备清单勾选目标 → 选方案 → 并发执行 → 异常标记 → 导出 HTML 报告", self)
        body = tk.Frame(self, bg=theme.bg)
        body.pack(fill=tk.BOTH, expand=True, padx=16, pady=(0, 12))

        top = tk.Frame(body, bg=theme.bg)
        top.pack(fill=tk.X, pady=(0, 6))
        ttk.Label(top, text="巡检方案:", style="H2.TLabel").pack(side=tk.LEFT)
        self.cmb_scheme = ttk.Combobox(top, state="readonly", width=14)
        self.cmb_scheme["values"] = list(inspector.BUILTIN_SCHEMES)
        self.cmb_scheme.current(0)
        self.cmb_scheme.pack(side=tk.LEFT, padx=(6, 14))
        ttk.Label(top, text="并发:", style="H2.TLabel").pack(side=tk.LEFT)
        self.cmb_workers = ttk.Combobox(top, state="readonly", width=4,
                                        values=("5", "10", "20", "50"), )
        self.cmb_workers.current(2)
        self.cmb_workers.pack(side=tk.LEFT, padx=(6, 14))
        self.btn_run = WButton(top, text="开始巡检", bg=theme.accent, fg="white", relief=tk.FLAT,
                                 activebackground=theme.nav2, command=self.start)
        self.btn_run.pack(side=tk.LEFT)
        self.btn_cancel = WButton(top, text="取消", command=self.cancel_run)
        self.btn_cancel.config(state=tk.DISABLED)
        self.btn_cancel.pack(side=tk.LEFT, padx=(6, 0))
        WButton(top, text="导出报告", bg=theme.nav2, fg=theme.fg, relief=tk.FLAT,
                  activebackground=theme.nav1, command=self.export_report).pack(side=tk.LEFT, padx=(6, 0))
        self.var_count = tk.StringVar(value="")
        tk.Label(top, textvariable=self.var_count, bg=theme.bg, fg=theme.muted, font=("", 9)).pack(side=tk.RIGHT)
        if not HAS_SSH:
            tk.Label(body, text="⚠ 未安装 paramiko：pip install paramiko 后重启即可启用巡检",
                     bg=theme.bg, fg=theme.warn, font=("", 10)).pack(anchor="w", pady=(0, 6))

        pane = tk.PanedWindow(body, orient=tk.HORIZONTAL, bg=theme.line, sashwidth=2)
        pane.pack(fill=tk.BOTH, expand=True)

        # 左：设备勾选
        left = tk.Frame(pane, bg=theme.panel)
        pane.add(left, width=300)
        tk.Label(left, text="目标设备（勾选）", bg=theme.panel, fg=theme.muted, font=("", 9)).pack(anchor="w", padx=10, pady=(8, 2))
        self.dev_list = tk.Frame(left, bg=theme.panel)
        self.dev_list.pack(fill=tk.BOTH, expand=True, padx=10)
        self.dev_vars: dict[str, tk.BooleanVar] = {}

        # 趋势区（页面底部固定高度）
        trend = tk.Frame(self, bg=theme.bg, height=230)
        trend.pack(fill=tk.X, side=tk.BOTTOM, padx=16, pady=(0, 10))
        trend.pack_propagate(False)
        tbar = tk.Frame(trend, bg=theme.bg)
        tbar.place(relx=0, rely=0, relwidth=1)
        ttk.Label(tbar, text="指标:", style="H2.TLabel").pack(side=tk.LEFT)
        self.cmb_metric = ttk.Combobox(tbar, state="readonly", width=14,
                                       values=("anomalies", "fail", "warn", "avg_ms"))
        self.cmb_metric.current(0)
        self.cmb_metric.pack(side=tk.LEFT, padx=(6, 8))
        tk.Button(tbar, text="刷新趋势", bg=theme.nav2, fg=theme.fg, relief=tk.FLAT,
                  command=self.draw_trend).pack(side=tk.LEFT)
        self.trend_canvas = tk.Canvas(trend, bg=theme.panel_alt,
                                      highlightbackground=theme.line,
                                      highlightthickness=1)
        self.trend_canvas.place(relx=0, rely=0, relwidth=1, relheight=1)
        tbar.lift()

        # 右：结果（R1 统一组件）
        right = tk.Frame(pane, bg=theme.panel)
        pane.add(right)
        cols = ("host", "status", "critical", "warn", "cost")
        heads = {"host": "设备", "status": "状态", "critical": "严重",
                 "warn": "告警", "cost": "耗时"}
        widths = {"host": 160, "status": 110, "critical": 60, "warn": 60, "cost": 80}
        self.table = DataTable(right, list(cols), heads, widths, height=9)
        self.table.pack(fill=tk.BOTH, expand=True, padx=10, pady=(8, 4))
        self.tree = self.table.tree   # 兼容按 iid=行号 反查结果的习惯
        self.tree.tag_configure("st-ok", foreground=theme.ok)
        self.tree.tag_configure("st-warn", foreground=theme.warn)
        self.tree.tag_configure("st-fail", foreground=theme.err)
        self.tree.tag_configure("st-un", foreground=theme.muted)
        self.tree.bind("<<TreeviewSelect>>", self._show_detail)
        self.detail = tk.Text(right, bg=theme.code_bg, fg=theme.fg, relief=tk.FLAT, font=FONT_MONO, height=12,
                              insertbackground=theme.fg)
        self.detail.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0, 10))
        self.results: list[inspector.DeviceResult] = []
        self.refresh_devices()

    def on_show(self):
        self.refresh_devices()
        self.draw_trend()

    def refresh_devices(self):
        for w in self.dev_list.winfo_children():
            w.destroy()
        self.dev_vars.clear()
        for d in self.app.inventory.devices:
            var = tk.BooleanVar(value=True)
            key = f"{d.host}:{d.port}"
            cb = ttk.Checkbutton(self.dev_list, text=f"{d.display_name} ({d.host}) · {VENDORS.get(d.vendor, d.vendor)}",
                                 variable=var, style="TCheckbutton")
            cb.pack(anchor="w", pady=1)
            self.dev_vars[key] = var

    def on_inventory_changed(self):
        self.refresh_devices()

    def start(self):
        if not HAS_SSH:
            messagebox.showwarning("缺依赖", "请先安装 paramiko：pip install paramiko")
            return
        if getattr(self, "_running", False):
            return
        picked = []
        for d in self.app.inventory.devices:
            var = self.dev_vars.get(f"{d.host}:{d.port}")
            if var and var.get():
                picked.append(d)
        if not picked:
            messagebox.showinfo("提示", "请先在左侧勾选设备（设备清单页可添加）")
            return
        scheme_name = self.cmb_scheme.get()
        scheme = inspector.BUILTIN_SCHEMES[scheme_name]
        workers = int(self.cmb_workers.get())
        # R7 巡检治理：可取消 + 并发可配（下拉）+ 每命令超时走 inspector 默认值
        self._running = True
        self._cancel_evt = threading.Event()
        self._batch_result = None
        self._batch_dirty = False
        self.btn_run.config(state=tk.DISABLED)
        self.btn_cancel.config(state=tk.NORMAL)
        self.table.set_rows([])
        self.detail.delete("1.0", tk.END)
        self.var_count.set(f"巡检中… 0/{len(picked)}")

        def worker():
            results, skipped = inspector.run_batch(
                picked, scheme, workers=workers, progress=self._progress,
                cancel=self._cancel_evt.is_set)
            self._batch_result = (results, scheme_name, skipped)   # 只置数据不碰 Tk
            self._batch_dirty = True

        threading.Thread(target=worker, daemon=True).start()
        self.after(150, self._batch_poll)

    def _progress(self, done, total):
        """worker 线程只置计数，由轮询刷新 UI（红线：后台线程不碰 Tk）。"""
        self._progress_value = (done, total)

    def _batch_poll(self):
        """主线程轮询巡检结果（与 events 页的置脏标记同一约定）。"""
        if getattr(self, "_batch_dirty", False):
            self._batch_dirty = False
            self._running = False
            self.btn_run.config(state=tk.NORMAL)
            self.btn_cancel.config(state=tk.DISABLED)
            results, scheme_name, skipped = self._batch_result
            self._done(results, scheme_name, skipped)
            return
        if getattr(self, "_running", False):
            value = getattr(self, "_progress_value", None)
            if value:
                self.var_count.set(f"巡检中… {value[0]}/{value[1]}")
            self.after(150, self._batch_poll)

    def cancel_run(self):
        """R7：取消本轮巡检——按钮立即变灰，线程池 2 秒内收尾。"""
        if getattr(self, "_running", False):
            self._cancel_evt.set()
            self.btn_cancel.config(state=tk.DISABLED)
            self.app.set_status("正在取消巡检…（等已在执行的设备收尾）")

    def _done(self, results, scheme_name, skipped=None):
        self.btn_run.config(state=tk.NORMAL)
        self.results = results
        self._scheme_name = scheme_name
        status_icon = {"OK": "✓ 正常", "WARNING": "▲ 告警", "FAILED": "✖ 失败",
                       "UNREACHABLE": "○ 不可达"}
        rows, tags = [], []
        for r in results:
            rows.append((r.host, status_icon[r.status], r.critical_count,
                         len(r.anomalies), f"{r.cost_ms} ms"))
            tags.append(({"OK": "st-ok", "WARNING": "st-warn", "FAILED": "st-fail",
                          "UNREACHABLE": "st-un"}[r.status],))
        self.table.set_rows(rows, tags)
        summary = " ".join(f"{k}:{v}" for k, v in sorted(
            {s: sum(1 for r in results if r.status == s)
             for s in {r.status for r in results}}.items()))
        note = f" · 跳过 {len(skipped)} 台（{scheme_name} 无该厂商命令集）" if skipped else ""
        self.var_count.set(f"完成：{len(results)} 台 · {summary}{note}")
        if skipped:
            self.app.set_status("已跳过: " + "、".join(skipped[:5]) + ("…" if len(skipped) > 5 else ""))
        if results:
            self.tree.selection_set("0")
            toast(self.app, f"巡检完成：{summary}", "ok" if "WARNING" not in summary
                  and "FAILED" not in summary else "warn")
        # 趋势数据落盘（每轮巡检一条摘要）
        hist.append_history("inspection", {
            "scheme": scheme_name,
            "ok": sum(1 for r in results if r.status == "OK"),
            "warn": sum(1 for r in results if r.status == "WARNING"),
            "fail": sum(1 for r in results if r.status in ("FAILED", "UNREACHABLE")),
            "anomalies": sum(len(r.anomalies) for r in results),
            "avg_ms": (sum(r.cost_ms for r in results) // len(results)) if results else 0,
        })

    METRIC_LABELS = {"anomalies": "异常/告警总数", "fail": "失败/不可达台数",
                     "warn": "警告台数", "avg_ms": "平均耗时(ms)"}

    def draw_trend(self):
        metric = self.cmb_metric.get()
        entries = hist.load_history("inspection", limit=60)
        series = hist.extract_series(entries, metric)
        draw_line_chart(self.trend_canvas, series,
                        title=f"巡检趋势 · {self.METRIC_LABELS.get(metric, metric)}",
                        empty_text="暂无巡检历史：执行一次批量巡检后即可看到趋势")

    def _show_detail(self, _ev=None):
        sel = self.tree.selection()
        if not sel:
            return
        r = self.results[int(sel[0])]
        self.detail.delete("1.0", tk.END)
        self.detail.insert(tk.END, f"设备 {r.host} · {r.vendor} · {r.status} · {r.cost_ms}ms\n", "h")
        for a in r.anomalies:
            mark = "🔴" if a.severity == "critical" else "🟠"
            self.detail.insert(tk.END, f"{mark} [{a.severity.upper()}] {a.title} — {a.message}\n")
        for c in r.commands:
            self.detail.insert(tk.END, f"\n▸ {c.command}\n")
            if c.error:
                from netwright.lib.errors import friendly_text

                self.detail.insert(tk.END, f"  [错误] {friendly_text(c.error)}\n")
            self.detail.insert(tk.END, c.output[:3000] + ("\n…(截断)" if len(c.output) > 3000 else ""))
        self.detail.see("1.0")

    def export_report(self):
        if not self.results:
            messagebox.showinfo("提示", "还没有巡检结果，请先执行巡检")
            return
        path = filedialog.asksaveasfilename(
            defaultextension=".html", initialfile=f"巡检报告_{datetime.now():%Y%m%d_%H%M%S}.html",
            filetypes=[("HTML", "*.html")])
        if not path:
            return
        with open(path, "w", encoding="utf-8") as f:
            f.write(inspector.build_html_report(self.results, self._scheme_name))
        messagebox.showinfo("导出完成", f"报告已保存到 {path}")

