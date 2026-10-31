"""widgets.py — 可复用 UI 组件库（云控制台风格）。

  page_header  页面标题区（标题 + 说明 + 品牌强调线 + 右侧动作槽）
  Card         白色卡片容器（统一边框/圆角感/内边距）
  StatCard     总览统计卡（大数字 + 标签 + 打开按钮，顶部强调条）
  PillLabel    状态徽章（语义色：ok/warn/err/info）
  make_table   标准数据表（表头/列宽/斑马纹一次配好）
  EmptyState   空状态占位
"""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from .theme import FONT_BOLD, FONT_SMALL, theme


class Card(tk.Frame):
    """标准卡片容器：panel 底色 + 1px 边框 + 统一内边距。"""

    def __init__(self, master, title: str = "", padding: int = 14, **kw):
        super().__init__(master, bg=theme.panel,
                         highlightbackground=theme.line, highlightthickness=1, **kw)
        self.body = tk.Frame(self, bg=theme.panel)
        self.body.pack(fill=tk.BOTH, expand=True, padx=padding, pady=padding)
        if title:
            tk.Label(self.body, text=title, bg=theme.panel, fg=theme.fg,
                     font=FONT_BOLD).pack(anchor="w", pady=(0, 8))


class Page(tk.Frame):
    """工作区页面基类：持有 app 引用（inventory/controller_api 等）。"""

    def __init__(self, master, app):
        super().__init__(master, bg=theme.bg)
        self.app = app


def page_header(parent: tk.Frame, title: str, desc: str) -> None:
    """页面标题区：标题 + 一句说明 + 品牌强调线。"""
    bar = tk.Frame(parent, bg=theme.bg)
    bar.pack(fill=tk.X, padx=18, pady=(14, 8))
    tk.Label(bar, text=title, bg=theme.bg, fg=theme.fg,
             font=("Microsoft YaHei UI", 16, "bold")).pack(anchor="w")
    tk.Label(bar, text=desc, bg=theme.bg, fg=theme.muted, font=FONT_SMALL).pack(anchor="w")
    tk.Frame(parent, bg=theme.accent, height=2).pack(fill=tk.X, padx=18)


def stat_card(parent, title: str, desc: str, command=None) -> tk.Label:
    """总览统计卡：顶部强调条 + 大数字（返回数字 Label 供刷新）+ 打开按钮。"""
    card = tk.Frame(parent, bg=theme.panel,
                    highlightbackground=theme.line, highlightthickness=1)
    tk.Frame(card, bg=theme.accent, height=3).pack(fill=tk.X)
    tk.Label(card, text=title, bg=theme.panel, fg=theme.muted,
             font=FONT_SMALL).pack(anchor="w", padx=16, pady=(12, 0))
    stat = tk.Label(card, text="—", bg=theme.panel, fg=theme.accent,
                    font=("Microsoft YaHei UI", 20, "bold"))
    stat.pack(anchor="w", padx=16)
    tk.Label(card, text=desc, bg=theme.panel, fg=theme.muted,
             font=FONT_SMALL).pack(anchor="w", padx=16)
    tk.Button(card, text="打开 →", bg=theme.accent_soft, fg=theme.fg, relief=tk.FLAT,
              activebackground=theme.accent, activeforeground="white", cursor="hand2",
              font=FONT_SMALL, command=command).pack(anchor="w", padx=16, pady=(4, 12))
    return stat


def pill_text(text: str, kind: str) -> str:
    """状态列的文本徽章（表格里用 tag 上色）。"""
    marks = {"ok": "● ", "warn": "▲ ", "err": "✖ ", "info": "ℹ "}
    return marks.get(kind, "") + text


def make_table(parent, columns: list[str], headings: dict[str, str],
               widths: dict[str, int], height: int = 15,
               selectmode: str = "browse") -> tuple[tk.Frame, ttk.Treeview]:
    """标准数据表：外框 + 表头 + 斑马纹 tag。返回 (容器, treeview)。"""
    wrap = tk.Frame(parent, bg=theme.line,
                    highlightbackground=theme.line, highlightthickness=1)
    tree = ttk.Treeview(wrap, columns=columns, show="headings", height=height,
                        selectmode=selectmode)
    for c in columns:
        tree.heading(c, text=headings[c])
        tree.column(c, width=widths[c], anchor="center" if c in ("port", "state",
                    "status", "alive", "delay", "critical", "warn", "cost", "sev")
                    else "w", stretch=True)
    vsb = ttk.Scrollbar(wrap, orient=tk.VERTICAL, command=tree.yview)
    tree.configure(yscrollcommand=vsb.set)
    tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
    vsb.pack(side=tk.RIGHT, fill=tk.Y)
    tree.tag_configure("even", background=theme.panel)
    tree.tag_configure("odd", background=theme.panel_alt)
    return wrap, tree


def zebra(tree: ttk.Treeview, iid: str, index: int):
    """插入行后调用：按奇偶行打斑马纹 tag。"""
    tags = list(tree.item(iid, "tags"))
    tags.append("even" if index % 2 == 0 else "odd")
    tree.item(iid, tags=tags)


def empty_state(parent, text: str) -> tk.Label:
    return tk.Label(parent, text=text, bg=theme.bg, fg=theme.faint,
                    font=FONT_SMALL, pady=30)
