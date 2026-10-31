"""总览工作区页面。"""
from __future__ import annotations

import tkinter as tk

from netforge.lib import HAS_SSH
from netforge.lib import generator as gen
from netforge.theme import (
    ACCENT, AMBER, BG, FG, GREEN, LINE, MUTED, NAVY, NAVY2, PANEL,
)
from netforge.widgets import Page, page_header


def header(title, desc, page):
    page_header(page, title, desc)
class DashboardPage(Page):
    def __init__(self, master, app):
        super().__init__(master, app)
        header("总览", "NetForge 把设备清单、巡检、配置生成和日常小工具收进同一个工作台", self)
        body = tk.Frame(self, bg=BG)
        body.pack(fill=tk.BOTH, expand=True, padx=16, pady=(0, 12))
        self.grid = tk.Frame(body, bg=BG)
        self.grid.pack(fill=tk.X)
        self.cards: dict[str, tk.Label] = {}
        cards = [
            ("inventory", "设备清单", "inventory"),
            ("inspect", "SSH 批量巡检", "inspect"),
            ("generate", "配置生成", "generate"),
            ("toolbox", "日常工具箱", "toolbox"),
        ]
        for i, (title_, desc, key) in enumerate(cards):
            card = tk.Frame(self.grid, bg=PANEL, highlightbackground=LINE, highlightthickness=1)
            card.grid(row=0, column=i, sticky="ew", padx=6, pady=8)
            self.grid.columnconfigure(i, weight=1)
            tk.Label(card, text=title_, bg=PANEL, fg=FG, font=("", 12, "bold")).pack(anchor="w", padx=14, pady=(12, 0))
            stat = tk.Label(card, text="—", bg=PANEL, fg=ACCENT, font=("", 20, "bold"))
            stat.pack(anchor="w", padx=14)
            self.cards[key] = stat
            tk.Label(card, text=desc, bg=PANEL, fg=MUTED, font=("", 9)).pack(anchor="w", padx=14)
            tk.Button(card, text="打开 →", bg=NAVY2, fg=FG, relief=tk.FLAT,
                      activebackground=NAVY, cursor="hand2",
                      command=lambda k=key: self.app.show(k)).pack(anchor="w", padx=14, pady=(4, 12))
        self.refresh()

    def refresh(self):
        inv = self.app.inventory
        self.cards["inventory"].config(text=str(len(inv.devices)))
        self.cards["generate"].config(text=str(len(gen.list_builtin_templates())))
        ssh = "已就绪" if HAS_SSH else "未安装 paramiko"
        self.cards["inspect"].config(text=ssh, fg=GREEN if HAS_SSH else AMBER)
        self.cards["toolbox"].config(text="4 件")


