"""
NetForge — 网络工程师工作台
============================

一个轻量平台壳，把网络工程师的日常工具收进一个窗口：

  * 总览      —— 外部模块（NetPilot / NADT / Inspection / Traffic）发现与一键启动
  * 子网计算  —— CIDR / 掩码换算、可用主机范围、VLSM 划分
  * 端口扫描  —— TCP connect 并发扫描 + 常用端口速查
  * 在线检测  —— 网段 ping 扫描（存活主机 / 延迟 / 主机名）
  * 命令速查  —— 场景 × 厂商 CLI 备忘检索

只依赖 Python 标准库。运行：python netforge.py
"""
from __future__ import annotations

import os
import sys
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

if getattr(sys, "frozen", False):
    BASE_DIR = os.path.dirname(os.path.abspath(sys.executable))
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)

from netforge_lib import cheatsheet, launch, netcalc, portscan  # noqa: E402
from netforge_lib import __version__  # noqa: E402

# ── 配色（暗色工作台）─────────────────────────────────────────────
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

MODULE_ICON = {"netpilot": "🛰", "nadt": "🚀", "inspection": "🔎", "traffic": "⚡"}


class Page(tk.Frame):
    """页面基类。"""

    def __init__(self, master, app):
        super().__init__(master, bg=BG)
        self.app = app


