"""
NetForge — 网络工程师工作台（独立完整版）
==========================================

六个工作区，全部长在本程序里，不依赖任何外部项目：

  总览      —— 设备/巡检/生成 统计与入口
  设备清单  —— 集中管理设备与凭据（DPAPI 加密落盘），支持 CSV 导入导出
  批量巡检  —— SSH 登录批量执行内置方案（标准/硬件/链路/安全），异常标记 + HTML 报告
  配置生成  —— {{变量}} 模板 × 设备表 → 批量 .cfg（内置 9 个多厂商模板）
  工具箱    —— 子网计算(VLSM) / 端口扫描 / 在线检测 / 密码生成
  命令速查  —— 场景 × 厂商 CLI 备忘检索

依赖：paramiko（SSH 巡检）。运行：python netforge.py
"""
from __future__ import annotations

import os
import random
import string
import sys
import threading
import tkinter as tk
from datetime import datetime
from tkinter import filedialog, messagebox, ttk

if getattr(sys, "frozen", False):
    BASE_DIR = os.path.dirname(os.path.abspath(sys.executable))
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)

from netforge_lib import (
    __version__,
    cheatsheet,
    inspector,
    netcalc,
    portscan,
)
from netforge_lib import generator as gen
from netforge_lib import secrets as sec
from netforge_lib.controller import deploy as deploy_mod
from netforge_lib.controller import intents as intents_mod
from netforge_lib.controller.restapi import ControllerAPI, ControllerState
from netforge_lib.inventory import VENDORS, Device, Inventory, safe_filename

# ── 配色 ──────────────────────────────────────────────────────────────
NAVY = "#0b1f3a"
NAVY2 = "#12294a"
PANEL = "#132a4d"
BG = "#0e1a2e"
LINE = "#1e3a5f"
FG = "#e6ecf5"
MUTED = "#8aa0bd"
ACCENT = "#3b82f6"
GREEN = "#22c55e"
AMBER = "#f59e0b"
RED = "#ef4444"
MONO = ("Consolas", 10)

try:
    import paramiko  # noqa: F401
    HAS_SSH = True
except ImportError:
    HAS_SSH = False


def header(title: str, desc: str, page: Page):
    bar = tk.Frame(page, bg=BG)
    bar.pack(fill=tk.X, padx=16, pady=(12, 6))
    tk.Label(bar, text=title, bg=BG, fg=FG, font=("", 16, "bold")).pack(anchor="w")
    tk.Label(bar, text=desc, bg=BG, fg=MUTED, font=("", 9)).pack(anchor="w")
    tk.Frame(page, bg=ACCENT, height=2).pack(fill=tk.X, padx=16)


class Page(tk.Frame):
    def __init__(self, master, app):
        super().__init__(master, bg=BG)
        self.app = app


# ══════════════════════════════ 总览 ══════════════════════════════
class DashboardPage(Page):
    def __init__(self, master, app):
        super().__init__(master, app)
        header("总览", "NetForge 把设备清单、巡检、配置生成和日常小工具收进同一个工作台", self)
        body = tk.Frame(self, bg=BG)
        body.pack(fill=tk.BOTH, expand=True, padx=16, pady=(0, 12))
        self.grid = tk.Frame(body, bg=BG)
        self.grid.pack(fill=tk.X)
        self.cards: dict[str, tk.Label] = {}
        cards = [
            ("inventory", "设备清单", "inventory"),
            ("inspect", "SSH 批量巡检", "inspect"),
            ("generate", "配置生成", "generate"),
            ("toolbox", "日常工具箱", "toolbox"),
        ]
        for i, (title_, desc, key) in enumerate(cards):
            card = tk.Frame(self.grid, bg=PANEL, highlightbackground=LINE, highlightthickness=1)
            card.grid(row=0, column=i, sticky="ew", padx=6, pady=8)
            self.grid.columnconfigure(i, weight=1)
            tk.Label(card, text=title_, bg=PANEL, fg=FG, font=("", 12, "bold")).pack(anchor="w", padx=14, pady=(12, 0))
            stat = tk.Label(card, text="—", bg=PANEL, fg=ACCENT, font=("", 20, "bold"))
            stat.pack(anchor="w", padx=14)
            self.cards[key] = stat
            tk.Label(card, text=desc, bg=PANEL, fg=MUTED, font=("", 9)).pack(anchor="w", padx=14)
            tk.Button(card, text="打开 →", bg=NAVY2, fg=FG, relief=tk.FLAT,
                      activebackground=NAVY, cursor="hand2",
                      command=lambda k=key: self.app.show(k)).pack(anchor="w", padx=14, pady=(4, 12))
        self.refresh()

    def refresh(self):
        inv = self.app.inventory
        self.cards["inventory"].config(text=str(len(inv.devices)))
        self.cards["generate"].config(text=str(len(gen.list_builtin_templates())))
        ssh = "已就绪" if HAS_SSH else "未安装 paramiko"
        self.cards["inspect"].config(text=ssh, fg=GREEN if HAS_SSH else AMBER)
        self.cards["toolbox"].config(text="4 件")


