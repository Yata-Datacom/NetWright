"""命令速查工作区页面。"""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from netforge.lib import cheatsheet
from netforge.theme import FONT_MONO, theme
from netforge.widgets import (Page, page_header)


def header(title, desc, page):
    page_header(page, title, desc)


class CheatPage(Page):
    def __init__(self, master, app):
        super().__init__(master, app)
        header("命令速查", "场景 × 厂商 CLI 备忘；输入关键字即时过滤，双击行复制", self)
        body = tk.Frame(self, bg=theme.bg)
        body.pack(fill=tk.BOTH, expand=True, padx=16, pady=(0, 12))
        row = tk.Frame(body, bg=theme.bg)
        row.pack(fill=tk.X, pady=(2, 6))
        tk.Label(row, text="搜索:", bg=theme.bg, fg=theme.muted).pack(side=tk.LEFT)
        self.ent = tk.Entry(row, bg=theme.panel, fg=theme.fg, relief=tk.FLAT, font=FONT_MONO, width=40, insertbackground=theme.fg)
        self.ent.pack(side=tk.LEFT, padx=(6, 0), ipady=4)
        self.ent.bind("<KeyRelease>", lambda e: self.refresh())
        self.var_count = tk.StringVar()
        tk.Label(row, textvariable=self.var_count, bg=theme.bg, fg=theme.muted, font=("", 9)).pack(side=tk.RIGHT)
        cols = ("scene", "vendor", "title", "cmd")
        wrap = tk.Frame(body, bg=theme.bg)
        wrap.pack(fill=tk.BOTH, expand=True, pady=(6, 0))
        self.tree = ttk.Treeview(wrap, columns=cols, show="headings", height=18)
        for c, t, w in (("scene", "场景", 110), ("vendor", "厂商", 130),
                        ("title", "标题", 180), ("cmd", "命令 / 说明", 440)):
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
        self.app.clipboard_clear()
        self.app.clipboard_append(self.tree.item(sel[0], "values")[3])
        self.app.set_status("已复制到剪贴板")

