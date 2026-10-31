"""批量巡检工作区页面。"""
from __future__ import annotations

import threading
import tkinter as tk
from datetime import datetime
from tkinter import filedialog, messagebox, ttk

from netforge.lib import HAS_SSH, inspector
from netforge.lib.inventory import VENDORS
from netforge.theme import (
    ACCENT, AMBER, BG, FG, LINE, MUTED, NAVY, NAVY2, PANEL, MONO,
)
from netforge.widgets import Page, page_header


def header(title, desc, page):
    page_header(page, title, desc)
class InspectPage(Page):
    def __init__(self, master, app):
        super().__init__(master, app)
        header("SSH 批量巡检", "从设备清单勾选目标 → 选方案 → 并发执行 → 异常标记 → 导出 HTML 报告", self)
        body = tk.Frame(self, bg=BG)
        body.pack(fill=tk.BOTH, expand=True, padx=16, pady=(0, 12))

        top = tk.Frame(body, bg=BG)
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
        self.btn_run = tk.Button(top, text="开始巡检", bg=ACCENT, fg="white", relief=tk.FLAT,
                                 activebackground=NAVY2, command=self.start)
        self.btn_run.pack(side=tk.LEFT)
        tk.Button(top, text="导出报告", bg=NAVY2, fg=FG, relief=tk.FLAT,
                  activebackground=NAVY, command=self.export_report).pack(side=tk.LEFT, padx=(6, 0))
        self.var_count = tk.StringVar(value="")
        tk.Label(top, textvariable=self.var_count, bg=BG, fg=MUTED, font=("", 9)).pack(side=tk.RIGHT)
        if not HAS_SSH:
            tk.Label(body, text="⚠ 未安装 paramiko：pip install paramiko 后重启即可启用巡检",
                     bg=BG, fg=AMBER, font=("", 10)).pack(anchor="w", pady=(0, 6))

        pane = tk.PanedWindow(body, orient=tk.HORIZONTAL, bg=LINE, sashwidth=2)
        pane.pack(fill=tk.BOTH, expand=True)

        # 左：设备勾选
        left = tk.Frame(pane, bg=PANEL)
        pane.add(left, width=300)
        tk.Label(left, text="目标设备（勾选）", bg=PANEL, fg=MUTED, font=("", 9)).pack(anchor="w", padx=10, pady=(8, 2))
        self.dev_list = tk.Frame(left, bg=PANEL)
        self.dev_list.pack(fill=tk.BOTH, expand=True, padx=10)
        self.dev_vars: dict[str, tk.BooleanVar] = {}

        # 右：结果
        right = tk.Frame(pane, bg=PANEL)
        pane.add(right)
        cols = ("host", "status", "critical", "warn", "cost")
        wrap = tk.Frame(right, bg=PANEL)
        wrap.pack(fill=tk.BOTH, expand=True, padx=10, pady=(8, 4))
        self.tree = ttk.Treeview(wrap, columns=cols, show="headings", height=9)
        for c, t, w in (("host", "设备", 160), ("status", "状态", 110), ("critical", "严重", 60),
                        ("warn", "告警", 60), ("cost", "耗时", 80)):
            self.tree.heading(c, text=t)
            self.tree.column(c, width=w, anchor="center")
        vsb = ttk.Scrollbar(wrap, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)
        self.tree.bind("<<TreeviewSelect>>", self._show_detail)
        self.detail = tk.Text(right, bg="#0a1526", fg=FG, relief=tk.FLAT, font=MONO, height=12,
                              insertbackground=FG)
        self.detail.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0, 10))
        self.results: list[inspector.DeviceResult] = []
        self.refresh_devices()

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
            cb.configure(command=lambda k=key, v=var: None)
            self.dev_vars[key] = var

    def on_inventory_changed(self):
        self.refresh_devices()

    def start(self):
        if not HAS_SSH:
            messagebox.showwarning("缺依赖", "请先安装 paramiko：pip install paramiko")
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
        self.btn_run.config(state=tk.DISABLED)
        self.tree.delete(*self.tree.get_children())
        self.detail.delete("1.0", tk.END)
        self.var_count.set(f"巡检中… 0/{len(picked)}")

        def worker():
            results, skipped = inspector.run_batch(picked, scheme, workers=workers,
                                                   progress=self._progress)
            self.app.after(0, lambda: self._done(results, scheme_name, skipped))

        threading.Thread(target=worker, daemon=True).start()

    def _progress(self, done, total):
        self.app.after(0, lambda: self.var_count.set(f"巡检中… {done}/{total}"))

    def _done(self, results, scheme_name, skipped=None):
        self.btn_run.config(state=tk.NORMAL)
        self.results = results
        self._scheme_name = scheme_name
        for i, r in enumerate(results):
            self.tree.insert("", "end", iid=str(i), values=(
                r.host, r.status, r.critical_count, len(r.anomalies), f"{r.cost_ms} ms"))
        summary = " ".join(f"{k}:{v}" for k, v in sorted(
            {s: sum(1 for r in results if r.status == s)
             for s in {r.status for r in results}}.items()))
        note = f" · 跳过 {len(skipped)} 台（{scheme_name} 无该厂商命令集）" if skipped else ""
        self.var_count.set(f"完成：{len(results)} 台 · {summary}{note}")
        if skipped:
            self.app.set_status("已跳过: " + "、".join(skipped[:5]) + ("…" if len(skipped) > 5 else ""))
        if results:
            self.tree.selection_set("0")

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
                self.detail.insert(tk.END, f"  [错误] {c.error}\n")
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