# ══════════════════════════════ 设备清单 ══════════════════════════════
class InventoryPage(Page):
    def __init__(self, master, app):
        super().__init__(master, app)
        header("设备清单", "所有模块共用的设备与凭据中心；密码经 Windows DPAPI 加密落盘", self)
        body = tk.Frame(self, bg=BG)
        body.pack(fill=tk.BOTH, expand=True, padx=16, pady=(0, 12))

        bar = tk.Frame(body, bg=BG)
        bar.pack(fill=tk.X, pady=(0, 6))
        for text, cmd in (("＋ 添加设备", self.add_dialog), ("✎ 编辑", self.edit_dialog),
                          ("✖ 删除", self.remove_sel), ("导入 CSV…", self.import_csv),
                          ("导出 CSV", self.export_csv)):
            tk.Button(bar, text=text, bg=NAVY2, fg=FG, relief=tk.FLAT,
                      activebackground=NAVY, command=cmd).pack(side=tk.LEFT, padx=(0, 6))
        self.var_count = tk.StringVar()
        tk.Label(bar, textvariable=self.var_count, bg=BG, fg=MUTED, font=("", 9)).pack(side=tk.RIGHT)

        cols = ("name", "host", "port", "vendor", "username", "password", "note")
        wrap = tk.Frame(body, bg=BG)
        wrap.pack(fill=tk.BOTH, expand=True)
        self.tree = ttk.Treeview(wrap, columns=cols, show="headings", height=18)
        for c, t, w in (("name", "名称", 150), ("host", "地址", 140), ("port", "端口", 60),
                        ("vendor", "厂商", 130), ("username", "用户名", 110),
                        ("password", "密码", 90), ("note", "备注", 200)):
            self.tree.heading(c, text=t)
            self.tree.column(c, width=w, anchor="center" if c in ("port", "password") else "w")
        vsb = ttk.Scrollbar(wrap, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)
        self.tree.bind("<Double-1>", lambda e: self.edit_dialog())
        self.refresh()

    def refresh(self):
        self.tree.delete(*self.tree.get_children())
        for i, d in enumerate(self.app.inventory.devices):
            self.tree.insert("", "end", iid=str(i), values=(
                d.display_name, d.host, d.port, VENDORS.get(d.vendor, d.vendor),
                d.username, sec.mask(d.password) if d.password else "", d.note))
        self.var_count.set(f"{len(self.app.inventory.devices)} 台设备")

    def _selected_index(self):
        sel = self.tree.selection()
        return int(sel[0]) if sel else None

    def add_dialog(self):
        self._device_dialog(None)

    def edit_dialog(self):
        idx = self._selected_index()
        if idx is None:
            messagebox.showinfo("提示", "请先选择一台设备")
            return
        self._device_dialog(idx)

    def _device_dialog(self, idx):
        dev = self.app.inventory.devices[idx] if idx is not None else Device(host="")
        dlg = tk.Toplevel(self)
        dlg.title("编辑设备" if idx is not None else "添加设备")
        dlg.configure(bg=PANEL)
        dlg.transient(self)
        dlg.grab_set()
        fields = [("名称", "hostname"), ("地址*", "host"), ("端口", "port"),
                  ("厂商", "vendor"), ("用户名", "username"), ("密码", "password"), ("备注", "note")]
        vars_: dict[str, tk.StringVar] = {}
        for r, (label, key) in enumerate(fields):
            tk.Label(dlg, text=label, bg=PANEL, fg=MUTED, font=("", 9)).grid(
                row=r, column=0, sticky="w", padx=14, pady=(8, 0))
            if key == "vendor":
                w = ttk.Combobox(dlg, state="readonly", width=28,
                                 values=[f"{k} · {v}" for k, v in VENDORS.items()])
                cur = dev.vendor
                keys = list(VENDORS)
                w.current(keys.index(cur) if cur in keys else keys.index("generic"))
                vars_[key] = w
            else:
                w = tk.Entry(dlg, bg=BG, fg=FG, relief=tk.FLAT, width=30,
                             show="•" * 8 if key == "password" and dev.password else "",
                             insertbackground=FG)
                w.insert(0, str(getattr(dev, key) if key != "password" else dev.password or ""))
                vars_[key] = w
            w.grid(row=r, column=1, sticky="ew", padx=14, pady=(8, 0))
        dlg.columnconfigure(1, weight=1)

        def ok():
            vendor_val = vars_["vendor"].get().split(" · ")[0]
            new = Device(
                hostname=vars_["hostname"].get().strip(),
                host=vars_["host"].get().strip(),
                port=int(vars_["port"].get() or 22),
                vendor=vendor_val,
                username=vars_["username"].get().strip(),
                password=vars_["password"].get(),
                note=vars_["note"].get().strip())
            try:
                if idx is None:
                    self.app.inventory.add(new)
                else:
                    self.app.inventory.update(idx, new)
            except (ValueError, IndexError) as e:
                messagebox.showwarning("保存失败", str(e))
                return
            dlg.destroy()
            self.refresh()
            self.app.refresh_dashboard()

        btns = tk.Frame(dlg, bg=PANEL)
        btns.grid(row=len(fields), column=0, columnspan=2, sticky="e", padx=14, pady=14)
        tk.Button(btns, text="取消", bg=NAVY2, fg=FG, relief=tk.FLAT, command=dlg.destroy).pack(side=tk.LEFT, padx=6)
        tk.Button(btns, text="保存", bg=ACCENT, fg="white", relief=tk.FLAT, command=ok).pack(side=tk.LEFT)

    def remove_sel(self):
        idx = self._selected_index()
        if idx is None:
            return
        if messagebox.askyesno("删除", f"确定删除 {self.app.inventory.devices[idx].display_name} 吗？"):
            self.app.inventory.remove(idx)
            self.refresh()
            self.app.refresh_dashboard()

    def import_csv(self):
        path = filedialog.askopenfilename(filetypes=[("CSV", "*.csv"), ("文本", "*.txt"), ("全部", "*.*")])
        if not path:
            return
        with open(path, "r", encoding="utf-8-sig", errors="replace") as f:
            text = f.read()
        added, warns = self.app.inventory.import_csv(text)
        self.refresh()
        self.app.refresh_dashboard()
        msg = f"导入 {added} 台设备"
        if warns:
            msg += "\n" + "\n".join(warns[:8])
        messagebox.showinfo("导入完成", msg)

    def export_csv(self):
        path = filedialog.asksaveasfilename(defaultextension=".csv",
                                            initialfile=f"devices_{datetime.now():%Y%m%d}.csv")
        if not path:
            return
        with open(path, "w", encoding="utf-8-sig", newline="") as f:
            f.write(self.app.inventory.export_csv())
        messagebox.showinfo("导出完成", f"已导出到 {path}")


# ══════════════════════════════ 批量巡检 ══════════════════════════════
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


