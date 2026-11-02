"""控制器工作区页面。"""
from __future__ import annotations

import threading
import tkinter as tk
from tkinter import messagebox, ttk

from netwright.lib.controller import deploy as deploy_mod
from netwright.lib.controller import intents as intents_mod
from netwright.lib.inventory import VENDORS
from netwright.theme import FONT_MONO, FONT_SMALL, theme
from netwright.widgets import (Page, SectionCard, page_header, WButton, toast)


def header(title, desc, page):
    page_header(page, title, desc, "控制器 / 意图与策略")


class ControllerPage(Page):
    """意图控制器（OpenDaylight 思路的极简实现）：

      拓扑页   —— LLDP 自动发现 + 画布可视化
      意图页   —— 表单声明意图 → Dry-Run 预览 → 确认下发 → 审计
      API 页   —— 北向 REST 服务开关（供自动化脚本调用）
    """

    def __init__(self, master, app):
        super().__init__(master, app)
        header("意图与策略", "声明意图，控制器翻译成各厂商命令：默认 Dry-Run，确认后才下发（全程审计）", self)
        self.nb = ttk.Notebook(self)
        self.nb.pack(fill=tk.BOTH, expand=True, padx=20, pady=(0, 16))
        self._topo_tab()
        self._intent_tab()
        self._api_tab()

    # ────────── 拓扑 ──────────
    def _topo_tab(self):
        tab = tk.Frame(self.nb, bg=theme.bg)
        self.nb.add(tab, text=" 拓扑发现 ")
        card = SectionCard(tab, title="拓扑已迁移到独立工作区",
                           desc="画布支持缩放/拖拽/节点检查器，链路区分 LLDP 实测与台账来源")
        card.pack(fill=tk.X, pady=(12, 8))
        row = tk.Frame(card.body, bg=theme.panel)
        row.pack(fill=tk.X)
        WButton(row, text="◈ 打开拓扑工作区",
                command=lambda: self.app.show("topology")).pack(side=tk.LEFT)
        WButton(row, text="⟳ 立即发现", command=self.discover).pack(side=tk.LEFT, padx=(8, 0))
        self.var_topo = tk.StringVar(value="")
        tk.Label(card.body, textvariable=self.var_topo, bg=theme.panel,
                 fg=theme.muted, font=("", 9)).pack(anchor="w", pady=(8, 0))

    def discover(self):
        """委托给拓扑工作区（发现逻辑与渲染只有一处实现）。"""
        topo_page = self.app.pages.get("topology")
        if topo_page is None:
            return
        self.app.show("topology")
        if hasattr(topo_page, "discover"):
            topo_page.discover()
        self.var_topo.set("已切到拓扑工作区，发现进度见该页状态栏")

    # ────────── 意图下发 ──────────
    def _intent_tab(self):
        tab = tk.Frame(self.nb, bg=theme.bg)
        self.nb.add(tab, text=" 意图下发 ")
        self.intent_items = intents_mod.list_intents()

        top = SectionCard(tab, title="声明意图", desc="意图目录驱动表单；控制器负责翻译成各厂商命令")
        top.pack(fill=tk.X, pady=(12, 10))
        bar = tk.Frame(top.body, bg=theme.panel)
        bar.pack(fill=tk.X)
        tk.Label(bar, text="意图类型", bg=theme.panel, fg=theme.muted,
                 font=FONT_SMALL).pack(side=tk.LEFT)
        self.cmb_intent = ttk.Combobox(bar, state="readonly", width=22,
                                       values=[i["title"] for i in self.intent_items])
        self.cmb_intent.current(0)
        self.cmb_intent.pack(side=tk.LEFT, padx=(6, 18))
        self.cmb_intent.bind("<<ComboboxSelected>>", lambda e: self._render_fields())

        tk.Label(bar, text="目标设备", bg=theme.panel, fg=theme.muted,
                 font=FONT_SMALL).pack(side=tk.LEFT)
        self.cmb_target = ttk.Combobox(bar, state="readonly", width=26)
        self.cmb_target.pack(side=tk.LEFT, padx=(6, 0))

        self.fields_frame = tk.Frame(top.body, bg=theme.panel)
        self.fields_frame.pack(fill=tk.X, pady=(10, 0))

        bottom = SectionCard(tab, title="Dry-Run 计划", desc="预览绝不连接设备；确认后才真实下发并审计")
        bottom.pack(fill=tk.BOTH, expand=True)
        btns = tk.Frame(bottom.body, bg=theme.panel)
        btns.pack(fill=tk.X, pady=(0, 8))
        WButton(btns, text="① Dry-Run 预览", bg=theme.accent,
                command=self.dry_run).pack(side=tk.LEFT)
        self.btn_apply = WButton(btns, text="② 确认下发", bg=theme.warn, fg="#1c1200",
                                 state=tk.DISABLED, command=self.apply)
        self.btn_apply.pack(side=tk.LEFT, padx=(8, 0))
        self.var_intent = tk.StringVar(value="")
        tk.Label(btns, textvariable=self.var_intent, bg=theme.panel, fg=theme.muted,
                 font=FONT_SMALL).pack(side=tk.RIGHT)

        self.preview = tk.Text(bottom.body, bg=theme.code_bg, fg="#D7E2F2", relief=tk.FLAT,
                               font=FONT_MONO, height=14, insertbackground=theme.fg,
                               highlightthickness=0, bd=0, padx=10, pady=8)
        self.preview.pack(fill=tk.BOTH, expand=True)
        self.preview.tag_config("dev", foreground=theme.chrome_accent,
                                font=("", 10, "bold"))
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
            row = tk.Frame(self.fields_frame, bg=theme.panel)
            row.pack(fill=tk.X, pady=2)
            mark = "*" if f["required"] else ""
            tk.Label(row, text=f"{f['label']}{mark}", bg=theme.panel, fg=theme.muted,
                     width=16, anchor="w", font=FONT_SMALL).pack(side=tk.LEFT)
            var = tk.StringVar(value=f["default"] or "")
            self.field_vars[f["name"]] = var
            if f["type"] == "choice":
                w = ttk.Combobox(row, textvariable=var, state="readonly", width=28,
                                 values=[str(c) for c in f["choices"]])
                if f["choices"]:
                    w.current(0)
            else:
                w = tk.Entry(row, textvariable=var, bg=theme.panel, fg=theme.fg,
                             relief=tk.FLAT, width=32, insertbackground=theme.fg,
                             highlightthickness=1, highlightbackground=theme.line,
                             highlightcolor=theme.accent)
            w.pack(side=tk.LEFT, ipady=3, padx=(4, 0))
            if f["hint"]:
                tk.Label(row, text=f["hint"], bg=theme.panel, fg=theme.faint,
                         font=("Microsoft YaHei UI", 8)).pack(side=tk.LEFT, padx=(10, 0))
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

        card = SectionCard(tab, title="北向接口",
                           desc="v1 面向脚本化既有功能，v2 是控制器语义接口（拓扑/事件/策略）")
        card.pack(fill=tk.BOTH, expand=True, pady=(12, 10))
        info = (
            "v2 控制器接口\n"
            "  GET  /api/v2/health              健康与统计\n"
            "  GET  /api/v2/topology            控制器图（节点/链路）\n"
            "  GET  /api/v2/events?limit=50     事件流\n"
            "  GET  /api/v2/policies            已编译策略\n"
            "  GET  /api/v2/southbound          南向适配器与能力位\n"
            "  POST /api/v2/policies/compile    意图 → 策略（不连设备）\n"
            "  POST /api/v2/topology/sync       设备清单 → 图\n\n"
            "v1 兼容接口\n"
            "  GET  /api/devices · /api/intents · /api/topology\n"
            "  POST /api/dry-run · /api/apply（需 \"confirm\": true）\n\n"
            "示例\n"
            "  curl http://127.0.0.1:8899/api/v2/snapshot\n"
            "  curl -X POST http://127.0.0.1:8899/api/v2/policies/compile \\\n"
            "       -H \"Content-Type: application/json\" \\\n"
            "       -d '{\"intent_key\":\"vlan_deploy\",\"params\":{\"vlans\":\"10,20\"}}'\n")
        tk.Label(card.body, text=info, bg=theme.panel, fg=theme.fg, font=FONT_MONO,
                 justify="left").pack(anchor="w")
        row = tk.Frame(card.body, bg=theme.panel)
        row.pack(fill=tk.X, pady=(10, 0))
        self.var_api = tk.StringVar(value="API 服务未启动")
        tk.Label(row, textvariable=self.var_api, bg=theme.panel, fg=theme.muted,
                 font=FONT_SMALL).pack(side=tk.LEFT)
        self.btn_api = WButton(row, text="启动 REST 服务", bg=theme.accent,
                               command=self.toggle_api)
        self.btn_api.pack(side=tk.RIGHT)

        tok = tk.Frame(card.body, bg=theme.panel)
        tok.pack(fill=tk.X, pady=(10, 0))
        tk.Label(tok, text="API Token", bg=theme.panel, fg=theme.muted,
                 font=FONT_SMALL).pack(side=tk.LEFT)
        self.var_token = tk.StringVar(value="")
        tk.Label(tok, textvariable=self.var_token, bg=theme.panel_alt, fg=theme.fg,
                 font=FONT_MONO, padx=8, pady=2).pack(side=tk.LEFT, padx=(8, 8))
        WButton(tok, text="复制", command=self.copy_token).pack(side=tk.LEFT, padx=(0, 6))
        WButton(tok, text="轮换", command=self.rotate_token).pack(side=tk.LEFT)
        tk.Label(tok, text="除 /health 外，v2 请求都要带 Authorization: Bearer <token>",
                 bg=theme.panel, fg=theme.faint, font=FONT_SMALL).pack(side=tk.RIGHT)
        self._refresh_token()

        audit = SectionCard(tab, title="下发审计", desc="最近 30 条，新在上（不含密码）")
        audit.pack(fill=tk.X)
        self.audit_text = tk.Text(audit.body, bg=theme.panel_alt, fg=theme.muted,
                                  relief=tk.FLAT, font=FONT_MONO, height=6,
                                  highlightthickness=0, bd=0, padx=8, pady=6)
        self.audit_text.pack(fill=tk.X)

    def _refresh_token(self):
        auth = getattr(self.app, "api_auth", None)
        self.var_token.set(auth.masked() if auth is not None else "（disabled）")

    def copy_token(self):
        auth = getattr(self.app, "api_auth", None)
        if auth is None:
            return
        self.app.clipboard_clear()
        self.app.clipboard_append(auth.token)
        toast(self.app, "API token 已复制到剪贴板", "ok")

    def rotate_token(self):
        self.app.rotate_api_token()
        self._refresh_token()
        toast(self.app, "API token 已轮换：旧 token 立即失效", "ok")

    def toggle_api(self):
        if self.app.controller_api.running:
            self.app.controller_api.stop()
            self.var_api.set("API 服务未启动")
            self.btn_api.config(text="启动 REST 服务", bg=theme.accent)
        else:
            self.app.controller_api.start()
            self.var_api.set(f"API 运行中：http://127.0.0.1:{self.app.controller_api.port}")
            self.btn_api.config(text="停止 REST 服务", bg=theme.err)

    def refresh_audit(self):
        """把最近审计记录展示（最新 30 条，新在上）。"""
        entries = deploy_mod.audit_tail(30)
        box = getattr(self, "audit_text", None)
        if box is None:
            return
        box.delete("1.0", tk.END)
        for e in reversed(entries):
            box.insert(tk.END,
                       f"{e.get('time', '')}  {e.get('action', '')}  {e.get('intent', '')}  "
                       f"{e.get('device', e.get('skipped', ''))}  → {e.get('status', '')}\n")
        if not entries:
            box.insert(tk.END, "（暂无审计记录）")
