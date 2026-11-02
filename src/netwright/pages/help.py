"""help.py — 新手引导面板（小白的第一站）。

设计取向：**不问"你想做什么"，而是直接给三条最短路径**：
  ① 没设备 → 载入演示数据，先看看界面长什么样；
  ② 有设备 → 看拓扑、跑巡检；
  ③ 想下发 → 走一遍 Dry-Run，知道"预览不等于真下发"。

所有动作都能一键直达，不要求用户先读文档。
"""
from __future__ import annotations

import os
import tkinter as tk

from ..theme import FONT_SMALL, theme
from ..widgets import WButton, toast
from .. import demo

STEPS = [
    ("1", "载入演示数据", "用 192.0.2.x 文档网段的 7 台假设备，立刻看到拓扑、事件与策略。\n"
                          "不会覆盖你已有的设备，随时可以一键清除。", "demo"),
    ("2", "看看拓扑长什么样", "左侧「控制器 → 拓扑」：滚轮缩放、拖拽平移，点节点看邻居与端口。\n"
                              "实线是 LLDP 实测，虚线是台账登记。", "topology"),
    ("3", "试一次意图下发", "「控制器 → 意图与策略 → 意图下发」：选 VLAN 部署，填 10,20，\n"
                            "先点「Dry-Run 预览」——它不会碰设备，只告诉你将要发什么命令。", "controller"),
    ("4", "跑一轮批量巡检", "「运维 → 批量巡检」：勾设备、选方案、点开始。\n"
                            "设备不可达也没关系，状态会显示「不可达」，这是预期行为。", "inspect"),
]

SHORTCUTS = [
    ("F5", "刷新当前页面"),
    ("Ctrl+H", "打开这个新手引导"),
    ("Ctrl+1 … Ctrl+9", "按顺序切换左侧工作区"),
    ("Esc", "关闭弹窗 / 抽屉"),
]