# ══════════════════════════════ 配置生成 ══════════════════════════════
class GeneratePage(Page):
    def __init__(self, master, app):
        super().__init__(master, app)
        header("配置生成", "内置多厂商模板 × 设备参数表 → 批量生成 .cfg（零残留校验，坏配置不下发）", self)
        body = tk.Frame(self, bg=BG)
        body.pack(fill=tk.BOTH, expand=True, padx=16, pady=(0, 12))

        bar = tk.Frame(body, bg=BG)
        bar.pack(fill=tk.X, pady=(0, 6))
        ttk.Label(bar, text="厂商:", style="H2.TLabel").pack(side=tk.LEFT)
        self.cmb_vendor = ttk.Combobox(bar, state="readonly", width=13)
        self.cmb_vendor["values"] = ["全部", "华为", "新华三", "思科"]
        self.cmb_vendor.current(0)
        self.cmb_vendor.pack(side=tk.LEFT, padx=(6, 10))
        self.cmb_vendor.bind("<<ComboboxSelected>>", lambda e: self._apply_vendor_filter())
        ttk.Label(bar, text="模板:", style="H2.TLabel").pack(side=tk.LEFT)
        self.all_templates = gen.list_builtin_templates()
        self.cmb_tpl = ttk.Combobox(bar, state="readonly", width=52)
        self.cmb_tpl.pack(side=tk.LEFT, padx=(6, 10))
        self.cmb_tpl.bind("<<ComboboxSelected>>", lambda e: self._load_template())
        tk.Button(bar, text="生成到目录…", bg=ACCENT, fg="white", relief=tk.FLAT,
                  activebackground=NAVY2, command=self.generate).pack(side=tk.LEFT, padx=(0, 6))
        tk.Button(bar, text="载入清单设备", bg=NAVY2, fg=FG, relief=tk.FLAT,
                  activebackground=NAVY, command=self.load_inventory).pack(side=tk.LEFT)
        self.var_info = tk.StringVar(value="")
        tk.Label(bar, textvariable=self.var_info, bg=BG, fg=MUTED, font=("", 9)).pack(side=tk.RIGHT)

        pane = tk.PanedWindow(body, orient=tk.HORIZONTAL, bg=LINE, sashwidth=2)
        pane.pack(fill=tk.BOTH, expand=True)

        left = tk.Frame(pane, bg=PANEL)
        pane.add(left)
        tk.Label(left, text="设备参数表（CSV：首行 = 模板变量名）", bg=PANEL, fg=MUTED,
                 font=("", 9)).pack(anchor="w", padx=10, pady=(8, 2))
        self.table_text = tk.Text(left, bg="#0a1526", fg=FG, relief=tk.FLAT, font=MONO,
                                  insertbackground=FG, wrap=tk.NONE)
        self.table_text.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0, 10))

        right = tk.Frame(pane, bg=PANEL)
        pane.add(right)
        tk.Label(right, text="模板预览", bg=PANEL, fg=MUTED, font=("", 9)).pack(anchor="w", padx=10, pady=(8, 2))
        self.tpl_text = tk.Text(right, bg="#0a1526", fg=MUTED, relief=tk.FLAT, font=MONO,
                                insertbackground=FG, wrap=tk.NONE)
        self.tpl_text.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0, 10))
        self._apply_vendor_filter()   # 控件就绪后再填充模板（顺序不能提前）

    def _apply_vendor_filter(self):
        """按厂商过滤模板下拉（92 个模板按厂商分档）。"""
        vendor_key = {"华为": "huawei", "新华三": "h3c", "思科": "cisco"}.get(self.cmb_vendor.get())
        picked = [t for t in self.all_templates
                  if vendor_key is None or t["vendor"] == vendor_key]
        self.tpl_map = {t["name"]: t for t in picked}
        self.cmb_tpl["values"] = list(self.tpl_map)
        if self.tpl_map:
            self.cmb_tpl.current(0)
        self._load_template()

    def _load_template(self):
        t = self.tpl_map.get(self.cmb_tpl.get())
        self.tpl_text.delete("1.0", tk.END)
        if t:
            self.tpl_text.insert(tk.END, t["text"])
            self.var_info.set(f"变量: {', '.join(t['vars'])}")

    def load_inventory(self):
        rows = []
        tpl = self.tpl_map.get(self.cmb_tpl.get())
        var_names = tpl["vars"] if tpl else []
        cols = ["hostname"] + [v for v in var_names if v != "hostname"]
        rows.append(",".join(cols))
        for i, d in enumerate(self.app.inventory.devices, 1):
            sample = {c: "" for c in cols}
            sample["hostname"] = d.hostname or d.host
            for c in cols:
                if c.endswith("_password") and not sample[c]:
                    sample[c] = d.password
            rows.append(",".join(sample[c] for c in cols))
        self.table_text.delete("1.0", tk.END)
        self.table_text.insert(tk.END, "\n".join(rows))
        self.app.set_status("已按设备清单生成参数表骨架（缺的变量请自行补齐）")

    def generate(self):
        t = self.tpl_map.get(self.cmb_tpl.get())
        if not t:
            return
        try:
            _header, devices = gen.parse_device_table(self.table_text.get("1.0", tk.END))
            files = gen.generate(t["text"], devices, filename_rule="hostname")
        except ValueError as e:
            messagebox.showwarning("生成失败", str(e))
            return
        out = filedialog.askdirectory(title="选择输出目录")
        if not out:
            return
        out = os.path.join(out, safe_filename(t["file"].replace("/", "_").replace(".cfg", "")))
        n = gen.write_outputs(out, files)
        messagebox.showinfo("生成完成", f"已生成 {n} 个配置文件到:\n{out}")
        self.app.set_status(f"已生成 {n} 个配置 → {out}")


