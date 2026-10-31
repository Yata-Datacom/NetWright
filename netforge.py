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
            results = inspector.run_batch(picked, scheme, workers=workers,
                                          progress=self._progress)
            self.app.after(0, lambda: self._done(results, scheme_name))

        threading.Thread(target=worker, daemon=True).start()

    def _progress(self, done, total):
        self.app.after(0, lambda: self.var_count.set(f"巡检中… {done}/{total}"))

    def _done(self, results, scheme_name):
        self.btn_run.config(state=tk.NORMAL)
        self.results = results
        self._scheme_name = scheme_name
        for i, r in enumerate(results):
            self.tree.insert("", "end", iid=str(i), values=(
                r.host, r.status, r.critical_count, len(r.anomalies), f"{r.cost_ms} ms"))
        self.var_count.set(f"完成：{len(results)} 台 · " +
                           " ".join(f"{k}:{v}" for k, v in sorted(
                               {s: sum(1 for r in results if r.status == s)
                                for s in {r.status for r in results}}.items())))
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
        self._apply_vendor_filter()
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
        self._load_template()

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


def main() -> None:
    app = NetForgeApp()
    app.mainloop()


if __name__ == "__main__":
    main()
