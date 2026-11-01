"""控制器工作区页面。"""
from __future__ import annotations

import threading
import tkinter as tk
from tkinter import messagebox, ttk

from netwright.lib.controller import deploy as deploy_mod
from netwright.lib.controller import intents as intents_mod
from netwright.lib.inventory import VENDORS
from netwright.theme import FONT_MONO, theme
from netwright.widgets import (Page, page_header, WButton, toast)


def header(title, desc, page):
    page_header(page, title, desc)


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
        tab = tk.Frame(self.nb, bg=theme.bg)
        self.nb.add(tab, text=" 拓扑发现 ")
        bar = tk.Frame(tab, bg=theme.bg)
        bar.pack(fill=tk.X, pady=(8, 4))
        self.btn_discover = WButton(bar, text="从设备清单自动发现拓扑 (LLDP/CDP)",
                                      bg=theme.accent, fg="white", relief=tk.FLAT,
                                      activebackground=theme.nav2, command=self.discover)
        self.btn_discover.pack(side=tk.LEFT)
        self.var_topo = tk.StringVar(value="尚未发现")
        tk.Label(bar, textvariable=self.var_topo, bg=theme.bg, fg=theme.muted, font=("", 9)).pack(side=tk.LEFT, padx=10)
        self.canvas = tk.Canvas(tab, bg=theme.code_bg, highlightthickness=0)
        self.canvas.pack(fill=tk.BOTH, expand=True, pady=(4, 0))
        self.canvas.create_text(480, 300, text="点击上方按钮开始发现拓扑\n（需要设备已开启 LLDP/CDP 且可 SSH 登录）",
                                fill=theme.muted, font=("", 11), tags="placeholder")

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
        # 合并台账链路（虚线）：从清单 links 生成
        ledger = []
        names = {d.host: (d.hostname or d.host) for d in self.app.inventory.devices}
        for lk in self.app.inventory.links:
            a = names.get(lk.device_host, lk.device_host)
            b = names.get(lk.peer_host, lk.peer_host)
            ledger.append((a, lk.local_intf, b, lk.peer_intf))
        from netwright.lib.controller.topology import Topology, Link
        merged = Topology(nodes=topo.nodes, links=topo.links)
        for a, li, b, pi in ledger:
            merged.nodes.update([a, b])
            merged.links.append(Link(a, li, b, pi))
        self.app.controller_state.topology = merged
        edges = merged.undirected_edges()
        ledger_keys = {tuple(sorted((a, b))) for a, _li, b, _pi in ledger}
        self.var_topo.set(f"{len(merged.nodes)} 台设备 · {len(edges)} 条链路"
                          f"（含台账 {len(ledger)} 条）")
        self._draw_topology(merged, ledger_keys)

    def _draw_topology(self, topo):
        import math
        self.canvas.delete("all")
        nodes = sorted(topo.nodes)
        if not nodes:
            self.canvas.create_text(480, 300, text="未发现任何邻居（检查 LLDP 是否开启）",
                                    fill=theme.muted, font=("", 11))
            return
        w = max(self.canvas.winfo_width(), 900)
        h = max(self.canvas.winfo_height(), 600)
        cx, cy, r = w / 2, h / 2, min(w, h) * 0.36
        pos = {n: (cx + r * math.cos(2 * math.pi * i / len(nodes)),
                   cy + r * math.sin(2 * math.pi * i / len(nodes)))
               for i, n in enumerate(nodes)}
        for a, ai, b, bi in topo.undirected_edges():
            if a in pos and b in pos:
                self.canvas.create_line(*pos[a], *pos[b], fill=theme.muted, width=2, dash=(6, 3))
                mx, my = (pos[a][0] + pos[b][0]) / 2, (pos[a][1] + pos[b][1]) / 2
                self.canvas.create_text(mx, my, text=f"{ai}↔{bi}", fill=theme.muted, font=("", 8))
        inv = {d.host: d for d in self.app.inventory.devices}
        for n, (x, y) in pos.items():
            dev = next((d for d in inv.values()
                        if (d.hostname or d.host) == n or d.host == n), None)
            from netwright.theme import VENDOR_COLORS
            color = VENDOR_COLORS.get(dev.vendor if dev else "", theme.faint)
            self.canvas.create_oval(x - 14, y - 14, x + 14, y + 14, fill=color, outline="white", width=2)
            self.canvas.create_text(x, y + 26, text=n, fill=theme.fg, font=("", 9))

    # ────────── 意图下发 ──────────
    def _intent_tab(self):
        tab = tk.Frame(self.nb, bg=theme.bg)
        self.nb.add(tab, text=" 意图下发 ")
        self.intent_items = intents_mod.list_intents()

        bar = tk.Frame(tab, bg=theme.bg)
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

        frm = tk.Frame(tab, bg=theme.bg)
        frm.pack(fill=tk.X, pady=(4, 6))
        self.fields_frame = tk.Frame(frm, bg=theme.bg)
        self.fields_frame.pack(fill=tk.X)

        btns = tk.Frame(tab, bg=theme.bg)
        btns.pack(fill=tk.X, pady=(0, 6))
        WButton(btns, text="① Dry-Run 预览（不连接设备）", bg=theme.nav2, fg=theme.fg, relief=tk.FLAT,
                  activebackground=theme.nav1, command=self.dry_run).pack(side=tk.LEFT)
        self.btn_apply = WButton(btns, text="② 确认下发", bg=theme.warn, fg="#1c1200", relief=tk.FLAT,
                                   activebackground=theme.warn, state=tk.DISABLED, command=self.apply)
        self.btn_apply.pack(side=tk.LEFT, padx=(8, 0))
        self.var_intent = tk.StringVar(value="")
        tk.Label(btns, textvariable=self.var_intent, bg=theme.bg, fg=theme.muted, font=("", 9)).pack(side=tk.RIGHT)

        self.preview = tk.Text(tab, bg=theme.code_bg, fg=theme.fg, relief=tk.FLAT, font=FONT_MONO, height=18,
                               insertbackground=theme.fg)
        self.preview.pack(fill=tk.BOTH, expand=True)
        self.preview.tag_config("dev", foreground=theme.accent, font=("", 10, "bold"))
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
            row = tk.Frame(self.fields_frame, bg=theme.bg)
            row.pack(fill=tk.X, pady=2)
            mark = "*" if f["required"] else ""
            tk.Label(row, text=f"{f['label']}{mark}:", bg=theme.bg, fg=theme.muted, width=22,
                     anchor="w").pack(side=tk.LEFT)
            var = tk.StringVar(value=f["default"] or "")
            self.field_vars[f["name"]] = var
            if f["type"] == "choice":
                w = ttk.Combobox(row, textvariable=var, state="readonly", width=28,
                                 values=[str(c) for c in f["choices"]])
                if f["choices"]:
                    w.current(0)
            else:
                w = tk.Entry(row, textvariable=var, bg=theme.panel, fg=theme.fg, relief=tk.FLAT,
                             width=34, insertbackground=theme.fg)
            w.pack(side=tk.LEFT, ipady=3)
            if f["hint"]:
                tk.Label(row, text=f"  {f['hint']}", bg=theme.bg, fg=theme.muted, font=("", 8)).pack(side=tk.LEFT)
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
            self.preview.delete("1.0", tk.END)
            self.preview.insert(tk.END, f"✖ 参数错误：{e}", "dev")
            toast(self.app, f"参数错误：{e}", "err")
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
        toast(self.app, f"意图下发完成：成功 {ok} / 警告 {warn} / 失败 {fail}",
              "ok" if fail == 0 and warn == 0 else "warn")
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
        tab = tk.Frame(self.nb, bg=theme.bg)
        self.nb.add(tab, text=" REST API ")
        info = (
            "把 NetWright 控制器开放成本机 REST 服务，供自动化脚本/CI 调用。\n\n"
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
        tk.Label(tab, text=info, bg=theme.bg, fg=theme.fg, font=FONT_MONO, justify="left").pack(
            anchor="w", padx=14, pady=(12, 8))
        row = tk.Frame(tab, bg=theme.bg)
        row.pack(fill=tk.X, padx=14)
        self.var_api = tk.StringVar(value="API 服务未启动")
        tk.Label(row, textvariable=self.var_api, bg=theme.bg, fg=theme.muted, font=("", 10)).pack(side=tk.LEFT)
        self.btn_api = WButton(row, text="启动 REST 服务 (127.0.0.1:8899)", bg=theme.accent, fg="white",
                                 relief=tk.FLAT, activebackground=theme.nav2, command=self.toggle_api)
        self.btn_api.pack(side=tk.LEFT, padx=(16, 0))

    def toggle_api(self):
        if self.app.controller_api.running:
            self.app.controller_api.stop()
            self.var_api.set("API 服务未启动")
            self.btn_api.config(text="启动 REST 服务 (127.0.0.1:8899)", bg=theme.accent)
        else:
            self.app.controller_api.start()
            self.var_api.set("API 服务运行中: http://127.0.0.1:8899")
            self.btn_api.config(text="停止 REST 服务", bg=theme.err, fg="white")



    def refresh_audit(self):
        """把最近审计记录展示（最新 30 条，新在上）。"""
        entries = deploy_mod.audit_tail(30)
        box = getattr(self, "audit_text", None)
        if box is None:
            box = tk.Text(self, bg=theme.panel_alt, fg=theme.muted, relief=tk.FLAT,
                          font=FONT_MONO, height=6, insertbackground=theme.fg)
            self.audit_text = box
            box.pack(fill=tk.X, side=tk.BOTTOM)
        box.delete("1.0", tk.END)
        for e in reversed(entries):
            box.insert(tk.END,
                       f"{e.get('time','')}  {e.get('action','')}  {e.get('intent','')}  "
                       f"{e.get('device', e.get('skipped',''))}  → {e.get('status','')}")
        if not entries:
            box.insert(tk.END, "（暂无审计记录）")
