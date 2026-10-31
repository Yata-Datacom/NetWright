"""theme.py — 设计令牌（Design Tokens）与全局 ttk 样式。

参考云计算厂商控制台的视觉语言：
  * 中性浅灰画布 + 白色卡片 + 细边框 + 克制的品牌色
  * 状态色语义化（成功/警告/危险/信息），只用于状态，不做装饰
  * 排版三级：标题 15 bold / 正文 10 / 辅助 9 muted
同时提供暗色（默认）与亮色两套令牌，页面代码只引用符号、不写裸色值。
"""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk

# ── 品牌 ──────────────────────────────────────────────────────────────
BRAND = "#1a66ff"          # 主品牌蓝（云控制台主色）
BRAND_DARK = "#0e4fce"
BRAND_SOFT = "#e8f0ff"     # 选中底色（亮色）

# ── 暗色令牌（默认）──────────────────────────────────────────────────
DARK = {
    "bg": "#0d1420",           # 画布
    "panel": "#111b2e",        # 卡片
    "panel_alt": "#0a1120",    # 卡内深色区（代码/输出）
    "line": "#22314c",         # 边框
    "fg": "#e8eef8",
    "muted": "#8ba0c0",
    "faint": "#5b6c8c",
    "accent": "#3b82f6",
    "accent_soft": "#16294a",
    "ok": "#22c55e",
    "warn": "#f59e0b",
    "err": "#ef4444",
    "info": "#38bdf8",
}

# ── 亮色令牌 ─────────────────────────────────────────────────────────
LIGHT = {
    "bg": "#f2f5fa",
    "panel": "#ffffff",
    "panel_alt": "#f7f9fc",
    "line": "#d9e1ec",
    "fg": "#17233d",
    "muted": "#5b6b84",
    "faint": "#94a3b8",
    "accent": "#1a66ff",
    "accent_soft": "#e8f0ff",
    "ok": "#16a34a",
    "warn": "#d97706",
    "err": "#dc2626",
    "info": "#0284c7",
}

# ── 字体 ─────────────────────────────────────────────────────────────
FONT = ("Microsoft YaHei UI", 10)
FONT_BOLD = ("Microsoft YaHei UI", 10, "bold")
FONT_H1 = ("Microsoft YaHei UI", 15, "bold")
FONT_H2 = ("Microsoft YaHei UI", 11, "bold")
FONT_SMALL = ("Microsoft YaHei UI", 9)
FONT_MONO = ("Consolas", 10)
FONT_MONO_SMALL = ("Consolas", 9)


# ── 模块级常量（暗色令牌的静态别名）────────────────────────────────
# 页面代码可直接 `from netforge.theme import BG, PANEL...`；
# 亮色切换通过 Theme.use + 重启生效（常量为加载时快照）。
BG = DARK["bg"]
PANEL = DARK["panel"]
PANEL_ALT = DARK["panel_alt"]
LINE = DARK["line"]
FG = DARK["fg"]
MUTED = DARK["muted"]
FAINT = DARK["faint"]
ACCENT = DARK["accent"]
ACCENT_SOFT = DARK["accent_soft"]
OK = DARK["ok"]
WARN = DARK["warn"]
ERR = DARK["err"]
INFO = DARK["info"]
GREEN, AMBER, RED = OK, WARN, ERR
INFO = DARK["info"]

# ── 导航底色（深海军蓝，与卡片区分）──
NAVY = "#0b1f3a"
NAVY2 = "#12294a"
MONO = FONT_MONO


class Theme:
    """当前主题（令牌容器），支持运行时切换 dark/light。"""

    def __init__(self, name: str = "dark"):
        self.name = name
        self.tokens = dict(DARK)

    def use(self, name: str):
        self.name = name
        self.tokens = dict(DARK if name == "dark" else LIGHT)

    def __getattr__(self, key):
        try:
            return self.tokens[key]
        except KeyError as e:
            raise AttributeError(f"未知设计令牌: {key}") from e


theme = Theme("dark")


def setup_ttk(root: tk.Tk | tk.Toplevel) -> None:
    """全局 ttk 样式（表格/按钮/标签页/复选框），云控制台风格。"""
    style = ttk.Style(root)
    try:
        style.theme_use("clam")
    except Exception:
        pass
    t = theme
    style.configure(".", font=FONT)
    # 表格：斑马纹由 tag 实现，这里统一行高与表头
    style.configure("Treeview", background=t.panel, foreground=t.fg,
                    fieldbackground=t.panel, rowheight=28, borderwidth=0)
    style.configure("Treeview.Heading", background=t.accent_soft, foreground=t.fg,
                    borderwidth=0, font=FONT_SMALL, padding=(8, 6))
    style.map("Treeview", background=[("selected", t.accent_soft)],
              foreground=[("selected", t.fg)])
    style.configure("TCheckbutton", background=t.bg, foreground=t.fg)
    style.configure("TNotebook", background=t.bg, borderwidth=0)
    style.configure("TNotebook.Tab", background=t.bg, foreground=t.muted,
                    padding=(16, 7), font=FONT)
    style.map("TNotebook.Tab",
              background=[("selected", t.panel)],
              foreground=[("selected", t.accent)])
    style.configure("TCombobox", fieldbackground=t.panel, background=t.panel,
                    foreground=t.fg, arrowcolor=t.muted, bordercolor=t.line)
    style.configure("TSpinbox", fieldbackground=t.panel, foreground=t.fg,
                    arrowcolor=t.muted, bordercolor=t.line)


def nav_style_configure() -> None:
    """侧栏按钮用的动态配色在页面内以 tk.Label 实现，这里只占位以保证可读性。"""
    return None
