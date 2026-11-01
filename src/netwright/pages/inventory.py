"""设备清单工作区页面。"""
from __future__ import annotations

import tkinter as tk
from datetime import datetime
from tkinter import filedialog, messagebox, ttk

from netwright.lib import portscan, secrets as sec
from netwright.lib.inventory import VENDORS, Device
from netwright.theme import theme
from netwright.widgets import (Page, page_header)


def header(title, desc, page):
    page_header(page, title, desc)


class InventoryPage(Page):
    def __init__(self, master, app):
        super().__init__(master, app)
        header("设备清单", "所有模块共用的设备与凭据中心；密码经 Windows DPAPI 加密落盘", self)
        body = tk.Frame(self, bg=theme.bg)
        body.pack(fill=tk.BOTH, expand=True, padx=16, pady=(0, 12))

        bar = tk.Frame(body, bg=theme.bg)
        bar.pack(fill=tk.X, pady=(0, 6))
        for text, cmd in (("＋ 添加设备", self.add_dialog), ("✎ 编辑", self.edit_dialog),
                          ("✖ 删除", self.remove_sel), ("导入 CSV…", self.import_csv),
                          ("导出 CSV", self.export_csv), ("⚡ 在线检测", self.alive_check)):
            tk.Button(bar, text=text, bg=theme.nav2, fg=theme.fg, relief=tk.FLAT,
                      activebackground=theme.nav1, command=cmd).pack(side=tk.LEFT, padx=(0, 6))
        self.var_count = tk.StringVar()
        tk.Label(bar, textvariable=self.var_count, bg=theme.bg, fg=theme.muted, font=("", 9)).pack(side=tk.RIGHT)

        cols = ("name", "host", "port", "vendor", "alive", "username", "password", "note")
        wrap = tk.Frame(body, bg=theme.bg)
        wrap.pack(fill=tk.BOTH, expand=True)
        self.tree = ttk.Treeview(wrap, columns=cols, show="headings", height=18)
        for c, t, w in (("name", "名称", 140), ("host", "地址", 130), ("port", "端口", 55),
                        ("vendor", "厂商", 120), ("alive", "在线", 65),
                        ("username", "用户名", 100),
                        ("password", "密码", 80), ("note", "备注", 170)):
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
            alive = getattr(d, "_alive", None)
            alive_text = "—" if alive is None else ("在线" if alive else "离线")
            self.tree.insert("", "end", iid=str(i), values=(
                d.display_name, d.host, d.port, VENDORS.get(d.vendor, d.vendor),
                alive_text,
                d.username, sec.mask(d.password) if d.password else "", d.note),
                tags=("ok",) if alive is True else ("warn",) if alive is False else ())

        self.tree.tag_configure("ok", foreground=theme.ok)
        self.tree.tag_configure("warn", foreground=theme.warn)
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
        dlg.configure(bg=theme.panel)
        dlg.transient(self)
        dlg.grab_set()
        fields = [("名称", "hostname"), ("地址*", "host"), ("端口", "port"),
                  ("厂商", "vendor"), ("用户名", "username"), ("密码", "password"), ("备注", "note")]
        vars_: dict[str, tk.StringVar] = {}
        for r, (label, key) in enumerate(fields):
            tk.Label(dlg, text=label, bg=theme.panel, fg=theme.muted, font=("", 9)).grid(
                row=r, column=0, sticky="w", padx=14, pady=(8, 0))
            if key == "vendor":
                w = ttk.Combobox(dlg, state="readonly", width=28,
                                 values=[f"{k} · {v}" for k, v in VENDORS.items()])
                cur = dev.vendor
                keys = list(VENDORS)
                w.current(keys.index(cur) if cur in keys else keys.index("generic"))
                vars_[key] = w
            else:
                w = tk.Entry(dlg, bg=theme.bg, fg=theme.fg, relief=tk.FLAT, width=30,
                             show="•" * 8 if key == "password" and dev.password else "",
                             insertbackground=theme.fg)
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

        btns = tk.Frame(dlg, bg=theme.panel)
        btns.grid(row=len(fields), column=0, columnspan=2, sticky="e", padx=14, pady=14)
        tk.Button(btns, text="取消", bg=theme.nav2, fg=theme.fg, relief=tk.FLAT, command=dlg.destroy).pack(side=tk.LEFT, padx=6)
        tk.Button(btns, text="保存", bg=theme.accent, fg="white", relief=tk.FLAT, command=ok).pack(side=tk.LEFT)

    def remove_sel(self):
        idx = self._selected_index()
        if idx is None:
            return
        if messagebox.askyesno("删除", f"确定删除 {self.app.inventory.devices[idx].display_name} 吗？"):
            self.app.inventory.remove(idx)
            self.refresh()
            self.app.refresh_dashboard()

    def alive_check(self):
        """一键在线检测：并发 ping 清单设备，回填在线状态。"""
        import threading
        if not self.app.inventory.devices:
            messagebox.showinfo("提示", "清单为空")
            return
        for d in self.app.inventory.devices:
            d._alive = None
        self.refresh()
        self.app.set_status("在线检测中…")

        def worker():
            try:
                for d in self.app.inventory.devices:
                    d._alive = portscan.ping_host(d.host, timeout_ms=800).alive
                self.app.after(0, self.refresh)
            except tk.TclError:
                pass  # 窗口已关闭，放弃回调

        threading.Thread(target=worker, daemon=True).start()

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

