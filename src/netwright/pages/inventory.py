"""设备清单工作区页面（资源列表标杆：Drawer 编辑 + 状态 Tag + 批量操作浮层）。"""
from __future__ import annotations

import threading
import tkinter as tk
from datetime import datetime
from tkinter import filedialog, messagebox, ttk

from netwright.lib import portscan, secrets as sec
from netwright.lib.errors import friendly_error
from netwright.lib.inventory import VENDORS, Device
from netwright.theme import FONT_SMALL, theme
from netwright.widgets import (
    Drawer, Page, WButton, make_table, page_header, toast, zebra,
)


def header(title, desc, page):
    page_header(page, title, desc, "资源 / 设备清单")


class InventoryPage(Page):
    def __init__(self, master, app):
        super().__init__(master, app)
        header("设备清单", "所有模块共用的设备与凭据中心；密码经 Windows DPAPI 加密落盘", self)
        body = tk.Frame(self, bg=theme.bg)
        body.pack(fill=tk.BOTH, expand=True, padx=16, pady=(0, 12))

        # ── 工具栏（ghost 按钮）──
        bar = tk.Frame(body, bg=theme.bg)
        bar.pack(fill=tk.X, pady=(0, 8))
        for text, cmd in (("＋ 添加设备", self.add_dialog), ("✎ 编辑", self.edit_dialog),
                          ("✖ 删除", self.remove_sel), ("导入 CSV…", self.import_csv),
                          ("导出 CSV", self.export_csv), ("⚡ 在线检测", self.alive_check),
                          ("🔌 测试连接", self.test_connections),
                          ("🗄 备份配置", self.backup_configs),
                          ("🗂 备份历史", self.show_backups)):
            WButton(bar, text=text, command=cmd).pack(side=tk.LEFT, padx=(0, 8))
        self.var_count = tk.StringVar()
        tk.Label(bar, textvariable=self.var_count, bg=theme.bg, fg=theme.muted,
                 font=FONT_SMALL).pack(side=tk.RIGHT)

        # ── 表格（行高 40 由全局样式；斑马纹）──
        cols = ("name", "host", "port", "vendor", "protocol", "alive",
                "username", "password", "note")
        heads = {"name": "名称", "host": "地址", "port": "端口", "vendor": "厂商",
                 "protocol": "协议", "alive": "在线", "username": "用户名",
                 "password": "密码", "note": "备注"}
        widths = {"name": 140, "host": 130, "port": 55, "vendor": 125,
                  "protocol": 70, "alive": 80, "username": 100,
                  "password": 80, "note": 150}
        self.table_wrap, self.tree = make_table(
            body, list(cols), heads, widths, height=18, selectmode="extended")
        self.table_wrap.pack(fill=tk.BOTH, expand=True)
        self.tree.tag_configure("ok", foreground=theme.ok)
        self.tree.tag_configure("warn", foreground=theme.warn)
        self.tree.tag_configure("even", background=theme.panel)
        self.tree.tag_configure("odd", background=theme.panel_alt)
        self.tree.bind("<Double-1>", lambda e: self.edit_dialog())
        self.tree.bind("<<TreeviewSelect>>", lambda e: self._update_batchbar())

        # ── 空状态：给三条最短路径，而不是只留一句话 ──
        self.empty = tk.Frame(body, bg=theme.bg)
        box = tk.Frame(self.empty, bg=theme.panel, highlightbackground=theme.line,
                       highlightthickness=1)
        box.pack(expand=True)
        tk.Label(box, text="还没有设备", bg=theme.panel, fg=theme.fg,
                 font=("Microsoft YaHei UI", 14, "bold")).pack(pady=(28, 4))
        tk.Label(box, text="三条路，选一条开始：", bg=theme.panel, fg=theme.muted,
                 font=FONT_SMALL).pack()
        row = tk.Frame(box, bg=theme.panel)
        row.pack(pady=(14, 6))
        WButton(row, text="① 载入演示数据", bg=theme.accent_soft,
                command=self._load_demo).pack(side=tk.LEFT, padx=6)
        WButton(row, text="② 手动添加设备", command=self.add_dialog).pack(side=tk.LEFT, padx=6)
        WButton(row, text="③ 导入 CSV 台账", command=self.import_csv).pack(side=tk.LEFT, padx=6)
        tk.Label(box, text="演示数据使用 192.0.2.x 文档网段，不会连到任何真实地址",
                 bg=theme.panel, fg=theme.faint, font=FONT_SMALL).pack(pady=(0, 24))

        # ── 批量操作浮层（多选时出现）──
        self.batchbar = tk.Frame(body, bg=theme.accent_soft,
                                 highlightbackground=theme.accent, highlightthickness=1)
        self.batch_count = tk.StringVar()
        tk.Label(self.batchbar, textvariable=self.batch_count, bg=theme.accent_soft,
                 fg=theme.fg, font=FONT_SMALL).pack(side=tk.LEFT, padx=(12, 8))
        WButton(self.batchbar, text="⚡ 批量在线检测",
                command=self.alive_check).pack(side=tk.LEFT, padx=4, pady=6)
        WButton(self.batchbar, text="✖ 批量删除",
                command=self.remove_sel).pack(side=tk.LEFT, padx=4, pady=6)
        tk.Button(self.batchbar, text="×", bg=theme.accent_soft, fg=theme.muted,
                  relief=tk.FLAT, command=self._clear_sel, cursor="hand2").pack(
            side=tk.RIGHT, padx=8)
        self.batchbar.pack_forget()

        self.refresh()

    # ── 渲染 ──
    def refresh(self):
        # 自动刷新每 10 秒跑一次：先记住选中行，刷新后还原（否则用户勾选会被"吞掉"）
        keep = self._selected_indices()
        self.tree.delete(*self.tree.get_children())
        devices = self.app.inventory.devices
        for i, d in enumerate(devices):
            alive = getattr(d, "_alive", None)
            alive_text = "—" if alive is None else ("● 在线" if alive else "○ 离线")
            self.tree.insert("", "end", iid=str(i), values=(
                d.display_name, d.host, d.port, VENDORS.get(d.vendor, d.vendor),
                d.protocol.upper(), alive_text,
                d.username, sec.mask(d.password) if d.password else "", d.note),
                tags=("ok",) if alive is True else ("warn",) if alive is False else ())
            zebra(self.tree, str(i), i)
        for index in keep:
            if index < len(devices):
                self.tree.selection_add(str(index))
        self.tree.tag_configure("ok", foreground=theme.ok)
        self.tree.tag_configure("warn", foreground=theme.warn)
        self.var_count.set(f"{len(devices)} 台设备")
        self._toggle_empty(not devices)
        self._update_batchbar()

    def _toggle_empty(self, show_empty: bool):
        if show_empty:
            self.empty.pack(fill=tk.BOTH, expand=True)
            self.table_wrap.pack_forget()
        else:
            self.empty.pack_forget()
            self.table_wrap.pack(fill=tk.BOTH, expand=True)

    # ── 选择/批量 ──
    def _selected_indices(self) -> list[int]:
        return sorted(int(s) for s in self.tree.selection())

    def _selected_devices(self) -> list:
        devices = self.app.inventory.devices
        return [devices[i] for i in self._selected_indices() if 0 <= i < len(devices)]

    def _selected_index(self):
        idx = self._selected_indices()
        return idx[0] if idx else None

    def _update_batchbar(self):
        sel = self._selected_indices()
        if len(sel) > 1:
            self.batch_count.set(f"已选 {len(sel)} 台")
            self.batchbar.pack_forget()
            self.batchbar.pack(fill=tk.X, side=tk.BOTTOM, before=self.table_wrap,
                               pady=(6, 0))
        else:
            self.batchbar.pack_forget()

    def _clear_sel(self):
        self.tree.selection_remove(*self.tree.selection())

    def remove_sel(self):
        sel = self._selected_indices()
        if not sel:
            return
        if len(sel) == 1:
            msg = f"确定删除 {self.app.inventory.devices[sel[0]].display_name} 吗？"
        else:
            msg = f"确定删除选中的 {len(sel)} 台设备吗？"
        if messagebox.askyesno("删除", msg):
            for i in reversed(sel):
                self.app.inventory.remove(i)
            self.refresh()
            self.app.refresh_dashboard()
            toast(self.app, f"已删除 {len(sel)} 台设备", "ok")

    def alive_check(self):
        """一键在线检测：并发 ping，回填状态；批量操作浮层复用同一入口。"""
        import threading
        if not self.app.inventory.devices:
            toast(self.app, "清单为空", "warn")
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

    # ── Drawer 编辑表单 ──
    def add_dialog(self):
        self._device_drawer(None)

    def edit_dialog(self):
        idx = self._selected_index()
        if idx is None:
            toast(self.app, "请先选择一台设备（双击行可直接编辑）", "warn")
            return
        self._device_drawer(idx)

    def _device_drawer(self, idx):
        dev = self.app.inventory.devices[idx] if idx is not None else Device(host="")
        is_edit = idx is not None
        drawer = Drawer(self, "编辑设备" if is_edit else "添加设备", width=560)
        body = drawer.body

        tk.Label(body, text="基本配置", bg=theme.panel, fg=theme.muted,
                 font=FONT_SMALL).pack(anchor="w", pady=(0, 4))
        fields = [
            ("名称", "hostname", "text", False, ""),
            ("地址 *", "host", "text", True, ""),
            ("端口", "port", "text", True, "22"),
            ("厂商", "vendor", "choice", True, "huawei"),
            ("接入协议", "protocol", "choice", True, "ssh"),
        ]
        sec_auth = tk.Label(body, text="认证", bg=theme.panel, fg=theme.muted,
                            font=FONT_SMALL)
        sec_auth.pack(anchor="w", pady=(12, 4))
        fields += [
            ("用户名", "username", "text", False, ""),
            ("密码", "password", "password", False, ""),
        ]
        sec_other = tk.Label(body, text="其他", bg=theme.panel, fg=theme.muted,
                             font=FONT_SMALL)
        sec_other.pack(anchor="w", pady=(12, 4))
        fields += [("备注", "note", "text", False, "")]

        vars_: dict[str, tk.StringVar] = {}
        err_labels: dict[str, tk.Label] = {}
        widgets_by_key: dict[str, tk.Widget] = {}

        def add_row(label, key, kind, required, value):
            row = tk.Frame(body, bg=theme.panel)
            row.pack(fill=tk.X, pady=(0, 8))
            head = tk.Frame(row, bg=theme.panel)
            head.pack(fill=tk.X)
            tk.Label(head, text=label + (" *" if required else ""), bg=theme.panel,
                     fg=theme.muted if not required else theme.fg,
                     font=FONT_SMALL).pack(side=tk.LEFT)
            var = tk.StringVar(value=value)
            vars_[key] = var
            if kind == "choice":
                w = ttk.Combobox(row, textvariable=var, state="readonly")
            elif kind == "password":
                w = tk.Entry(row, textvariable=var, bg=theme.panel_alt, fg=theme.fg,
                             relief=tk.FLAT, show="•", insertbackground=theme.fg)
            else:
                w = tk.Entry(row, textvariable=var, bg=theme.panel_alt, fg=theme.fg,
                             relief=tk.FLAT, insertbackground=theme.fg)
            w.pack(fill=tk.X, pady=(2, 0), ipady=4)
            widgets_by_key[key] = w
            err = tk.Label(row, text="", bg=theme.panel, fg=theme.err, font=FONT_SMALL)
            err.pack(anchor="w")
            err_labels[key] = err

        for label, key, kind, required, _v in fields:
            value = str(getattr(dev, key) or "")
            if key == "protocol":
                value = dev.protocol or "ssh"
            add_row(label, key, kind, required, value)
        # choice 选项
        vendor_cb = widgets_by_key["vendor"]
        vendor_cb["values"] = [f"{k} · {v}" for k, v in VENDORS.items()]
        vendor_cb.current(list(VENDORS).index(dev.vendor)
                          if dev.vendor in VENDORS else list(VENDORS).index("generic"))
        proto_cb = widgets_by_key["protocol"]
        proto_cb["values"] = ("ssh", "telnet")
        proto_cb.current(0 if (dev.protocol or "ssh") == "ssh" else 1)

        err_bar = tk.Label(body, text="", bg=theme.panel, fg=theme.err,
                           font=FONT_SMALL, wraplength=500, justify="left")
        err_bar.pack(anchor="w", pady=(8, 0))

        save_btn_holder = tk.Frame(body, bg=theme.panel)
        save_btn_holder.pack(fill=tk.X, pady=(12, 0))
        save_btn = WButton(save_btn_holder, text="保存", bg=theme.accent)

        def set_field_error(key, msg):
            err_labels[key].config(text=msg)
            w = widgets_by_key[key]
            if isinstance(w, tk.Entry):
                w.config(highlightbackground=theme.err, highlightcolor=theme.err,
                         highlightthickness=1)

        def clear_errors():
            for lb in err_labels.values():
                lb.config(text="")
            for w in widgets_by_key.values():
                if isinstance(w, tk.Entry):
                    w.config(highlightbackground=theme.panel_alt,
                             highlightthickness=0)

        def do_save():
            clear_errors()
            errors = {}
            host = vars_["host"].get().strip()
            if not host:
                errors["host"] = "主机地址不能为空"
            try:
                port = int(vars_["port"].get() or 22)
                if not (1 <= port <= 65535):
                    raise ValueError
            except ValueError:
                errors["port"] = "端口必须是 1-65535 的整数"
            if errors:
                for k, m in errors.items():
                    set_field_error(k, m)
                err_bar.config(text="请修正上方标红的字段")
                return
            vendor_val = vars_["vendor"].get().split(" · ")[0]
            new = Device(
                hostname=vars_["hostname"].get().strip(),
                host=host, port=port, vendor=vendor_val,
                username=vars_["username"].get().strip(),
                password=vars_["password"].get(),
                protocol=vars_["protocol"].get(),
                note=vars_["note"].get().strip())
            save_btn.config(text="保存中…", state=tk.DISABLED)
            err_bar.config(text="")

            def commit():
                try:
                    if is_edit:
                        self.app.inventory.update(idx, new)
                    else:
                        self.app.inventory.add(new)
                except (ValueError, IndexError) as e:
                    err_bar.config(text=str(e))
                    save_btn.config(text="保存", state=tk.NORMAL)
                    return
                drawer.close()
                self.refresh()
                self.app.refresh_dashboard()
                toast(self.app, "设备已保存", "ok")

            self.after(180, commit)   # 短暂 loading 视觉反馈

        save_btn.config(command=do_save)
        WButton(save_btn_holder, text="取消", command=drawer.close).pack(
            side=tk.RIGHT, padx=(8, 0))
        save_btn.pack(side=tk.RIGHT)

    # ── 导入/导出/删除 ──
    def import_csv(self):
        path = filedialog.askopenfilename(filetypes=[("CSV", "*.csv"),
                                                     ("文本", "*.txt"), ("全部", "*.*")])
        if not path:
            return
        with open(path, encoding="utf-8-sig", errors="replace") as f:
            text = f.read()
        added, warns = self.app.inventory.import_csv(text)
        self.refresh()
        self.app.refresh_dashboard()
        if added:
            toast(self.app, f"导入 {added} 台设备", "ok")
        if warns:
            messagebox.showwarning("导入完成（含告警）",
                                   f"导入 {added} 台设备\n" + "\n".join(warns[:8]))

    def export_csv(self):
        path = filedialog.asksaveasfilename(
            defaultextension=".csv",
            initialfile=f"devices_{datetime.now():%Y%m%d}.csv")
        if not path:
            return
        with open(path, "w", encoding="utf-8-sig", newline="") as f:
            f.write(self.app.inventory.export_csv())
        toast(self.app, f"已导出到 {path}（不含密码）", "ok")

    # ── 连接测试（小白最容易卡住的一步：地址/端口/凭据到底通不通）──
    def _load_demo(self):
        """空状态里的「载入演示数据」：一键把界面填满，先看见再理解。"""
        from netwright import demo

        devices, links = demo.seed(self.app.inventory)
        self.app.controller_store.graph.clear()
        self.app.controller_store.sync_inventory()
        self.refresh()
        self.app.refresh_dashboard()
        self.app.event_bus.publish("demo.loaded",
                                   f"已载入演示数据：{devices} 台设备 / {links} 条链路",
                                   source="inventory")
        toast(self.app, f"演示数据就绪：{devices} 台设备 / {links} 条链路", "ok")
        self.app.set_status("演示数据已载入，可去「拓扑」看看效果")

    def test_connections(self):
        devices = self._selected_devices() or list(self.app.inventory.devices)
        if not devices:
            messagebox.showinfo("提示", "请先添加设备，或载入演示数据")
            return
        results: list[str] = []

        def worker():
            from netwright.sdn.southbound import default_registry
            registry = default_registry()
            for device in devices:
                adapter = registry.for_device(device)
                if adapter is None:
                    results.append(f"✖ {device.display_name}: 不支持的接入协议 {device.protocol}")
                    continue
                port = device.port or (23 if device.protocol == "telnet" else 22)
                try:
                    import socket
                    with socket.create_connection((device.host, port), timeout=2.5):
                        results.append(f"✓ {device.display_name}: {device.host}:{port} 端口可达"
                                       f"（{device.protocol.upper()}）")
                except OSError as exc:
                    results.append(f"✖ {device.display_name}: {device.host}:{port} "
                                   f"不可达（{friendly_error(exc)}）")
            self.app.after(0, self._test_done, results)

        self.app.set_status(f"正在测试 {len(devices)} 台设备的连通性…")
        threading.Thread(target=worker, daemon=True).start()

    def _test_done(self, results: list):
        ok = sum(1 for r in results if r.startswith("✓"))
        self.app.set_status(f"连通性测试完成：{ok}/{len(results)} 台端口可达")
        messagebox.showinfo("连接测试结果",
                            "\n".join(results[:20]) +
                            ("\n…" if len(results) > 20 else "") +
                            "\n\n端口可达只代表网络通；登录是否成功还要看用户名/密码。")

    # ── 配置备份（Oxidized 式：按设备存档，未变化不落盘）──
    def backup_configs(self):
        devices = self._selected_devices() or list(self.app.inventory.devices)
        if not devices:
            messagebox.showinfo("提示", "请先添加设备，或载入演示数据")
            return
        store = self.app.controller_store
        if getattr(store, "backups", None) is None:
            messagebox.showwarning("备份未启用", "当前控制器没有配置备份目录")
            return
        self.app.set_status(f"正在备份 {len(devices)} 台设备的配置…")
        results: list[tuple] = []

        def worker():
            for device in devices:
                try:
                    entry = store.backup_device(device)
                    results.append((device.display_name, True, entry["file"],
                                    entry["changed"]))
                except Exception as exc:      # noqa: BLE001
                    results.append((device.display_name, False, friendly_error(exc), False))
            self.app.after(0, self._backup_done, results)

        threading.Thread(target=worker, daemon=True).start()

    def _backup_done(self, results: list):
        ok = [r for r in results if r[1]]
        changed = [r for r in ok if r[3]]
        self.app.set_status(
            f"配置备份完成：{len(ok)}/{len(results)} 台成功，{len(changed)} 台有变化")
        lines = []
        for name, success, detail, was_changed in results:
            if success:
                lines.append(f"✓ {name}: {'已更新' if was_changed else '无变化'}（{detail}）")
            else:
                lines.append(f"✖ {name}: {detail}")
        messagebox.showinfo("配置备份结果",
                            "\n".join(lines[:20]) +
                            ("\n…" if len(lines) > 20 else "") +
                            f"\n\n存放目录：{self.app.controller_store.backups.root}")

    # ── 备份历史 / 差异（Oxidized 的 GUI 那一半）──
    def show_backups(self):
        devices = self._selected_devices()
        if not devices:
            messagebox.showinfo("提示", "请先选中一台设备，再查看它的备份历史")
            return
        store = self.app.controller_store
        if getattr(store, "backups", None) is None:
            messagebox.showwarning("备份未启用", "当前控制器没有配置备份目录")
            return
        dialog = BackupHistoryDialog(self.app, devices[0].display_name)
        dialog.focus_force()