# ══════════════════════════════ 控制器 ══════════════════════════════
class ControllerPage(Page):
    """意图控制器（OpenDaylight 思路的极简实现）：

      拓扑页   —— LLDP 自动发现 + 画布可视化
      意图页   —— 表单声明意图 → Dry-Run 预览 → 确认下发 → 审计
      API 页   —— 北向 REST 服务开关（供自动化脚本调用）
    """

    def __init__(self, master, app):
        super().__init__(master, app)
        header("控制器中心", "声明意图，控制器翻译成各厂商命令：默认 Dry-Run，确认后才下发（全程审计）", self)
        self.nb = ttk.Notebook(self)
        self.nb.pack(fill=tk.BOTH, expand=True, padx=16, pady=(0, 12))
        self._topo_tab()
        self._intent_tab()
        self._api_tab()

    # ────────── 拓扑 ──────────
    def _topo_tab(self):
        tab = tk.Frame(self.nb, bg=BG)
        self.nb.add(tab, text=" 拓扑发现 ")
        bar = tk.Frame(tab, bg=BG)
        bar.pack(fill=tk.X, pady=(8, 4))
        self.btn_discover = tk.Button(bar, text="从设备清单自动发现拓扑 (LLDP/CDP)",
                                      bg=ACCENT, fg="white", relief=tk.FLAT,
                                      activebackground=NAVY2, command=self.discover)
        self.btn_discover.pack(side=tk.LEFT)
        self.var_topo = tk.StringVar(value="尚未发现")
        tk.Label(bar, textvariable=self.var_topo, bg=BG, fg=MUTED, font=("", 9)).pack(side=tk.LEFT, padx=10)
        self.canvas = tk.Canvas(tab, bg="#0a1526", highlightthickness=0)
        self.canvas.pack(fill=tk.BOTH, expand=True, pady=(4, 0))
        self.canvas.create_text(480, 300, text="点击上方按钮开始发现拓扑\n（需要设备已开启 LLDP/CDP 且可 SSH 登录）",
                                fill=MUTED, font=("", 11), tags="placeholder")

    def discover(self):
        devices = [d for d in self.app.inventory.devices
                   if d.vendor in ("huawei", "h3c", "cisco", "ruijie")]
        if not devices:
            messagebox.showinfo("提示", "设备清单里没有可发现拓扑的设备（需要 huawei/h3c/cisco/ruijie）")
            return
        self.btn_discover.config(state=tk.DISABLED)
        self.var_topo.set(f"发现中… 0/{len(devices)}")

        def worker():
            topo = deploy_mod.discover_topology(devices, progress=self._topo_progress)
            self.app.after(0, lambda: self._topo_done(topo))

        threading.Thread(target=worker, daemon=True).start()

    def _topo_progress(self, done, total):
        self.app.after(0, lambda: self.var_topo.set(f"发现中… {done}/{total}"))

    def _topo_done(self, topo):
        self.btn_discover.config(state=tk.NORMAL)
        self.app.controller_state.topology = topo
        edges = topo.undirected_edges()
        self.var_topo.set(f"{len(topo.nodes)} 台设备 · {len(edges)} 条链路")
        self._draw_topology(topo)

    def _draw_topology(self, topo):
        import math
        self.canvas.delete("all")
        nodes = sorted(topo.nodes)
        if not nodes:
            self.canvas.create_text(480, 300, text="未发现任何邻居（检查 LLDP 是否开启）",
                                    fill=MUTED, font=("", 11))
            return
        w = max(self.canvas.winfo_width(), 900)
        h = max(self.canvas.winfo_height(), 600)
        cx, cy, r = w / 2, h / 2, min(w, h) * 0.36
        pos = {n: (cx + r * math.cos(2 * math.pi * i / len(nodes)),
                   cy + r * math.sin(2 * math.pi * i / len(nodes)))
               for i, n in enumerate(nodes)}
        for a, ai, b, bi in topo.undirected_edges():
            if a in pos and b in pos:
                self.canvas.create_line(*pos[a], *pos[b], fill="#3b5c8a", width=2)
                mx, my = (pos[a][0] + pos[b][0]) / 2, (pos[a][1] + pos[b][1]) / 2
                self.canvas.create_text(mx, my, text=f"{ai}↔{bi}", fill=MUTED, font=("", 8))
        inv = {d.host: d for d in self.app.inventory.devices}
        for n, (x, y) in pos.items():
            dev = next((d for d in inv.values()
                        if (d.hostname or d.host) == n or d.host == n), None)
            color = {"huawei": "#e74c3c", "h3c": "#3498db", "cisco": "#2ecc71",
                     "ruijie": "#f39c12"}.get(dev.vendor if dev else "", "#8aa0bd")
            self.canvas.create_oval(x - 14, y - 14, x + 14, y + 14, fill=color, outline="white", width=2)
            self.canvas.create_text(x, y + 26, text=n, fill=FG, font=("", 9))

    # ────────── 意图下发 ──────────
    def _intent_tab(self):
        tab = tk.Frame(self.nb, bg=BG)
        self.nb.add(tab, text=" 意图下发 ")
        self.intent_items = intents_mod.list_intents()

        bar = tk.Frame(tab, bg=BG)
        bar.pack(fill=tk.X, pady=(8, 4))
        ttk.Label(bar, text="意图类型:", style="H2.TLabel").pack(side=tk.LEFT)
        self.cmb_intent = ttk.Combobox(bar, state="readonly", width=24,
                                       values=[i["title"] for i in self.intent_items])
        self.cmb_intent.current(0)
        self.cmb_intent.pack(side=tk.LEFT, padx=(6, 14))
        self.cmb_intent.bind("<<ComboboxSelected>>", lambda e: self._render_fields())

        ttk.Label(bar, text="目标设备:", style="H2.TLabel").pack(side=tk.LEFT)
        self.cmb_target = ttk.Combobox(bar, state="readonly", width=24)
        self.cmb_target.pack(side=tk.LEFT, padx=(6, 0))

        frm = tk.Frame(tab, bg=BG)
        frm.pack(fill=tk.X, pady=(4, 6))
        self.fields_frame = tk.Frame(frm, bg=BG)
        self.fields_frame.pack(fill=tk.X)

        btns = tk.Frame(tab, bg=BG)
        btns.pack(fill=tk.X, pady=(0, 6))
        tk.Button(btns, text="① Dry-Run 预览（不连接设备）", bg=NAVY2, fg=FG, relief=tk.FLAT,
                  activebackground=NAVY, command=self.dry_run).pack(side=tk.LEFT)
        self.btn_apply = tk.Button(btns, text="② 确认下发", bg=AMBER, fg="#1c1200", relief=tk.FLAT,
                                   activebackground=AMBER, state=tk.DISABLED, command=self.apply)
        self.btn_apply.pack(side=tk.LEFT, padx=(8, 0))
        self.var_intent = tk.StringVar(value="")
        tk.Label(btns, textvariable=self.var_intent, bg=BG, fg=MUTED, font=("", 9)).pack(side=tk.RIGHT)

        self.preview = tk.Text(tab, bg="#0a1526", fg=FG, relief=tk.FLAT, font=MONO, height=18,
                               insertbackground=FG)
        self.preview.pack(fill=tk.BOTH, expand=True)
        self.preview.tag_config("dev", foreground=ACCENT, font=("", 10, "bold"))
        self._render_fields()

    def _current_intent(self):
        title = self.cmb_intent.get()
        return next(i for i in self.intent_items if i["title"] == title)

    def _render_fields(self):
        for w in self.fields_frame.winfo_children():
            w.destroy()
        spec = self._current_intent()
        self.field_vars: dict[str, tk.StringVar] = {}
        for f in spec["fields"]:
            row = tk.Frame(self.fields_frame, bg=BG)
            row.pack(fill=tk.X, pady=2)
            mark = "*" if f["required"] else ""
            tk.Label(row, text=f"{f['label']}{mark}:", bg=BG, fg=MUTED, width=22,
                     anchor="w").pack(side=tk.LEFT)
            var = tk.StringVar(value=f["default"] or "")
            self.field_vars[f["name"]] = var
            if f["type"] == "choice":
                w = ttk.Combobox(row, textvariable=var, state="readonly", width=28,
                                 values=[str(c) for c in f["choices"]])
                if f["choices"]:
                    w.current(0)
            else:
                w = tk.Entry(row, textvariable=var, bg=PANEL, fg=FG, relief=tk.FLAT,
                             width=34, insertbackground=FG)
            w.pack(side=tk.LEFT, ipady=3)
            if f["hint"]:
                tk.Label(row, text=f"  {f['hint']}", bg=BG, fg=MUTED, font=("", 8)).pack(side=tk.LEFT)
        # 目标设备下拉
        self.target_map = {f"{d.display_name} ({d.host}) · {VENDORS.get(d.vendor, d.vendor)}": d
                           for d in self.app.inventory.devices}
        self.cmb_target["values"] = ["(全部设备)"] + list(self.target_map)
        if self.target_map:
            self.cmb_target.current(0)

    def _target_devices(self):
        sel = self.cmb_target.get()
        if sel.startswith("(全部"):
            return list(self.app.inventory.devices)
        dev = self.target_map.get(sel)
        return [dev] if dev else []

    def _collect(self):
        spec = self._current_intent()
        return {name: var.get() for name, var in self.field_vars.items()} | \
               {"_spec_title": spec["title"]}

    def dry_run(self):
        spec = self._current_intent()
        key = spec["key"]
        intent = {k: v for k, v in self._collect().items() if not k.startswith("_")}
        devices = self._target_devices()
        if not devices:
            messagebox.showinfo("提示", "设备清单为空，请先在「设备清单」页添加")
            return
        try:
            plan = deploy_mod.dry_run(key, intent, devices)
        except ValueError as e:
            messagebox.showwarning("参数有误", str(e))
            return
        self._last_plan = (key, intent)
        self.btn_apply.config(state=tk.NORMAL if plan["plan"] else tk.DISABLED)
        self.preview.delete("1.0", tk.END)
        self.preview.insert(tk.END, "── Dry-Run 计划（未连接任何设备）──\n", "dev")
        for entry in plan["plan"]:
            self.preview.insert(tk.END, f"\n■ {entry['device']} ({entry['vendor']})\n", "dev")
            for c in entry["commands"]:
                self.preview.insert(tk.END, f"   {c}\n")
        for s in plan["skipped"]:
            self.preview.insert(tk.END, f"\n⚠ 跳过 {s}\n")
        self.var_intent.set(f"计划覆盖 {len(plan['plan'])} 台设备")

    def apply(self):
        if not getattr(self, "_last_plan", None):
            messagebox.showinfo("提示", "请先执行 Dry-Run 预览")
            return
        key, intent = self._last_plan
        devices = self._target_devices()
        if not messagebox.askyesno(
                "确认下发", "即将通过 SSH 真实下发以上命令。\n请确认已审阅 Dry-Run 预览。继续？"):
            return
        self.btn_apply.config(state=tk.DISABLED)
        self.var_intent.set("下发中…")

        def worker():
            result = deploy_mod.apply(key, intent, devices, progress=self._apply_progress)
            self.app.after(0, lambda: self._apply_done(result))

        threading.Thread(target=worker, daemon=True).start()

    def _apply_progress(self, done, total):
        self.app.after(0, lambda: self.var_intent.set(f"下发中… {done}/{total}"))

    def _apply_done(self, result):
        self.btn_apply.config(state=tk.NORMAL)
        ok = sum(1 for r in result["results"] if r["status"] == "OK")
        warn = sum(1 for r in result["results"] if r["status"] == "WARNING")
        fail = sum(1 for r in result["results"] if r["status"] == "FAILED")
        self.var_intent.set(f"下发完成：OK {ok} · 警告 {warn} · 失败 {fail}")
        self.preview.insert(tk.END, "\n── 下发结果 ──\n", "dev")
        for r in result["results"]:
            mark = {"OK": "✓", "WARNING": "⚠", "FAILED": "✗"}.get(r["status"], "·")
            self.preview.insert(tk.END, f"{mark} {r['device']} → {r['status']}")
            if r["error"]:
                self.preview.insert(tk.END, f"  {r['error']}")
            self.preview.insert(tk.END, "\n")
        self.preview.see(tk.END)

    # ────────── REST API ──────────
    def _api_tab(self):
        tab = tk.Frame(self.nb, bg=BG)
        self.nb.add(tab, text=" REST API ")
        info = (
            "把 NetForge 控制器开放成本机 REST 服务，供自动化脚本/CI 调用。\n\n"
            "  GET  /api/health          健康检查\n"
            "  GET  /api/devices         设备清单（密码打码）\n"
            "  GET  /api/intents         意图目录与表单定义\n"
            "  GET  /api/topology        最近一次发现的拓扑\n"
            "  POST /api/dry-run         意图 → 命令计划（不连设备）\n"
            "  POST /api/apply           真实下发（必须带 \"confirm\": true）\n\n"
            "示例：\n"
            "  curl http://127.0.0.1:8899/api/devices\n"
            "  curl -X POST http://127.0.0.1:8899/api/dry-run -H \"Content-Type: application/json\" \\\n"
            "       -d '{\"intent_key\":\"vlan_deploy\",\"intent\":{\"vlans\":\"10,20\"},"
            "\"device_hosts\":[\"192.0.2.1\"]}'\n")
        tk.Label(tab, text=info, bg=BG, fg=FG, font=MONO, justify="left").pack(
            anchor="w", padx=14, pady=(12, 8))
        row = tk.Frame(tab, bg=BG)
        row.pack(fill=tk.X, padx=14)
        self.var_api = tk.StringVar(value="API 服务未启动")
        tk.Label(row, textvariable=self.var_api, bg=BG, fg=MUTED, font=("", 10)).pack(side=tk.LEFT)
        self.btn_api = tk.Button(row, text="启动 REST 服务 (127.0.0.1:8899)", bg=ACCENT, fg="white",
                                 relief=tk.FLAT, activebackground=NAVY2, command=self.toggle_api)
        self.btn_api.pack(side=tk.LEFT, padx=(16, 0))

    def toggle_api(self):
        if self.app.controller_api.running:
            self.app.controller_api.stop()
            self.var_api.set("API 服务未启动")
            self.btn_api.config(text="启动 REST 服务 (127.0.0.1:8899)", bg=ACCENT)
        else:
            self.app.controller_api.start()
            self.var_api.set("API 服务运行中: http://127.0.0.1:8899")
            self.btn_api.config(text="停止 REST 服务", bg=RED, fg="white")