class HelpDialog(tk.Toplevel):
    """模态新手引导。"""

    def __init__(self, app):
        super().__init__(app)
        self.app = app
        self.title("新手引导 · 5 分钟上手")
        self.configure(bg=theme.bg)
        self.transient(app)
        self.resizable(False, False)
        w, h = 760, 660
        x = app.winfo_rootx() + max(0, (app.winfo_width() - w) // 2)
        y = app.winfo_rooty() + max(0, (app.winfo_height() - h) // 2)
        self.geometry(f"{w}x{h}+{x}+{y}")
        self._build()
        self.protocol("WM_DELETE_WINDOW", self.close)
        self.bind("<Escape>", lambda _e: self.close())
        try:
            self.grab_set()
        except tk.TclError:
            pass

    def _build(self):
        head = tk.Frame(self, bg=theme.chrome, height=64)
        head.pack(fill=tk.X)
        head.pack_propagate(False)
        tk.Label(head, text="5 分钟上手 NetWright", bg=theme.chrome, fg=theme.chrome_fg,
                 font=("Microsoft YaHei UI", 14, "bold")).pack(side=tk.LEFT, padx=18)
        tk.Label(head, text="从零到看懂一台网络", bg=theme.chrome,
                 fg=theme.chrome_muted, font=FONT_SMALL).pack(side=tk.LEFT, padx=(0, 0))

        body = tk.Frame(self, bg=theme.bg)
        body.pack(fill=tk.BOTH, expand=True, padx=18, pady=14)

        for num, title, desc, action in STEPS:
            card = tk.Frame(body, bg=theme.panel, highlightbackground=theme.line,
                            highlightthickness=1)
            card.pack(fill=tk.X, pady=(0, 8))
            left = tk.Frame(card, bg=theme.panel)
            left.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=14, pady=10)
            row = tk.Frame(left, bg=theme.panel)
            row.pack(anchor="w")
            badge = tk.Canvas(row, width=20, height=20, bg=theme.panel, highlightthickness=0)
            badge.pack(side=tk.LEFT, padx=(0, 8))
            badge.create_oval(1, 1, 19, 19, fill=theme.accent_soft, outline="")
            badge.create_text(10, 10, text=num, fill=theme.accent, font=("", 9, "bold"))
            tk.Label(row, text=title, bg=theme.panel, fg=theme.fg,
                     font=("Microsoft YaHei UI", 11, "bold")).pack(side=tk.LEFT)
            tk.Label(left, text=desc, bg=theme.panel, fg=theme.muted, font=FONT_SMALL,
                     justify=tk.LEFT, anchor="w").pack(anchor="w", padx=(28, 0), pady=(4, 0))
            WButton(card, text="去这里 →",
                    command=lambda a=action: self._go(a)).pack(side=tk.RIGHT, padx=14)

        shortcuts = tk.Frame(body, bg=theme.panel, highlightbackground=theme.line,
                             highlightthickness=1)
        shortcuts.pack(fill=tk.X, pady=(2, 8))
        tk.Label(shortcuts, text="快捷键", bg=theme.panel, fg=theme.muted,
                 font=FONT_SMALL).pack(anchor="w", padx=14, pady=(10, 2))
        grid = tk.Frame(shortcuts, bg=theme.panel)
        grid.pack(fill=tk.X, padx=14, pady=(0, 10))
        for i, (keys, what) in enumerate(SHORTCUTS):
            col = i % 2
            row_i = i // 2
            cell = tk.Frame(grid, bg=theme.panel)
            cell.grid(row=row_i, column=col, sticky="w", pady=2, padx=(0, 24))
            tk.Label(cell, text=keys, bg=theme.panel_alt, fg=theme.fg,
                     font=("Consolas", 9), padx=6, pady=1).pack(side=tk.LEFT)
            tk.Label(cell, text=what, bg=theme.panel, fg=theme.muted,
                     font=FONT_SMALL).pack(side=tk.LEFT, padx=(8, 0))

        foot = tk.Frame(self, bg=theme.panel)
        foot.pack(fill=tk.X, side=tk.BOTTOM)
        inner = tk.Frame(foot, bg=theme.panel)
        inner.pack(fill=tk.X, padx=18, pady=10)
        WButton(inner, text="📖 打开完整用户指南", command=self._open_guide).pack(side=tk.LEFT)
        WButton(inner, text="🧹 清除演示数据", command=self._clear_demo).pack(
            side=tk.LEFT, padx=(8, 0))
        WButton(inner, text="关闭", bg=theme.accent, command=self.close).pack(side=tk.RIGHT)

    # ── 动作 ──
    def _go(self, action: str):
        if action == "demo":
            self._load_demo()
            return
        self.close()
        self.app.show(action)
        if action == "controller":
            page = self.app.pages.get("controller")
            if page is not None and hasattr(page, "nb"):
                page.nb.select(1)

    def _load_demo(self):
        devices, links = demo.seed(self.app.inventory)
        self.app.controller_store.graph.clear()
        self.app.controller_store.sync_inventory()
        self.app.event_bus.publish(
            "demo.loaded",
            f"已载入演示数据：{devices} 台设备 / {links} 条台账链路",
            source="help")
        self.app.refresh_dashboard()
        toast(self.app, f"演示数据就绪：{devices} 台设备 / {links} 条链路", "ok")
        self.close()
        self.app.show("topology")
        self.app.set_status("演示数据已载入：先看拓扑，再去「意图与策略」试一次 Dry-Run")

    def _clear_demo(self):
        removed = self.app.clear_demo_data()
        toast(self.app, f"已清除 {removed} 台演示设备", "info")

    def _open_guide(self):
        path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
            os.path.abspath(__file__)))), "..", "docs", "USER_GUIDE.zh-CN.md")
        path = os.path.abspath(path)
        if os.path.isfile(path):
            try:
                os.startfile(path)      # noqa: S606  Windows 打开本地文档
                return
            except OSError:
                pass
        toast(self.app, "未找到用户指南（docs/USER_GUIDE.zh-CN.md）", "warn")

    def close(self):
        try:
            self.grab_release()
        except tk.TclError:
            pass
        self.destroy()


def show_help(app):
    """打开引导面板；已打开则前置。"""
    existing = getattr(app, "_help_dialog", None)
    if existing is not None and existing.winfo_exists():
        existing.lift()
        return existing
    dialog = HelpDialog(app)
    app._help_dialog = dialog
    return dialog
