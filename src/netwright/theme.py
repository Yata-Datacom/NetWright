"""theme.py — 设计令牌与配色方案注册表（明/暗 × 多配色，支持运行时切换）。

视觉语言参考云计算厂商控制台：
  * 中性画布 + 卡片 + 细边框 + 克制的品牌色
  * 状态色语义化（ok/warn/err/info），只用于状态，不做装饰
  * 渐变：顶栏（品牌横向渐变）、侧栏（导航纵向渐变）、页头带（accent 渐变）

页面代码一律通过 ``theme.xxx`` 动态访问令牌；切换配色后由应用重建工作区即可生效。
"""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk

# ── 字体（静态）──────────────────────────────────────────────────────
FONT = ("Microsoft YaHei UI", 10)
FONT_BOLD = ("Microsoft YaHei UI", 10, "bold")
FONT_H1 = ("Microsoft YaHei UI", 15, "bold")
FONT_H2 = ("Microsoft YaHei UI", 11, "bold")
FONT_SMALL = ("Microsoft YaHei UI", 9)
FONT_MONO = ("Consolas", 10)
FONT_MONO_SMALL = ("Consolas", 9)


def _t(mode: str, accent: str, accent_soft: str, nav: tuple, header: tuple,
       grad: tuple) -> dict:
    """生成一套完整令牌：mode 决定明暗基底，其余为配色个性。"""
    base = {
        "dark": {
            "bg": "#0d1420", "panel": "#111b2e", "panel_alt": "#0a1120",
            "line": "#22314c", "fg": "#e8eef8", "muted": "#8ba0c0",
            "faint": "#5b6c8c", "accent_soft": "#16294a",
            "ok": "#22c55e", "warn": "#f59e0b", "err": "#ef4444", "info": "#38bdf8",
            "zebra": "#0f1a2c",
        },
        "light": {
            "bg": "#f2f5fa", "panel": "#ffffff", "panel_alt": "#f7f9fc",
            "line": "#d9e1ec", "fg": "#17233d", "muted": "#5b6b84",
            "faint": "#94a3b8", "accent_soft": "#e8f0ff",
            "ok": "#16a34a", "warn": "#d97706", "err": "#dc2626", "info": "#0284c7",
            "zebra": "#f7f9fc",
        },
    }[mode]
    tokens = dict(base)
    tokens.update({
        "mode": mode, "accent": accent, "accent_soft": accent_soft,
        "nav1": nav[0], "nav2": nav[1],
        "header1": header[0], "header2": header[1],
        "grad1": grad[0], "grad2": grad[1],
    })
    return tokens


# ── 配色方案注册表（清新系：亮色为主，低饱和、高留白）────────────────
THEMES: dict[str, dict] = {
    "薄荷清晨 · 亮": _t("light", "#10b981", "#d1fae5",
                        ("#0f3d33", "#0a2c25"), ("#10b981", "#0d9488"),
                        ("#f4faf7", "#e6f4ee")),
    "晴空 · 亮": _t("light", "#0ea5e9", "#e0f2fe",
                    ("#0c4a6e", "#093650"), ("#0ea5e9", "#0284c7"),
                    ("#f2f9fd", "#e6f1f8")),
    "樱粉 · 亮": _t("light", "#ec4899", "#fce7f3",
                    ("#4a1d33", "#371425"), ("#ec4899", "#db2777"),
                    ("#fdf4f7", "#f7e8ee")),
    "蜜橙 · 亮": _t("light", "#f97316", "#ffedd5",
                    ("#4a2410", "#38190a"), ("#f97316", "#ea580c"),
                    ("#fbf6f2", "#f4ece4")),
    "深空蓝 · 暗": _t("dark", "#38bdf8", "#16294a",
                      ("#0b1f3a", "#081527"), ("#1a66ff", "#0e4fce"),
                      ("#101b30", "#0b1220")),
    "曜石 · 暗": _t("dark", "#38bdf8", "#1f2937",
                    ("#18181b", "#101012"), ("#3f3f46", "#27272a"),
                    ("#141417", "#0c0c0e")),
}

DEFAULT_THEME = "薄荷清晨 · 亮"


class Theme:
    """当前主题（令牌容器 + 动态访问点）。"""

    def __init__(self, name: str = DEFAULT_THEME):
        self.name = name
        self.tokens = dict(THEMES[name])

    def use(self, name: str):
        if name not in THEMES:
            raise ValueError(f"未知配色方案: {name}")
        self.name = name
        self.tokens = dict(THEMES[name])

    @property
    def mode(self) -> str:
        return self.tokens["mode"]

    def __getattr__(self, key):
        try:
            return self.tokens[key]
        except KeyError as e:
            raise AttributeError(f"未知设计令牌: {key}") from e


theme = Theme(DEFAULT_THEME)


def setup_ttk(root: tk.Tk | tk.Toplevel) -> None:
    """全局 ttk 样式（表格/按钮/标签页/复选框），云控制台风格。"""
    style = ttk.Style(root)
    try:
        style.theme_use("clam")
    except Exception:
        pass
    t = theme
    style.configure(".", font=FONT)
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