# ══════════════════════════════ 工具箱 ══════════════════════════════
class ToolboxPage(Page):
    def __init__(self, master, app):
        super().__init__(master, app)
        header("工具箱", "子网计算(VLSM) · 端口扫描 · 在线检测 · 密码生成", self)
        self.nb = ttk.Notebook(self)
        self.nb.pack(fill=tk.BOTH, expand=True, padx=16, pady=(0, 12))
        self._subnet_tab()
        self._scan_tab()
        self._ping_tab()
        self._pwd_tab()

    # ── 子网计算 ──
    def _subnet_tab(self):
        tab = tk.Frame(self.nb, bg=BG)
        self.nb.add(tab, text=" 子网计算 ")
        row = tk.Frame(tab, bg=BG)
        row.pack(fill=tk.X, pady=8)
        tk.Label(row, text="网络 / CIDR:", bg=BG, fg=MUTED).pack(side=tk.LEFT)
        self.ent = tk.Entry(row, bg=PANEL, fg=FG, relief=tk.FLAT, font=MONO, width=30, insertbackground=FG)
        self.ent.insert(0, "192.168.10.130 255.255.255.0")
        self.ent.pack(side=tk.LEFT, padx=(8, 6), ipady=4)
        tk.Button(row, text="计算", bg=ACCENT, fg="white", relief=tk.FLAT, command=self.calc).pack(side=tk.LEFT, padx=(0, 6))
        tk.Label(row, text="VLSM 主机数:", bg=BG, fg=MUTED).pack(side=tk.LEFT, padx=(10, 4))
        self.ent_vlsm = tk.Entry(row, bg=PANEL, fg=FG, relief=tk.FLAT, font=MONO, width=16, insertbackground=FG)
        self.ent_vlsm.insert(0, "100, 50, 20, 5")
        self.ent_vlsm.pack(side=tk.LEFT)
        tk.Button(row, text="VLSM 划分", bg=NAVY2, fg=FG, relief=tk.FLAT, command=self.vlsm).pack(side=tk.LEFT, padx=(6, 0))
        self.out = tk.Text(tab, bg=PANEL, fg=FG, relief=tk.FLAT, font=MONO, height=15, insertbackground=FG)
        self.out.pack(fill=tk.BOTH, expand=True)
        self.out.tag_config("k", foreground=MUTED)
        self.out.tag_config("hl", foreground=ACCENT)
        self.calc()

    def calc(self):
        try:
            info = netcalc.calc_subnet(self.ent.get())
        except ValueError as e:
            messagebox.showwarning("输入有误", str(e))
            return
        self.out.config(state=tk.NORMAL)
        self.out.delete("1.0", tk.END)
        for k, v in (("网络地址", info.network), ("广播地址", info.broadcast),
                     ("子网掩码", info.netmask), ("反掩码", info.wildcard),
                     ("二进制掩码", info.binary_mask), ("前缀", f"/{info.prefix}"),
                     ("可用主机范围", f"{info.first_host} ~ {info.last_host}"),
                     ("可用主机数", f"{info.usable_hosts}（总地址 {info.total_ips}）"),
                     ("类别 / 范围", f"{info.ip_class} · {info.scope}")):
            self.out.insert(tk.END, f"{k:<14}", "k")
            self.out.insert(tk.END, v + "\n", "hl" if k in ("网络地址", "可用主机数") else ())
        self.out.config(state=tk.DISABLED)

    def vlsm(self):
        try:
            base = netcalc.cidr_normalize(self.ent.get())
            counts = [int(x) for x in self.ent_vlsm.get().replace("，", ",").split(",") if x.strip()]
            subs = netcalc.split_vlsm(base, counts)
        except ValueError as e:
            messagebox.showwarning("VLSM 失败", str(e))
            return
        self.out.config(state=tk.NORMAL)
        self.out.delete("1.0", tk.END)
        self.out.insert(tk.END, f"母网 {base} VLSM 划分（从大到小）:\n\n", "hl")
        for i, s in enumerate(subs, 1):
            self.out.insert(tk.END, f"子网{i}: {s.network}/{s.prefix}  可用 {s.usable_hosts} 台  {s.first_host} ~ {s.last_host}\n")
        self.out.config(state=tk.DISABLED)

    # ── 端口扫描 ──
    def _scan_tab(self):
        tab = tk.Frame(self.nb, bg=BG)
        self.nb.add(tab, text=" 端口扫描 ")
        row = tk.Frame(tab, bg=BG)
        row.pack(fill=tk.X, pady=8)
        tk.Label(row, text="主机:", bg=BG, fg=MUTED).pack(side=tk.LEFT)
        self.s_host = tk.Entry(row, bg=PANEL, fg=FG, relief=tk.FLAT, font=MONO, width=18, insertbackground=FG)
        self.s_host.insert(0, "192.0.2.1")
        self.s_host.pack(side=tk.LEFT, padx=(6, 12), ipady=4)
        tk.Label(row, text="端口:", bg=BG, fg=MUTED).pack(side=tk.LEFT)
        self.s_ports = tk.Entry(row, bg=PANEL, fg=FG, relief=tk.FLAT, font=MONO, width=28, insertbackground=FG)
        self.s_ports.insert(0, "22, 23, 80, 443, 830, 3389")
        self.s_ports.pack(side=tk.LEFT, padx=(6, 12), ipady=4)
        self.s_btn = tk.Button(row, text="扫描", bg=ACCENT, fg="white", relief=tk.FLAT, command=self.scan)
        self.s_btn.pack(side=tk.LEFT)
        self.s_count = tk.StringVar()
        tk.Label(row, textvariable=self.s_count, bg=BG, fg=MUTED, font=("", 9)).pack(side=tk.RIGHT)
        self.s_tree = self._make_tree(tab, ("port", "state", "service"),
                                      ("端口", "状态", "常见服务"), (100, 100, 220))
        self.s_tree.tag_configure("open", foreground=GREEN)

    def scan(self):
        try:
            ports = portscan.parse_ports(self.s_ports.get())
        except ValueError as e:
            messagebox.showwarning("输入有误", str(e))
            return
        host = self.s_host.get().strip()
        self.s_btn.config(state=tk.DISABLED)
        self.s_tree.delete(*self.s_tree.get_children())

        def worker():
            results = portscan.scan_ports(host, ports)
            self.app.after(0, lambda: self._scan_done(results))

        threading.Thread(target=worker, daemon=True).start()

    def _scan_done(self, results):
        self.s_btn.config(state=tk.NORMAL)
        opened = 0
        for r in results:
            self.s_tree.insert("", "end", values=(r.port, r.state, r.service),
                               tags=("open",) if r.state == "open" else ())
            opened += r.state == "open"
        self.s_count.set(f"{len(results)} 个端口，开放 {opened}")

    # ── 在线检测 ──
    def _ping_tab(self):
        tab = tk.Frame(self.nb, bg=BG)
        self.nb.add(tab, text=" 在线检测 ")
        row = tk.Frame(tab, bg=BG)
        row.pack(fill=tk.X, pady=8)
        tk.Label(row, text="目标:", bg=BG, fg=MUTED).pack(side=tk.LEFT)
        self.p_target = tk.Entry(row, bg=PANEL, fg=FG, relief=tk.FLAT, font=MONO, width=32, insertbackground=FG)
        self.p_target.insert(0, "192.168.1.0/24")
        self.p_target.pack(side=tk.LEFT, padx=(6, 12), ipady=4)
        self.p_btn = tk.Button(row, text="检测", bg=ACCENT, fg="white", relief=tk.FLAT, command=self.ping)
        self.p_btn.pack(side=tk.LEFT)
        self.p_count = tk.StringVar()
        tk.Label(row, textvariable=self.p_count, bg=BG, fg=MUTED, font=("", 9)).pack(side=tk.RIGHT)
        self.p_tree = self._make_tree(tab, ("ip", "alive", "delay"),
                                      ("IP 地址", "状态", "延迟(ms)"), (180, 100, 120))
        self.p_tree.tag_configure("alive", foreground=GREEN)

    def ping(self):
        try:
            ips = portscan.parse_ip_targets(self.p_target.get())
        except ValueError as e:
            messagebox.showwarning("输入有误", str(e))
            return
        self.p_btn.config(state=tk.DISABLED)
        self.p_tree.delete(*self.p_tree.get_children())

        def worker():
            results = portscan.sweep_hosts(ips)
            self.app.after(0, lambda: self._ping_done(results))

        threading.Thread(target=worker, daemon=True).start()

    def _ping_done(self, results):
        self.p_btn.config(state=tk.NORMAL)
        alive = 0
        for r in results:
            self.p_tree.insert("", "end", values=(r.ip, "在线" if r.alive else "离线",
                                                  f"{r.delay_ms:.0f}" if r.alive else "—"),
                               tags=("alive",) if r.alive else ())
            alive += r.alive
        self.p_count.set(f"{alive}/{len(results)} 台在线")

    # ── 密码生成 ──
    def _pwd_tab(self):
        tab = tk.Frame(self.nb, bg=BG)
        self.nb.add(tab, text=" 密码生成 ")
        row = tk.Frame(tab, bg=BG)
        row.pack(fill=tk.X, pady=8)
        tk.Label(row, text="长度:", bg=BG, fg=MUTED).pack(side=tk.LEFT)
        self.w_len = tk.Spinbox(row, from_=8, to=64, width=5, bg=PANEL, fg=FG,
                                relief=tk.FLAT, insertbackground=FG)
        self.w_len.delete(0, tk.END)
        self.w_len.insert(0, "16")
        self.w_len.pack(side=tk.LEFT, padx=(6, 12))
        self.w_upper = tk.BooleanVar(value=True)
        self.w_lower = tk.BooleanVar(value=True)
        self.w_digit = tk.BooleanVar(value=True)
        self.w_symbol = tk.BooleanVar(value=True)
        for text, var in (("大写", self.w_upper), ("小写", self.w_lower),
                          ("数字", self.w_digit), ("符号", self.w_symbol)):
            ttk.Checkbutton(row, text=text, variable=var, style="TCheckbutton").pack(side=tk.LEFT, padx=(0, 8))
        tk.Button(row, text="生成", bg=ACCENT, fg="white", relief=tk.FLAT, command=self.gen_pwd).pack(side=tk.LEFT)
        self.w_out = tk.Entry(row, bg=PANEL, fg=GREEN, relief=tk.FLAT, font=MONO, width=34,
                              insertbackground=FG, justify="center")
        self.w_out.pack(side=tk.LEFT, padx=(12, 0), ipady=5)

    def gen_pwd(self):
        pools = []
        if self.w_upper.get():
            pools.append(string.ascii_uppercase)
        if self.w_lower.get():
            pools.append(string.ascii_lowercase)
        if self.w_digit.get():
            pools.append(string.digits)
        if self.w_symbol.get():
            pools.append("!@#$%^&*-_=+?")
        if not pools:
            messagebox.showwarning("提示", "请至少选择一种字符集")
            return
        length = max(8, min(64, int(self.w_len.get() or 16)))
        alphabet = "".join(pools)
        pwd = "".join(random.SystemRandom().choice(alphabet) for _ in range(length))
        self.w_out.config(show="")
        self.w_out.delete(0, tk.END)
        self.w_out.insert(0, pwd)

    def _make_tree(self, parent, cols, heads, widths):
        wrap = tk.Frame(parent, bg=BG)
        wrap.pack(fill=tk.BOTH, expand=True, pady=(0, 8))
        tree = ttk.Treeview(wrap, columns=cols, show="headings", height=14)
        for c, t, w in zip(cols, heads, widths):
            tree.heading(c, text=t)
            tree.column(c, width=w, anchor="center")
        vsb = ttk.Scrollbar(wrap, orient=tk.VERTICAL, command=tree.yview)
        tree.configure(yscrollcommand=vsb.set)
        tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)
        return tree


