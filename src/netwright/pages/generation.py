"""配置生成工作区页面。"""
from __future__ import annotations

import os
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from netwright.lib import generator as gen
from netwright.lib.inventory import safe_filename
from netwright.theme import FONT_MONO, theme
from netwright.widgets import (Page, page_header, WButton)


def header(title, desc, page):
    page_header(page, title, desc)


class GeneratePage(Page):
    def __init__(self, master, app):
        super().__init__(master, app)
        header("配置生成", "内置多厂商模板 × 设备参数表 → 批量生成 .cfg（零残留校验，坏配置不下发）", self)
        body = tk.Frame(self, bg=theme.bg)
        body.pack(fill=tk.BOTH, expand=True, padx=16, pady=(0, 12))

        bar = tk.Frame(body, bg=theme.bg)
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
        WButton(bar, text="生成到目录…", bg=theme.accent, fg="white", relief=tk.FLAT,
                  activebackground=theme.nav2, command=self.generate).pack(side=tk.LEFT, padx=(0, 6))
        WButton(bar, text="载入清单设备", bg=theme.nav2, fg=theme.fg, relief=tk.FLAT,
                  activebackground=theme.nav1, command=self.load_inventory).pack(side=tk.LEFT)
        self.var_info = tk.StringVar(value="")
        tk.Label(bar, textvariable=self.var_info, bg=theme.bg, fg=theme.muted, font=("", 9)).pack(side=tk.RIGHT)

        pane = tk.PanedWindow(body, orient=tk.HORIZONTAL, bg=theme.line, sashwidth=2)
        pane.pack(fill=tk.BOTH, expand=True)

        left = tk.Frame(pane, bg=theme.panel)
        pane.add(left)
        tk.Label(left, text="设备参数表（CSV：首行 = 模板变量名）", bg=theme.panel, fg=theme.muted,
                 font=("", 9)).pack(anchor="w", padx=10, pady=(8, 2))
        self.table_text = tk.Text(left, bg=theme.code_bg, fg=theme.fg, relief=tk.FLAT, font=FONT_MONO,
                                  insertbackground=theme.fg, wrap=tk.NONE)
        self.table_text.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0, 10))

        right = tk.Frame(pane, bg=theme.panel)
        pane.add(right)
        tk.Label(right, text="模板预览", bg=theme.panel, fg=theme.muted, font=("", 9)).pack(anchor="w", padx=10, pady=(8, 2))
        self.tpl_text = tk.Text(right, bg=theme.code_bg, fg=theme.muted, relief=tk.FLAT, font=FONT_MONO,
                                insertbackground=theme.fg, wrap=tk.NONE)
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

    def export_all_templates(self):
        """批量导出：把内置模板库全部 .cfg 按目录结构写入用户选择目录。"""
        from netwright.widgets import toast
        tpls = gen.list_builtin_templates()
        if not tpls:
            toast(self.app, "模板库为空", "warn")
            return
        out = filedialog.askdirectory(title="选择模板导出目录")
        if not out:
            return
        n = 0
        for t in tpls:
            rel = t["file"].replace("/", os.sep)
            dest = os.path.join(out, "templates", rel)
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            with open(dest, "w", encoding="utf-8", newline=chr(10)) as f:
                f.write(t["text"])
            n += 1
        # 清单文件也一并导出（NADT 兼容格式）
        import shutil
        src_manifest = os.path.join(os.path.dirname(__file__), "..", "..",
                                    "templates", "library.json")
        if os.path.isfile(src_manifest):
            shutil.copy(src_manifest, os.path.join(out, "templates", "library.json"))
        toast(self.app, f"已导出 {n} 个模板 → {out}", "ok")
        self.app.set_status(f"已导出 {n} 个模板 → {out}")

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

