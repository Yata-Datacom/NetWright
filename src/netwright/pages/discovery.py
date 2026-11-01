"""discovery.py — 资产盘点工作区页面（可视化 + 一键盘点 + 一键入清单）。"""
from __future__ import annotations

import math
import threading
import tkinter as tk
from tkinter import ttk

from netwright.lib import discovery
from netwright.theme import FONT, FONT_SMALL, FONT_MONO, theme
from netwright.widgets import (Page, page_header, make_table, zebra, WButton)


class DiscoveryPage(Page):
    def __init__(self, master, app):
        super().__init__(master, app)
        page_header(self, "资产盘点", "从种子设备一键发现内网资产：LLDP/CDP 邻居 → ARP/MAC → IP 汇总 → 协议探测 → 关联分析")
        self.nb = ttk.Notebook(self)
        self.nb.pack(fill=tk.BOTH, expand=True, padx=16, pady=(0, 12))
        self._scan_tab()
        self._result_tab()
        self._topo_tab()

    # ── 盘点执行 ──
    def _scan_tab(self):
        tab = tk.Frame(self.nb, bg=theme.bg)
        self.nb.add(tab, text=" 盘点 ")
        bar = tk.Frame(tab, bg=theme.bg)
        bar.pack(fill=tk.X, pady=(8, 4))
        ttk.Label(bar, text="种子设备:", style="H2.TLabel").pack(side=tk.LEFT)
        self.cmb_seed = ttk.Combobox(bar, state="readonly", width=26)
        self._refresh_seeds()
        self.cmb_seed.pack(side=tk.LEFT, padx=(6, 12))
        ttk.Label(bar, text="递归跳数:", style="H2.TLabel").pack(side=tk.LEFT)
        self.cmb_depth = ttk.Combobox(bar, state="readonly", width=4,
                                      values=("1", "2", "3"))
        self.cmb_depth.current(0)
        self.cmb_depth.pack(side=tk.LEFT, padx=(6, 12))
        self.var_probe = tk.BooleanVar(value=True)
        ttk.Checkbutton(bar, text="协议端口探测 (22/23/830)", variable=self.var_probe,
                        style="TCheckbutton").pack(side=tk.LEFT, padx=(0, 12))
        self.btn_run = WButton(bar, text="🚀 一键盘点", bg=theme.accent, fg="white",
                                 relief=tk.FLAT, activebackground=theme.nav2,
                                 font=FONT, command=self.start)
        self.btn_run.pack(side=tk.LEFT, padx=(0, 12))
        WButton(bar, text="导入清单（新增设备）", bg=theme.ok, fg="white",
                  relief=tk.FLAT, activebackground=theme.nav2,
                  command=self.import_new).pack(side=tk.LEFT)
        self.var_prog = tk.StringVar(value="选择种子设备后开始")
        tk.Label(bar, textvariable=self.var_prog, bg=theme.bg, fg=theme.muted,
                 font=FONT_SMALL).pack(side=tk.RIGHT)
        self.progress = ttk.Progressbar(tab, mode="determinate")
        self.progress.pack(fill=tk.X, pady=(2, 8))

        cols = ("ip", "hostname", "vendor", "protocols", "source", "known")
        heads = {"ip": "IP 地址", "hostname": "主机名", "vendor": "厂商(推测)",
                 "protocols": "管理协议", "source": "发现来源", "known": "清单"}
        self.wrap, self.tree = make_table(
            tab, list(cols), heads,
            {"ip": 150, "hostname": 170, "vendor": 120,
             "protocols": 150, "source": 150, "known": 90}, height=15,
            selectmode="extended")
        self.tree.pack(fill=tk.BOTH, expand=True)
        self.tree.tag_configure("new", foreground=theme.warn)
        self.tree.tag_configure("known", foreground=theme.ok)
        self.summary = tk.Label(tab, text="", bg=theme.bg, fg=theme.muted, font=FONT_SMALL)
        self.summary.pack(anchor="w", pady=(4, 0))

    def _result_tab(self):
        tab = tk.Frame(self.nb, bg=theme.bg)
        self.nb.add(tab, text=" 原始输出 ")
        self.raw = tk.Text(tab, bg=theme.panel_alt, fg=theme.fg, relief=tk.FLAT,
                           font=FONT_MONO, insertbackground=theme.fg, wrap=tk.NONE)
        self.raw.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        self.raw.insert("1.0", "盘点后在这里查看各设备的原始采集输出。")

    # ── 拓扑（复用控制器画布逻辑）──
    def _topo_tab(self):
        tab = tk.Frame(self.nb, bg=theme.bg)
        self.nb.add(tab, text=" 拓扑 ")
        self.canvas = tk.Canvas(tab, bg=theme.panel_alt, highlightthickness=0)
        self.canvas.pack(fill=tk.BOTH, expand=True, pady=(6, 8))
        self.canvas.create_text(480, 300, text="盘点后自动生成拓扑（LLDP/CDP 邻居关系）",
                                fill=theme.muted, font=FONT_SMALL, tags="placeholder")

    def _refresh_seeds(self):
        self.app.inventory.devices and None
        seeds = [f"{d.display_name} ({d.host})" for d in self.app.inventory.devices]
        self.seed_map = {f"{d.display_name} ({d.host})": d
                         for d in self.app.inventory.devices}
        self.cmb_seed["values"] = seeds
        if seeds:
            self.cmb_seed.current(0)

    def refresh(self):
        self._refresh_seeds()

    def start(self):
        seed = self.seed_map.get(self.cmb_seed.get())
        if not seed:
            messagebox = __import__("tkinter.messagebox", fromlist=["messagebox"]).showinfo
            _msg("提示", "设备清单为空，请先在「设备清单」页添加种子设备")
            return
        depth = int(self.cmb_depth.get())
        probe = self.var_probe.get()
        self.btn_run.config(state=tk.DISABLED)
        self.progress.config(value=0, maximum=100)
        self.var_prog.set("盘点中…")
        self.tree.delete(*self.tree.get_children())

        def worker():
            result = discovery.discover_from_seeds(
                [seed], self.app.inventory, depth=depth, probe=probe,
                progress=self._progress)
            self.app.after(0, lambda: self._done(result))

        threading.Thread(target=worker, daemon=True).start()

    def _progress(self, done, total):
        pct = int(done / max(1, total) * 100)
        self.app.after(0, lambda: (
            self.progress.config(value=pct),
            self.var_prog.set(f"盘点中… {done}/{total}")))

    def _done(self, result):
        self.btn_run.config(state=tk.NORMAL)
        self.progress.config(value=100)
        assets = result["assets"]
        summary = result["summary"]
        self._result = result

        rows = sorted(assets.values(), key=lambda a: (not a.known, a.ip or a.key))
        for i, a in enumerate(rows):
            self.tree.insert("", "end", iid=str(i), values=(
                a.ip or "—", a.hostname or "—",
                a.vendor_guess or "—",
                ", ".join(a.protocols) or "—",
                " + ".join(sorted(a.source)) or "—",
                "已知" if a.known else "新增"),
                tags=("known",) if a.known else ("new",))
            zebra(self.tree, str(i), i)
        by_vendor = " · ".join(f"{k}:{v}" for k, v in sorted(summary["by_vendor"].items()))
        self.summary.config(text=f"资产 {len(assets)}（已知 {summary['known']} / 新增 {summary['new']}）"
                                 f" · 链路 {summary['links']} 条 · {by_vendor}")
        # 原始输出
        self.raw.delete("1.0", "end")
        self.raw.insert(tk.END, f"访问过的设备：{'、'.join(result['visited']) or '—'}\n")
        if result["errors"]:
            self.raw.insert(tk.END, "错误：\n" + "\n".join(result["errors"]) + "\n\n")
        self._draw_topology(result["topology"])
        self.app.set_status(f"盘点完成：{len(assets)} 项资产")

    def _draw_topology(self, topo):
        c = self.canvas
        c.delete("all")
        nodes = sorted(topo.nodes) if topo else []
        if not nodes:
            c.create_text(480, 300, text="未发现邻居", fill=theme.muted, font=FONT_SMALL)
            return
        w = max(c.winfo_width(), 900)
        h = max(c.winfo_height(), 600)
        cx, cy, r = w / 2, h / 2, min(w, h) * 0.38
        pos = {n: (cx + r * math.cos(2 * math.pi * i / len(nodes)),
                   cy + r * math.sin(2 * math.pi * i / len(nodes)))
               for i, n in enumerate(nodes)}
        for a, ai, b, bi in topo.undirected_edges():
            if a in pos and b in pos:
                c.create_line(*pos[a], *pos[b], fill=theme.accent, width=2)
                mx, my = (pos[a][0] + pos[b][0]) / 2, (pos[a][1] + pos[b][1]) / 2
                c.create_text(mx, my, text=f"{ai}↔{bi}", fill=theme.muted, font=FONT_SMALL)
        for n, (x, y) in pos.items():
            is_new = not any(a.known and a.hostname == n for a in
                             getattr(self, "_result", {"assets": {}})["assets"].values())
            color = theme.warn if is_new else theme.ok
            c.create_oval(x - 13, y - 13, x + 13, y + 13, fill=color,
                          outline="white", width=2)
            c.create_text(x, y + 25, text=n, fill=theme.fg, font=FONT_SMALL)
        c.create_text(w - 140, 20, text="● 已知设备", fill=theme.ok, font=FONT_SMALL, anchor="w")
        c.create_text(w - 40, 20, text="● 新发现", fill=theme.warn, font=FONT_SMALL, anchor="w")

    def import_new(self):
        """把“新增”资产一键写入设备清单（凭据沿用种子设备，协议取探测结果）。"""
        result = getattr(self, "_result", None)
        if not result:
            _msg("提示", "请先执行盘点")
            return
        seed = self.seed_map.get(self.cmb_seed.get())
        added = 0
        for a in result["assets"].values():
            if a.known or not a.ip:
                continue
            if self.app.inventory.find(a.ip, seed.port if seed else 22):
                continue
            from netwright.lib.inventory import Device
            self.app.inventory.devices.append(Device(
                host=a.ip, vendor=a.vendor_guess or seed.vendor,
                username=seed.username, password=seed.password,
                hostname=a.hostname, protocol="telnet" if "Telnet" in a.protocols and "SSH" not in a.protocols else "ssh",
                note="资产盘点发现"))
            added += 1
        self.app.inventory.save()
        self.app.pages["inventory"].refresh()
        _msg("导入完成", f"已把 {added} 台新发现设备加入清单（凭据沿用种子设备，请在清单页核对）")


def _msg(kind, text):
    import tkinter.messagebox as mb
    getattr(mb, kind.lower())("NetWright", text)