class OverviewPage(Page):
    def __init__(self, master, app):
        super().__init__(master, app)
        header("总览", "发现并启动你身边的网络工具；内置子网计算 / 端口扫描 / 在线检测 / 命令速查", self)
        body = tk.Frame(self, bg=BG)
        body.pack(fill=tk.BOTH, expand=True, padx=16, pady=(0, 12))

        ttk.Label(body, text="外部模块", style="H2.TLabel").pack(anchor="w", pady=(4, 6))
        self.cards = tk.Frame(body, bg=BG)
        self.cards.pack(fill=tk.X)
        self.modules = launch.discover_modules(BASE_DIR) + launch.load_custom_modules(BASE_DIR)
        for mod in self.modules:
            self._module_card(self.cards, mod)

        ttk.Label(body, text="内置工具", style="H2.TLabel").pack(anchor="w", pady=(14, 6))
        grid = tk.Frame(body, bg=BG)
        grid.pack(fill=tk.X)
        tools = [
            ("子网计算", "CIDR / 掩码 / VLSM", "subnet"),
            ("端口扫描", "TCP 并发 + 常用端口", "scan"),
            ("在线检测", "网段 ping 扫描", "ping"),
            ("命令速查", "场景 × 厂商 CLI 备忘", "cheat"),
        ]
        for i, (name, desc, key) in enumerate(tools):
            card = tk.Frame(grid, bg=PANEL, highlightbackground=LINE, highlightthickness=1)
            card.grid(row=i // 2, column=i % 2, sticky="ew", padx=6, pady=6)
            grid.columnconfigure(i % 2, weight=1)
            tk.Label(card, text=name, bg=PANEL, fg=FG, font=("", 12, "bold")).pack(
                anchor="w", padx=12, pady=(10, 0))
            tk.Label(card, text=desc, bg=PANEL, fg=MUTED, font=("", 9)).pack(anchor="w", padx=12)
            tk.Button(card, text="打开 →", bg=NAVY2, fg=FG, activebackground=NAVY,
                      relief=tk.FLAT, cursor="hand2",
                      command=lambda k=key: self.app.show(k)).pack(anchor="w", padx=12, pady=8)

        hint = ("提示：把 NetForge.exe 放在 NetPilot / NADT / network_A / test_A 的同级目录，"
                "总览会自动发现它们；也可用 netforge_modules.json 登记自定义工具。")
        tk.Label(body, text=hint, bg=BG, fg=MUTED, font=("", 9), wraplength=860,
                 justify="left").pack(anchor="w", pady=(10, 0))

    def _module_card(self, parent, mod):
        color = GREEN if mod.available else MUTED
        state = "可用" if mod.available else "未发现（放在同级目录即可）"
        card = tk.Frame(parent, bg=PANEL, highlightbackground=LINE, highlightthickness=1)
        card.pack(fill=tk.X, pady=5)
        inner = tk.Frame(card, bg=PANEL)
        inner.pack(fill=tk.X, padx=12, pady=10)
        tk.Label(inner, text=MODULE_ICON.get(mod.key, "🧩"), bg=PANEL, fg=FG,
                 font=("", 16)).pack(side=tk.LEFT, padx=(0, 10))
        mid = tk.Frame(inner, bg=PANEL)
        mid.pack(side=tk.LEFT, fill=tk.X, expand=True)
        tk.Label(mid, text=mod.name, bg=PANEL, fg=FG, font=("", 11, "bold")).pack(anchor="w")
        tk.Label(mid, text=mod.desc, bg=PANEL, fg=MUTED, font=("", 9), wraplength=640,
                 justify="left").pack(anchor="w")
        tk.Label(inner, text=f"● {state}", bg=PANEL, fg=color, font=("", 9)).pack(side=tk.RIGHT)
        btn = tk.Button(inner, text="启动", bg=ACCENT, fg="white", relief=tk.FLAT,
                        activebackground=NAVY2, cursor="hand2", state=tk.NORMAL if mod.available else tk.DISABLED,
                        command=lambda m=mod: self._launch(m))
        btn.pack(side=tk.RIGHT, padx=(10, 0))

    def _launch(self, mod):
        try:
            msg = launch.launch(mod.candidates[0])
            self.app.set_status(msg)
        except Exception as e:
            messagebox.showerror("启动失败", str(e))


class SubnetPage(Page):
    def __init__(self, master, app):
        super().__init__(master, app)
        header("子网计算", "CIDR / 点分掩码 → 网络地址、可用范围、二进制掩码；支持 VLSM 划分", self)
        body = tk.Frame(self, bg=BG)
        body.pack(fill=tk.BOTH, expand=True, padx=16, pady=(0, 12))

        row = tk.Frame(body, bg=BG)
        row.pack(fill=tk.X, pady=(2, 8))
        tk.Label(row, text="网络 / CIDR:", bg=BG, fg=MUTED, font=("", 10)).pack(side=tk.LEFT)
        self.ent = tk.Entry(row, bg=PANEL, fg=FG, relief=tk.FLAT, font=MONO, width=32,
                            insertbackground=FG)
        self.ent.insert(0, "192.168.10.130 255.255.255.0")
        self.ent.pack(side=tk.LEFT, padx=(8, 6), ipady=4)
        tk.Button(row, text="计算", bg=ACCENT, fg="white", relief=tk.FLAT,
                  activebackground=NAVY2, command=self.do_calc).pack(side=tk.LEFT, padx=(0, 6))
        tk.Button(row, text="VLSM 划分", bg=NAVY2, fg=FG, relief=tk.FLAT,
                  activebackground=NAVY, command=self.do_vlsm).pack(side=tk.LEFT)
        tk.Label(row, text="VLSM 主机数(逗号分隔):", bg=BG, fg=MUTED, font=("", 9)).pack(side=tk.LEFT, padx=(12, 4))
        self.ent_vlsm = tk.Entry(row, bg=PANEL, fg=FG, relief=tk.FLAT, font=MONO, width=18,
                                 insertbackground=FG)
        self.ent_vlsm.insert(0, "100, 50, 20, 5")
        self.ent_vlsm.pack(side=tk.LEFT)

        self.out = tk.Text(body, bg=PANEL, fg=FG, relief=tk.FLAT, font=MONO, height=16,
                           insertbackground=FG)
        self.out.pack(fill=tk.BOTH, expand=True)
        self.out.tag_config("k", foreground=MUTED)
        self.out.tag_config("v", foreground=FG)
        self.out.tag_config("hl", foreground=ACCENT)
        self._kv = {}
        self.ent.bind("<Return>", lambda e: self.do_calc())
        self.do_calc()

    def do_calc(self):
        try:
            info = netcalc.calc_subnet(self.ent.get())
        except ValueError as e:
            messagebox.showwarning("输入有误", str(e))
            return
        self.out.config(state=tk.NORMAL)
        self.out.delete("1.0", tk.END)
        rows = [
            ("网络地址", info.network), ("广播地址", info.broadcast),
            ("子网掩码", info.netmask), ("反掩码", info.wildcard),
            ("二进制掩码", info.binary_mask), ("前缀", f"/{info.prefix}"),
            ("第一个可用主机", info.first_host), ("最后一个可用主机", info.last_host),
            ("可用主机数", f"{info.usable_hosts}（总地址 {info.total_ips}）"),
            ("地址类别 / 范围", f"{info.ip_class} · {info.scope}"),
        ]
        for k, v in rows:
            self.out.insert(tk.END, f"{k:<14}", "k")
            self.out.insert(tk.END, v + "\n", "hl" if k in ("网络地址", "可用主机数") else "v")
        self.out.config(state=tk.DISABLED)
        self._last = info

    def do_vlsm(self):
        try:
            base = netcalc.cidr_normalize(self.ent.get())
            counts = [int(x) for x in self.ent_vlsm.get().replace("，", ",").split(",") if x.strip()]
            subs = netcalc.split_vlsm(base, counts)
        except ValueError as e:
            messagebox.showwarning("VLSM 划分失败", str(e))
            return
        self.out.config(state=tk.NORMAL)
        self.out.delete("1.0", tk.END)
        self.out.insert(tk.END, f"母网 {base} 的 VLSM 划分结果（按需求从大到小）:\n\n", "hl")
        for i, s in enumerate(subs, 1):
            self.out.insert(tk.END, f"子网{i}: {s.network}/{s.prefix}  ", "v")
            self.out.insert(tk.END, f"可用 {s.usable_hosts} 台  ", "k")
            self.out.insert(tk.END, f"{s.first_host} ~ {s.last_host}\n")
        self.out.config(state=tk.DISABLED)


class ScanPage(Page):
    def __init__(self, master, app):
        super().__init__(master, app)
        header("端口扫描", "TCP connect 并发探测；扫描自己管理的设备，请遵守所在网络的使用规范", self)
        body = tk.Frame(self, bg=BG)
        body.pack(fill=tk.BOTH, expand=True, padx=16, pady=(0, 12))

        row = tk.Frame(body, bg=BG)
        row.pack(fill=tk.X, pady=(2, 6))
        tk.Label(row, text="主机:", bg=BG, fg=MUTED).pack(side=tk.LEFT)
        self.ent_host = tk.Entry(row, bg=PANEL, fg=FG, relief=tk.FLAT, font=MONO, width=20,
                                 insertbackground=FG)
        self.ent_host.insert(0, "192.0.2.1")
        self.ent_host.pack(side=tk.LEFT, padx=(6, 12), ipady=4)
        tk.Label(row, text="端口:", bg=BG, fg=MUTED).pack(side=tk.LEFT)
        self.ent_ports = tk.Entry(row, bg=PANEL, fg=FG, relief=tk.FLAT, font=MONO, width=30,
                                  insertbackground=FG)
        self.ent_ports.insert(0, "22, 23, 80, 443, 830, 8080, 3389")
        self.ent_ports.pack(side=tk.LEFT, padx=(6, 12), ipady=4)
        self.btn = tk.Button(row, text="开始扫描", bg=ACCENT, fg="white", relief=tk.FLAT,
                             activebackground=NAVY2, command=self.start)
        self.btn.pack(side=tk.LEFT)
        self.var_count = tk.StringVar(value="")
        tk.Label(row, textvariable=self.var_count, bg=BG, fg=MUTED, font=("", 9)).pack(side=tk.RIGHT)

        cols = ("port", "state", "service")
        wrap = tk.Frame(body, bg=BG)
        wrap.pack(fill=tk.BOTH, expand=True, pady=(6, 0))
        self.tree = ttk.Treeview(wrap, columns=cols, show="headings", height=16)
        for c, t, w in (("port", "端口", 100), ("state", "状态", 100), ("service", "常见服务", 220)):
            self.tree.heading(c, text=t)
            self.tree.column(c, width=w, anchor="center" if c != "service" else "w")
        vsb = ttk.Scrollbar(wrap, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)
        self.tree.tag_configure("open", foreground=GREEN)
        self.tree.tag_configure("closed", foreground=MUTED)

    def start(self):
        host = self.ent_host.get().strip()
        try:
            ports = portscan.parse_ports(self.ent_ports.get())
        except ValueError as e:
            messagebox.showwarning("输入有误", str(e))
            return
        self.btn.config(state=tk.DISABLED)
        self.tree.delete(*self.tree.get_children())
        self.var_count.set("扫描中…")

        def worker():
            results = portscan.scan_ports(host, ports, progress=self._progress)
            self.app.after(0, lambda: self._done(results))

        threading.Thread(target=worker, daemon=True).start()

    def _progress(self, done, total):
        self.app.after(0, lambda: self.var_count.set(f"扫描中… {done}/{total}"))

    def _done(self, results):
        self.btn.config(state=tk.NORMAL)
        opened = 0
        for r in results:
            self.tree.insert("", "end", values=(r.port, r.state, r.service),
                             tags=("open",) if r.state == "open" else ("closed",))
            opened += r.state == "open"
        self.var_count.set(f"完成：{len(results)} 个端口，开放 {opened}")


class PingPage(Page):
    def __init__(self, master, app):
        super().__init__(master, app)
        header("在线检测", "网段 ping 扫描：存活主机、延迟、主机名反查（使用系统 ping）", self)
        body = tk.Frame(self, bg=BG)
        body.pack(fill=tk.BOTH, expand=True, padx=16, pady=(0, 12))

        row = tk.Frame(body, bg=BG)
        row.pack(fill=tk.X, pady=(2, 6))
        tk.Label(row, text="目标:", bg=BG, fg=MUTED).pack(side=tk.LEFT)
        self.ent_target = tk.Entry(row, bg=PANEL, fg=FG, relief=tk.FLAT, font=MONO, width=34,
                                   insertbackground=FG)
        self.ent_target.insert(0, "192.168.1.0/24")
        self.ent_target.pack(side=tk.LEFT, padx=(6, 12), ipady=4)
        self.var_names = tk.BooleanVar(value=False)
        ttk.Checkbutton(row, text="反查主机名", variable=self.var_names, style="TCheckbutton").pack(side=tk.LEFT)
        self.btn = tk.Button(row, text="开始检测", bg=ACCENT, fg="white", relief=tk.FLAT,
                             activebackground=NAVY2, command=self.start)
        self.btn.pack(side=tk.LEFT, padx=(10, 0))
        self.var_count = tk.StringVar(value="")
        tk.Label(row, textvariable=self.var_count, bg=BG, fg=MUTED, font=("", 9)).pack(side=tk.RIGHT)

        cols = ("ip", "alive", "delay", "name")
        wrap = tk.Frame(body, bg=BG)
        wrap.pack(fill=tk.BOTH, expand=True, pady=(6, 0))
        self.tree = ttk.Treeview(wrap, columns=cols, show="headings", height=17)
        for c, t, w in (("ip", "IP 地址", 160), ("alive", "状态", 80),
                        ("delay", "延迟(ms)", 100), ("name", "主机名", 260)):
            self.tree.heading(c, text=t)
            self.tree.column(c, width=w, anchor="center" if c != "name" else "w")
        vsb = ttk.Scrollbar(wrap, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)
        self.tree.tag_configure("alive", foreground=GREEN)
        self.tree.tag_configure("dead", foreground=MUTED)

    def start(self):
        try:
            ips = portscan.parse_ip_targets(self.ent_target.get())
        except ValueError as e:
            messagebox.showwarning("输入有误", str(e))
            return
        self.btn.config(state=tk.DISABLED)
        self.tree.delete(*self.tree.get_children())
        self.var_count.set(f"检测中… 0/{len(ips)}")

        def worker():
            results = portscan.sweep_hosts(ips, resolve_names=self.var_names.get(),
                                           progress=self._progress)
            self.app.after(0, lambda: self._done(results))

        threading.Thread(target=worker, daemon=True).start()

    def _progress(self, done, total):
        self.app.after(0, lambda: self.var_count.set(f"检测中… {done}/{total}"))

    def _done(self, results):
        self.btn.config(state=tk.NORMAL)
        alive = 0
        for r in results:
            self.tree.insert("", "end",
                             values=(r.ip, "在线" if r.alive else "离线",
                                     f"{r.delay_ms:.0f}" if r.alive else "—", r.hostname),
                             tags=("alive",) if r.alive else ("dead",))
            alive += r.alive
        self.var_count.set(f"完成：{alive}/{len(results)} 台在线")


class CheatPage(Page):
    def __init__(self, master, app):
        super().__init__(master, app)
        header("命令速查", "场景 × 厂商 CLI 备忘；输入关键字即时过滤，双击行复制", self)
        body = tk.Frame(self, bg=BG)
        body.pack(fill=tk.BOTH, expand=True, padx=16, pady=(0, 12))

        row = tk.Frame(body, bg=BG)
        row.pack(fill=tk.X, pady=(2, 6))
        tk.Label(row, text="搜索:", bg=BG, fg=MUTED).pack(side=tk.LEFT)
        self.ent = tk.Entry(row, bg=PANEL, fg=FG, relief=tk.FLAT, font=MONO, width=40,
                            insertbackground=FG)
        self.ent.pack(side=tk.LEFT, padx=(6, 0), ipady=4)
        self.ent.bind("<KeyRelease>", lambda e: self.refresh())
        self.var_count = tk.StringVar()
        tk.Label(row, textvariable=self.var_count, bg=BG, fg=MUTED, font=("", 9)).pack(side=tk.RIGHT)

        cols = ("scene", "vendor", "title", "cmd")
        wrap = tk.Frame(body, bg=BG)
        wrap.pack(fill=tk.BOTH, expand=True, pady=(6, 0))
        self.tree = ttk.Treeview(wrap, columns=cols, show="headings", height=18)
        for c, t, w in (("scene", "场景", 110), ("vendor", "厂商", 130),
                        ("title", "标题", 180), ("cmd", "命令 / 说明", 430)):
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
        cmd = self.tree.item(sel[0], "values")[3]
        self.app.clipboard_clear()
        self.app.clipboard_append(cmd)
        self.app.set_status("已复制到剪贴板")


def header(title: str, desc: str, page: Page):
    bar = tk.Frame(page, bg=BG)
    bar.pack(fill=tk.X, padx=16, pady=(12, 6))
    tk.Label(bar, text=title, bg=BG, fg=FG, font=("", 16, "bold")).pack(anchor="w")
    tk.Label(bar, text=desc, bg=BG, fg=MUTED, font=("", 9)).pack(anchor="w")
    tk.Frame(page, bg=ACCENT, height=2).pack(fill=tk.X, padx=16)


class NetForgeApp(tk.Tk):
    PAGES = [
        ("overview", "总览", "🏠"),
        ("subnet", "子网计算", "🧮"),
        ("scan", "端口扫描", "🔌"),
        ("ping", "在线检测", "📡"),
        ("cheat", "命令速查", "📖"),
    ]

    def __init__(self):
        super().__init__()
        self.title(f"NetForge — 网络工程师工作台 v{__version__}")
        self.geometry("1040x720")
        self.minsize(960, 620)
        self.configure(bg=BG)
        try:
            from tkinter import font as tkfont
            self.option_add("*Font", ("Microsoft YaHei UI", 10))
        except Exception:
            pass
        self._style()
        ico = os.path.join(BASE_DIR, "assets", "icon.ico")
        if os.path.isfile(ico):
            try:
                self.iconbitmap(ico)
            except Exception:
                pass

        # ── 顶栏 ──
        top = tk.Frame(self, bg=NAVY, height=56)
        top.pack(fill=tk.X)
        top.pack_propagate(False)
        tk.Label(top, text="⛏", bg=NAVY, fg=ACCENT, font=("", 18)).pack(side=tk.LEFT, padx=(16, 8))
        tk.Label(top, text="NetForge", bg=NAVY, fg=FG, font=("", 15, "bold")).pack(side=tk.LEFT)
        tk.Label(top, text="网络工程师工作台", bg=NAVY, fg=MUTED, font=("", 10)).pack(side=tk.LEFT, padx=(10, 0))
        self.var_status = tk.StringVar(value="就绪")
        tk.Label(top, textvariable=self.var_status, bg=NAVY, fg=MUTED, font=("", 9)).pack(side=tk.RIGHT, padx=14)

        # ── 侧栏 + 页面 ──
        main = tk.Frame(self, bg=BG)
        main.pack(fill=tk.BOTH, expand=True)
        rail = tk.Frame(main, bg=NAVY, width=170)
        rail.pack(side=tk.LEFT, fill=tk.Y)
        rail.pack_propagate(False)
        self._nav_buttons = {}
        for key, name, icon in self.PAGES:
            btn = tk.Label(rail, text=f"  {icon}  {name}", bg=NAVY, fg=MUTED, font=("", 11),
                           anchor="w", pady=10, cursor="hand2")
            btn.pack(fill=tk.X, padx=8, pady=(6 if key == "overview" else 0))
            btn.bind("<Button-1>", lambda e, k=key: self.show(k))
            self._nav_buttons[key] = btn
        tk.Frame(rail, bg=LINE, height=1).pack(fill=tk.X, padx=8, pady=6)
        tk.Label(rail, text=f"v{__version__}", bg=NAVY, fg=MUTED, font=("", 8)).pack(side=tk.BOTTOM, pady=8)

        self.pages: dict[str, Page] = {}
        for key, _name, _icon in self.PAGES:
            cls = {"overview": OverviewPage, "subnet": SubnetPage, "scan": ScanPage,
                   "ping": PingPage, "cheat": CheatPage}[key]
            page = cls(main, self)
            self.pages[key] = page
        self.show("overview")

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
        style.configure("H2.TLabel", background=BG, foreground=MUTED, font=("", 11, "bold"))

    def show(self, key: str):
        for k, page in self.pages.items():
            page.place_forget() if k != key else page.place(relx=0, rely=0, relwidth=1, relheight=1)
        for k, btn in self._nav_buttons.items():
            btn.config(bg=ACCENT if k == key else NAVY, fg="white" if k == key else MUTED)
        self.set_status("就绪")

    def set_status(self, text: str):
        self.var_status.set(text)


def main() -> None:
    app = NetForgeApp()
    app.mainloop()


if __name__ == "__main__":
    main()