# ══════════════════════════════ 命令速查 ══════════════════════════════
class CheatPage(Page):
    def __init__(self, master, app):
        super().__init__(master, app)
        header("命令速查", "场景 × 厂商 CLI 备忘；输入关键字即时过滤，双击行复制", self)
        body = tk.Frame(self, bg=BG)
        body.pack(fill=tk.BOTH, expand=True, padx=16, pady=(0, 12))
        row = tk.Frame(body, bg=BG)
        row.pack(fill=tk.X, pady=(2, 6))
        tk.Label(row, text="搜索:", bg=BG, fg=MUTED).pack(side=tk.LEFT)
        self.ent = tk.Entry(row, bg=PANEL, fg=FG, relief=tk.FLAT, font=MONO, width=40, insertbackground=FG)
        self.ent.pack(side=tk.LEFT, padx=(6, 0), ipady=4)
        self.ent.bind("<KeyRelease>", lambda e: self.refresh())
        self.var_count = tk.StringVar()
        tk.Label(row, textvariable=self.var_count, bg=BG, fg=MUTED, font=("", 9)).pack(side=tk.RIGHT)
        cols = ("scene", "vendor", "title", "cmd")
        wrap = tk.Frame(body, bg=BG)
        wrap.pack(fill=tk.BOTH, expand=True, pady=(6, 0))
        self.tree = ttk.Treeview(wrap, columns=cols, show="headings", height=18)
        for c, t, w in (("scene", "场景", 110), ("vendor", "厂商", 130),
                        ("title", "标题", 180), ("cmd", "命令 / 说明", 440)):
            self.tree.heading(c, text=t)
            self.tree.column(c, width=w, anchor="w")
        vsb = ttk.Scrollbar(wrap, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)
        self.tree.bind("<Double-1>", self._copy)
        self.refresh()

    def refresh(self):
        rows = cheatsheet.search(self.ent.get())
        self.tree.delete(*self.tree.get_children())
        for scene, vendor, title, cmd in rows:
            self.tree.insert("", "end", values=(scene, vendor, title, cmd))
        self.var_count.set(f"{len(rows)} 条")

    def _copy(self, _ev=None):
        sel = self.tree.selection()
        if not sel:
            return
        self.app.clipboard_clear()
        self.app.clipboard_append(self.tree.item(sel[0], "values")[3])
        self.app.set_status("已复制到剪贴板")


