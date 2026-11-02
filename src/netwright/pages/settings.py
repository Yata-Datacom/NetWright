"""设置工作区 —— 把"要改代码才能调"的东西搬进界面。

范围刻意克制：只放**真的会影响运行**的几项（端口、刷新、备份、日志、token）。
主题/主色在顶栏，设备与凭据在设备清单，不在这里重复。

生效策略（写清楚，避免用户改完不知道为什么没变）：
  * 事件源端口：保存后立即按新端口重启监听（如果之前是开着的）；
  * REST 端口：需要重启程序（Tk 主循环里换端口会断开正在用的连接，提示即可）；
  * 备份保留份数：立即生效；
  * 备份目录：点「迁移…」立即切换（旧文件原地不动，新快照进新目录）；
  * 日志级别：保存后即时应用到 netwright.* 命名空间；
  * API token：发放/吊销/轮换立即生效并持久化；
  * 自动刷新：立即生效（顶栏勾选与这里同步）。
"""
from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, simpledialog

from netwright.lib.settings import LOG_LEVELS, save_settings
from netwright.theme import FONT_SMALL, FONT_MONO, theme
from netwright.widgets import (Page, SectionCard, WButton, page_header, toast)


def _int_or(value: str, default: int) -> int:
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return default


class SettingsPage(Page):
    """端口 / 刷新 / 备份保留份数。"""

    def __init__(self, master, app):
        super().__init__(master, app)
        page_header(self, "设置", "端口、刷新与备份策略；改动会写入 netwright_settings.json",
                    "系统 / 设置")

        body = tk.Frame(self, bg=theme.bg)
        body.pack(fill=tk.BOTH, expand=True, padx=20, pady=(0, 18))
        body.columnconfigure(0, weight=1)
        body.columnconfigure(1, weight=1)

        # ── 北向与刷新 ──
        net_card = SectionCard(body, title="控制器与刷新",
                               desc="REST 端口改动后需要重启程序")
        net_card.grid(row=0, column=0, sticky="nsew", padx=(0, 10), pady=(0, 12))
        self.var_rest = tk.StringVar()
        self.var_auto = tk.BooleanVar()
        self.var_log = tk.StringVar()
        self._field_row(net_card.body, "REST 端口", self.var_rest,
                        "默认 8899；只监听 127.0.0.1")
        auto_row = tk.Frame(net_card.body, bg=theme.panel)
        auto_row.pack(fill=tk.X, pady=(8, 0))
        tk.Label(auto_row, text="自动刷新", width=12, anchor="w", bg=theme.panel,
                 fg=theme.muted, font=FONT_SMALL).pack(side=tk.LEFT)
        tk.Checkbutton(auto_row, text="每 10 秒刷新当前页", variable=self.var_auto,
                       bg=theme.panel, fg=theme.fg, selectcolor=theme.panel_alt,
                       activebackground=theme.panel, activeforeground=theme.fg,
                       highlightthickness=0, bd=0, font=FONT_SMALL,
                       cursor="hand2").pack(side=tk.LEFT)
        log_row = tk.Frame(net_card.body, bg=theme.panel)
        log_row.pack(fill=tk.X, pady=(8, 0))
        tk.Label(log_row, text="日志级别", width=12, anchor="w", bg=theme.panel,
                 fg=theme.muted, font=FONT_SMALL).pack(side=tk.LEFT)
        self.cmb_log = tk.OptionMenu(log_row, self.var_log, *LOG_LEVELS)
        self.cmb_log.config(font=FONT_SMALL, bg=theme.panel_alt, fg=theme.fg,
                            relief=tk.FLAT, highlightthickness=0, cursor="hand2")
        self.cmb_log.pack(side=tk.LEFT)

        # ── 事件源 ──
        src_card = SectionCard(body, title="事件源",
                               desc="保存后立即按新端口重启（若正在监听）")
        src_card.grid(row=0, column=1, sticky="nsew", padx=(10, 0), pady=(0, 12))
        self.var_syslog = tk.StringVar()
        self.var_trap = tk.StringVar()
        self._field_row(src_card.body, "Syslog 端口", self.var_syslog,
                        "设备侧 logging host <本机> port <端口>")
        self._field_row(src_card.body, "SNMP Trap", self.var_trap,
                        "snmp-server host <本机> traps version 2c …")
        self.var_source = tk.StringVar(value="")
        tk.Label(src_card.body, textvariable=self.var_source, bg=theme.panel,
                 fg=theme.faint, font=FONT_SMALL).pack(anchor="w", pady=(8, 0))
        src_btns = tk.Frame(src_card.body, bg=theme.panel)
        src_btns.pack(fill=tk.X, pady=(6, 0))
        WButton(src_btns, text="启动监听", command=self.start_sources).pack(side=tk.LEFT)
        WButton(src_btns, text="停止", command=self.stop_sources).pack(side=tk.LEFT, padx=(6, 0))

        # ── 备份 ──
        backup_card = SectionCard(body, title="配置备份",
                                  desc="快照目录与保留份数")
        backup_card.grid(row=1, column=0, sticky="nsew", padx=(0, 10))
        self.var_keep = tk.StringVar()
        self._field_row(backup_card.body, "保留份数", self.var_keep,
                        "每台设备最多保留多少份（2-500）")
        row_bd = tk.Frame(backup_card.body, bg=theme.panel)
        row_bd.pack(fill=tk.X, pady=(6, 0))
        tk.Label(row_bd, text="备份目录", width=12, anchor="w", bg=theme.panel,
                 fg=theme.muted, font=FONT_SMALL).pack(side=tk.LEFT)
        self.var_backup_dir = tk.StringVar()
        tk.Entry(row_bd, textvariable=self.var_backup_dir, bg=theme.panel,
                 fg=theme.fg, relief=tk.FLAT, insertbackground=theme.fg,
                 highlightthickness=1, highlightbackground=theme.line,
                 highlightcolor=theme.accent, font=FONT_MONO).pack(
            side=tk.LEFT, fill=tk.X, expand=True, ipady=3, padx=(0, 8))
        WButton(row_bd, text="迁移…", command=self.migrate_backup_dir).pack(side=tk.LEFT)
        store = self.app.controller_store
        root = getattr(getattr(store, "backups", None), "root", "（未启用）")
        tk.Label(backup_card.body, text=f"当前目录：{root}", bg=theme.panel,
                 fg=theme.faint, font=FONT_MONO, wraplength=420,
                 justify=tk.LEFT).pack(anchor="w", pady=(8, 0))

        # ── REST API token 管理（R6/R9）──
        token_card = SectionCard(body, title="REST API Token",
                                 desc="只读 token 仅能 GET；主 token 在「意图与策略 → API」页查看")
        token_card.grid(row=2, column=0, columnspan=2, sticky="nsew",
                        padx=(0, 10), pady=(0, 12))
        self.token_list = tk.Listbox(token_card.body, height=5, bg=theme.panel_alt,
                                     fg=theme.fg, relief=tk.FLAT, font=FONT_MONO,
                                     highlightthickness=0, activestyle="none")
        self.token_list.pack(fill=tk.X, padx=4, pady=(2, 6))
        token_btns = tk.Frame(token_card.body, bg=theme.panel)
        token_btns.pack(fill=tk.X)
        WButton(token_btns, text="发放只读 token",
                command=self.issue_readonly_token).pack(side=tk.LEFT)
        WButton(token_btns, text="吊销选中",
                command=self.revoke_selected_token).pack(side=tk.LEFT, padx=(6, 0))
        WButton(token_btns, text="轮换主 token",
                command=self.rotate_primary_token).pack(side=tk.LEFT, padx=(6, 0))
        self.var_token_note = tk.StringVar(value="")
        tk.Label(token_card.body, textvariable=self.var_token_note, bg=theme.panel,
                 fg=theme.faint, font=FONT_SMALL).pack(anchor="w", pady=(6, 0))

        # ── 保存 ──
        save_card = SectionCard(body, title="保存", desc="校验失败会指出具体哪一项")
        save_card.grid(row=1, column=1, sticky="nsew", padx=(10, 0))
        WButton(save_card.body, text="保存设置", bg=theme.accent,
                command=self.save).pack(anchor="w")
        tk.Label(save_card.body,
                 text="提示：REST 端口改动需重启程序；事件源端口保存后自动重启监听；"
                      "日志级别与 token 变更即时生效。",
                 bg=theme.panel, fg=theme.faint, font=FONT_SMALL,
                 wraplength=420, justify=tk.LEFT).pack(anchor="w", pady=(10, 0))

        self.refresh()

    def _field_row(self, parent, label: str, var: tk.StringVar, hint: str = "",
                   width: int = 10):
        row = tk.Frame(parent, bg=theme.panel)
        row.pack(fill=tk.X, pady=(6, 0))
        tk.Label(row, text=label, width=12, anchor="w", bg=theme.panel,
                 fg=theme.muted, font=FONT_SMALL).pack(side=tk.LEFT)
        entry = tk.Entry(row, textvariable=var, width=width, bg=theme.panel, fg=theme.fg,
                         relief=tk.FLAT, insertbackground=theme.fg,
                         highlightthickness=1, highlightbackground=theme.line,
                         highlightcolor=theme.accent)
        entry.pack(side=tk.LEFT, ipady=3, padx=(0, 10))
        if hint:
            tk.Label(row, text=hint, bg=theme.panel, fg=theme.faint,
                     font=FONT_SMALL).pack(side=tk.LEFT)

    # ── 读写 ──
    def refresh(self):
        settings = self.app.settings
        store = self.app.controller_store
        self.var_rest.set(str(settings.get("rest_port", 8899)))
        self.var_auto.set(bool(settings.get("auto_refresh", True)))
        status = store.listener_status()
        self.var_syslog.set(str(settings.get("syslog_port", 5140)))
        self.var_trap.set(str(settings.get("trap_port", 1162)))
        self.var_keep.set(str(settings.get("backup_keep", 30)))
        self.var_backup_dir.set(str(settings.get("backup_dir", "")))
        self.var_log.set(str(settings.get("log_level", "WARNING")).upper())
        running = []
        if status["syslog"]["running"]:
            running.append(f"Syslog UDP {status['syslog']['port']}")
        if status["snmp_trap"]["running"]:
            running.append(f"Trap UDP {status['snmp_trap']['port']}")
        self.var_source.set("正在监听：" + "、".join(running) if running else "当前未启动监听")
        self._refresh_tokens()

    def _refresh_tokens(self):
        """token 列表：label · scope · 掩码（主 token 排最前）。"""
        auth = self.app.api_auth
        self._token_rows: list[str] = [auth.token]
        self.token_list.delete(0, tk.END)
        self.token_list.insert(tk.END,
                               f"primary · write · {auth.masked()}（主 token）")
        for token, info in auth.export().items():
            self._token_rows.append(token)
            masked = f"{token[:4]}••••••••{token[-4:]}" if len(token) > 8 else "••••••"
            scope_text = "只读" if info["scope"] == "read" else "可写"
            self.token_list.insert(
                tk.END, f"{info['label'] or '未命名'} · {scope_text} · {masked}")
        self.var_token_note.set(
            f"共 {len(self._token_rows)} 个 token；调用来源（IP + label）见事件页「下发审计」")

    def save(self):
        rest = _int_or(self.var_rest.get(), -1)
        syslog = _int_or(self.var_syslog.get(), -1)
        trap = _int_or(self.var_trap.get(), -1)
        keep = _int_or(self.var_keep.get(), -1)
        errors = []
        for label, value in (("REST 端口", rest), ("Syslog 端口", syslog), ("Trap 端口", trap)):
            if not (1 <= value <= 65535):
                errors.append(f"{label} 必须是 1-65535 的整数")
        if not (2 <= keep <= 500):
            errors.append("保留份数必须在 2-500 之间")
        if errors:
            messagebox.showwarning("保存失败", "\n".join(errors))
            return

        settings = self.app.settings
        rest_changed = rest != int(settings.get("rest_port", 8899))
        settings.update({"rest_port": rest, "syslog_port": syslog, "trap_port": trap,
                         "backup_keep": keep, "auto_refresh": bool(self.var_auto.get()),
                         "log_level": self.var_log.get()})
        from netwright.lib.settings import apply_log_level
        apply_log_level(self.var_log.get())          # R9：日志级别即时生效
        save_settings(settings, self.app.base_dir)

        store = self.app.controller_store
        if store.backups is not None:
            store.backups.keep = keep
        was_running = store.syslog.running or store.snmp_trap.running
        if was_running:
            store.stop_listeners()
            store.syslog.port, store.snmp_trap.port = syslog, trap
            store.start_syslog()
            store.start_snmp_trap()

        # 顶栏勾选框同步
        if hasattr(self.app, "var_auto"):
            self.app.var_auto.set(bool(self.var_auto.get()))
            self.app.auto_refresh = bool(self.var_auto.get())
            if self.app.auto_refresh:
                self.app._schedule_auto_refresh()
            else:
                self.app._cancel_auto_refresh()

        self.refresh()
        self.app.event_bus.publish(
            "settings.saved",
            "设置已保存" + ("（REST 端口改动待重启生效）" if rest_changed else ""),
            source="settings", rest_port=rest)
        toast(self.app, "设置已保存", "ok")
        self.app.set_status("设置已保存" + ("；REST 端口需重启程序" if rest_changed else ""))

    def start_sources(self):
        store = self.app.controller_store
        store.syslog.port = _int_or(self.var_syslog.get(), 5140)
        store.snmp_trap.port = _int_or(self.var_trap.get(), 1162)
        try:
            store.start_syslog()
            store.start_snmp_trap()
        except OSError as exc:
            messagebox.showwarning("监听启动失败",
                                   f"端口可能被占用：{exc}\n换一个端口再试。")
            return
        self.refresh()
        self.app.set_status("事件源监听已启动")

    def stop_sources(self):
        self.app.controller_store.stop_listeners()
        self.refresh()
        self.app.set_status("事件源监听已停止")

    # ── R9：备份目录迁移 ──
    def migrate_backup_dir(self):
        """切换备份目录：旧文件原地不动，新快照进新目录（即时持久化）。"""
        new_dir = self.var_backup_dir.get().strip()
        if not new_dir:
            messagebox.showinfo("提示", "填写新的备份目录（留空表示恢复程序目录）。"
                                        "切换后新快照写入新目录，旧文件原地保留。")
            return
        current = str(self.app.settings.get("backup_dir", ""))
        if new_dir == current:
            toast(self.app, "备份目录没有变化", "info")
            return
        if not messagebox.askyesno(
                "迁移备份目录",
                f"新快照将写入：\n{new_dir}\n\n"
                "原目录里的文件保持原地不动（可自行拷走）。继续？"):
            return
        try:
            result = self.app.controller_store.set_backup_dir(new_dir, move=False)
        except OSError as exc:
            messagebox.showwarning("迁移失败", f"目录不可用：{exc}")
            return
        self.app.settings["backup_dir"] = new_dir
        save_settings(self.app.settings, self.app.base_dir)
        toast(self.app, "备份目录已切换（旧文件原地不动）", "ok")
        self.app.set_status(f"备份目录已迁移 → {result['new']}")
        self.refresh()

    # ── R9：REST API token 管理 ──
    def issue_readonly_token(self):
        label = simpledialog.askstring("发放只读 token",
                                       "给这个 token 起个名字（给谁的/干什么用）：",
                                       parent=self)
        if label is None:
            return
        token = self.app.issue_api_token("read", label.strip() or "未命名")
        self._refresh_tokens()
        self.token_list.selection_set(len(self._token_rows) - 1)
        messagebox.showinfo(
            "token 已发放",
            "只读 token（立即生效，仅能 GET）：\n\n"
            f"{token}\n\n"
            "请立即复制保存——关闭本窗口后不再完整显示。")
        self.app.set_status(f"已发放只读 token：{label or '未命名'}")

    def revoke_selected_token(self):
        selection = self.token_list.curselection()
        if not selection:
            toast(self.app, "请先在列表中选中要吊销的 token", "warn")
            return
        index = selection[0]
        token = self._token_rows[index]
        if index == 0:
            toast(self.app, "主 token 不能单独吊销，请用「轮换主 token」", "warn")
            return
        info = self.app.api_auth.tokens.get(token, {})
        if not messagebox.askyesno("吊销 token",
                                   f"确定吊销 {info.get('label', '未命名')} 的 token 吗？"
                                   "使用它的脚本将立即 401。"):
            return
        self.app.revoke_api_token(token)
        self._refresh_tokens()
        toast(self.app, "token 已吊销", "ok")

    def rotate_primary_token(self):
        if not messagebox.askyesno(
                "轮换主 token",
                "轮换后旧主 token 立即失效（GUI 与脚本都要换新 token）。继续？"):
            return
        token = self.app.rotate_api_token()
        self._refresh_tokens()
        messagebox.showinfo("主 token 已轮换",
                            "新主 token（立即生效）：\n\n"
                            f"{token}\n\n"
                            "请立即复制保存。")
        self.app.set_status("主 token 已轮换，旧 token 已失效")