class BackupHistoryDialog(tk.Toplevel):
    """列出某台设备的快照，并可对任意两份做 unified diff。"""

    def __init__(self, app, device: str):
        super().__init__(app)
        self.app = app
        self.device = device
        self.backup = app.controller_store.backups
        self.title(f"备份历史 · {device}")
        self.configure(bg=theme.bg)
        self.transient(app)
        w, h = 900, 620
        x = app.winfo_rootx() + max(0, (app.winfo_width() - w) // 2)
        y = app.winfo_rooty() + max(0, (app.winfo_height() - h) // 2)
        self.geometry(f"{w}x{h}+{x}+{y}")

        head = tk.Frame(self, bg=theme.panel)
        head.pack(fill=tk.X)
        tk.Label(head, text=f"{device} 的配置快照", bg=theme.panel, fg=theme.fg,
                 font=("Microsoft YaHei UI", 12, "bold")).pack(side=tk.LEFT, padx=14, pady=10)
        tk.Label(head, text=self.backup.root, bg=theme.panel, fg=theme.faint,
                 font=FONT_SMALL).pack(side=tk.RIGHT, padx=14)

        body = tk.Frame(self, bg=theme.bg)
        body.pack(fill=tk.BOTH, expand=True, padx=12, pady=10)
        body.columnconfigure(0, weight=0, minsize=250)
        body.columnconfigure(1, weight=1)
        body.rowconfigure(0, weight=1)

        left = tk.Frame(body, bg=theme.panel)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
        tk.Label(left, text="选择两份快照（按住 Ctrl 多选）", bg=theme.panel,
                 fg=theme.muted, font=FONT_SMALL).pack(anchor="w", padx=10, pady=(8, 4))
        self.listbox = tk.Listbox(left, selectmode=tk.EXTENDED, bg=theme.panel,
                                  fg=theme.fg, relief=tk.FLAT, highlightthickness=0,
                                  font=("Consolas", 9), activestyle="none")
        self.listbox.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0, 8))
        btns = tk.Frame(left, bg=theme.panel)
        btns.pack(fill=tk.X, padx=10, pady=(0, 10))
        WButton(btns, text="对比所选", command=self._diff_selected).pack(side=tk.LEFT)
        WButton(btns, text="最近两次", command=self._diff_latest).pack(side=tk.LEFT, padx=(6, 0))

        right = tk.Frame(body, bg=theme.panel)
        right.grid(row=0, column=1, sticky="nsew")
        self.diff_text = tk.Text(right, bg=theme.code_bg, fg="#D7E2F2", relief=tk.FLAT,
                                 font=("Consolas", 9), wrap="none", bd=0,
                                 highlightthickness=0, padx=10, pady=8)
        self.diff_text.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)
        self.diff_text.tag_config("add", foreground="#7EE787")
        self.diff_text.tag_config("del", foreground="#FF7B72")
        self.diff_text.tag_config("meta", foreground="#8B949E")

        self.entries: list = []
        self._load()
        self.bind("<Escape>", lambda _e: self.destroy())

    def _load(self):
        self.listbox.delete(0, tk.END)
        self.entries = self.backup.history(self.device)
        if not self.entries:
            self.listbox.insert(tk.END, "（还没有快照：先点「🗄 备份配置」）")
            self.diff_text.insert("1.0", "没有可对比的快照。")
            return
        for entry in self.entries:
            self.listbox.insert(tk.END, f"{entry.time_text}   {entry.size // 1024} KB")
        if len(self.entries) >= 2:
            self._diff_latest()

    def _diff_latest(self):
        if len(self.entries) < 2:
            self._show("只有一份快照，无法对比。再备份一次（内容有变化时）即可。")
            return
        new, old = self.entries[0], self.entries[1]
        self._show(self.backup.diff_text(self.backup.read(old), self.backup.read(new),
                                         old.filename, new.filename))

    def _diff_selected(self):
        selection = list(self.listbox.curselection())
        if len(selection) != 2:
            self._show("请按住 Ctrl 选中**两份**快照再点「对比所选」。")
            return
        first, second = sorted(selection)
        old, new = self.entries[first], self.entries[second]
        self._show(self.backup.diff_text(self.backup.read(old), self.backup.read(new),
                                         old.filename, new.filename))

    def _show(self, text: str):
        self.diff_text.delete("1.0", tk.END)
        if not text:
            self.diff_text.insert(tk.END, "两份快照内容一致，没有差异。")
            return
        for line in text.splitlines():
            tag = ""
            if line.startswith("+") and not line.startswith("+++"):
                tag = "add"
            elif line.startswith("-") and not line.startswith("---"):
                tag = "del"
            elif line.startswith(("---", "+++", "@@")):
                tag = "meta"
            self.diff_text.insert(tk.END, line + "\n", tag)