# ══════════════════════════════ 应用壳 ══════════════════════════════
class NetForgeApp(tk.Tk):
    PAGES = [
        ("dashboard", "总览", "🏠"),
        ("inventory", "设备清单", "🗂"),
        ("controller", "控制器", "🕸"),
        ("inspect", "批量巡检", "🔎"),
        ("generate", "配置生成", "🛠"),
        ("toolbox", "工具箱", "🧰"),
        ("cheat", "命令速查", "📖"),
    ]

    def __init__(self):
        super().__init__()
        self.title(f"NetForge — 网络工程师工作台 v{__version__}")
        self.geometry("1080x740")
        self.minsize(980, 640)
        self.configure(bg=BG)
        self.option_add("*Font", ("Microsoft YaHei UI", 10))
        self._style()
        ico = os.path.join(BASE_DIR, "assets", "icon.ico")
        if os.path.isfile(ico):
            try:
                self.iconbitmap(ico)
            except Exception:
                pass

        self.inventory = Inventory()
        self.controller_state = ControllerState(self.inventory)
        self.controller_api = ControllerAPI(self.controller_state)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        top = tk.Frame(self, bg=NAVY, height=56)
        top.pack(fill=tk.X)
        top.pack_propagate(False)
        tk.Label(top, text="⛏", bg=NAVY, fg=ACCENT, font=("", 18)).pack(side=tk.LEFT, padx=(16, 8))
        tk.Label(top, text="NetForge", bg=NAVY, fg=FG, font=("", 15, "bold")).pack(side=tk.LEFT)
        tk.Label(top, text="网络工程师工作台", bg=NAVY, fg=MUTED, font=("", 10)).pack(side=tk.LEFT, padx=(10, 0))
        self.var_status = tk.StringVar(value="就绪")
        tk.Label(top, textvariable=self.var_status, bg=NAVY, fg=MUTED, font=("", 9)).pack(side=tk.RIGHT, padx=14)

        main = tk.Frame(self, bg=BG)
        main.pack(fill=tk.BOTH, expand=True)
        rail = tk.Frame(main, bg=NAVY, width=168)
        rail.pack(side=tk.LEFT, fill=tk.Y)
        rail.pack_propagate(False)
        self._nav_buttons = {}
        for key, name, icon in self.PAGES:
            btn = tk.Label(rail, text=f"  {icon}  {name}", bg=NAVY, fg=MUTED, font=("", 11),
                           anchor="w", pady=10, cursor="hand2")
            btn.pack(fill=tk.X, padx=8, pady=(6 if key == "dashboard" else 0))
            btn.bind("<Button-1>", lambda e, k=key: self.show(k))
            self._nav_buttons[key] = btn
        tk.Frame(rail, bg=LINE, height=1).pack(fill=tk.X, padx=8, pady=6)
        tk.Label(rail, text=f"v{__version__}", bg=NAVY, fg=MUTED, font=("", 8)).pack(side=tk.BOTTOM, pady=8)

        cls_map = {"dashboard": DashboardPage, "inventory": InventoryPage,
                   "controller": ControllerPage,
                   "inspect": InspectPage, "generate": GeneratePage,
                   "toolbox": ToolboxPage, "cheat": CheatPage}
        self.pages = {key: cls(main, self) for key, cls in cls_map.items()}
        self.show("dashboard")

    def _style(self):
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except Exception:
            pass
        style.configure("Treeview", background=PANEL, foreground=FG, fieldbackground=PANEL,
                        rowheight=26, borderwidth=0)
        style.configure("Treeview.Heading", background=NAVY2, foreground=FG, borderwidth=0)
        style.map("Treeview", background=[("selected", NAVY2)])
        style.configure("TCheckbutton", background=BG, foreground=FG)
        style.configure("TNotebook", background=BG, borderwidth=0)
        style.configure("TNotebook.Tab", background=NAVY, foreground=MUTED, padding=(14, 6))
        style.map("TNotebook.Tab", background=[("selected", PANEL)], foreground=[("selected", FG)])
        style.configure("H2.TLabel", background=BG, foreground=MUTED, font=("", 10))

    def show(self, key: str):
        for k, page in self.pages.items():
            if k == key:
                page.place(relx=0, rely=0, relwidth=1, relheight=1)
            else:
                page.place_forget()
        for k, btn in self._nav_buttons.items():
            btn.config(bg=ACCENT if k == key else NAVY, fg="white" if k == key else MUTED)
        if key == "dashboard":
            self.pages["dashboard"].refresh()
        if key == "inventory":
            self.pages["inventory"].refresh()
        if key == "inspect":
            self.pages["inspect"].refresh_devices()
        self.set_status("就绪")

    def refresh_dashboard(self):
        self.pages["dashboard"].refresh()

    def set_status(self, text: str):
        self.var_status.set(text)


    def _on_close(self):
        try:
            self.controller_api.stop()
        except Exception:
            pass
        self.destroy()


def main() -> None:
    app = NetForgeApp()
    app.mainloop()


if __name__ == "__main__":
    main()
