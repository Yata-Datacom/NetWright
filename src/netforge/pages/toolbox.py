"""工具箱工作区页面。"""
from __future__ import annotations

import random
import string
import threading
import tkinter as tk
from tkinter import messagebox, ttk

from netforge.lib import netcalc, portscan
from netforge.theme import (
    ACCENT, BG, FG, GREEN, MUTED, NAVY2, PANEL, MONO,
)
from netforge.widgets import Page, page_header


def header(title, desc, page):
    page_header(page, title, desc)
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


