"""设备清单工作区页面。"""
from __future__ import annotations

import tkinter as tk
from datetime import datetime
from tkinter import filedialog, messagebox, ttk

from netforge.lib import secrets as sec
from netforge.lib.inventory import VENDORS, Device
from netforge.theme import (
    ACCENT, BG, FG, MUTED, NAVY, NAVY2, PANEL,
)
from netforge.widgets import Page, page_header


def header(title, desc, page):
    page_header(page, title, desc)
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


