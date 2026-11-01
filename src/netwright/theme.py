"""theme.py — 全局设计令牌（云控制台规范）+ 明/暗主题 + 主色可选。

规范要点：
  * 色彩集中于此，组件禁止硬编码色值；
  * 间距 8px 网格：4/8/12/16/24/32/48（space 常量）；
  * 字阶（px→Tk pt 近似）：12px≈9pt / 14px≈10pt / 16px≈12pt / 20px≈14pt / 24px≈16pt；
  * 状态色语义绑定：success=稳定/完成，warning=降级/待复核，danger=阻断/失败；
  * 无渐变、无玻璃拟态、无装饰插图。

兼容层：保留 pages 既有令牌名（bg/panel/fg/muted/accent/nav1/nav2/header1…），
值映射到新规范，保证逐页换肤前业务页面零改动。
"""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk

# ── 字阶（Tk pt）──────────────────────────────────────────────────────
FONT_XS = ("Microsoft YaHei UI", 9)       # 12px 辅助
FONT_SMALL = ("Microsoft YaHei UI", 9)    # 12px
FONT = ("Microsoft YaHei UI", 10)         # 14px 正文
FONT_BODY = ("Microsoft YaHei UI", 10)
FONT_MEDIUM = ("Microsoft YaHei UI", 10)
FONT_BOLD = ("Microsoft YaHei UI", 10, "bold")
FONT_H3 = ("Microsoft YaHei UI", 12)      # 16px
FONT_H2 = ("Microsoft YaHei UI", 14)      # 20px
FONT_H1 = ("Microsoft YaHei UI", 16)      # 24px
FONT_XL = ("Microsoft YaHei UI", 18)      # 32px 级
FONT_MONO = ("Consolas", 10)
FONT_MONO_SMALL = ("Consolas", 9)

# ── 间距（8px 网格）──────────────────────────────────────────────────
SPACE = {"xs": 4, "sm": 8, "md": 12, "lg": 16, "xl": 24, "xxl": 32, "xxxl": 48}

# ── 圆角/阴影 ────────────────────────────────────────────────────────
RADIUS = 6
SHADOW_SM = "0 1px 2px rgba(0,0,0,.06)"   # Tk 无法渲染，文档化令牌

# ── 主色可选（hue）───────────────────────────────────────────────────
PRIMARY_HUES = {
    "蓝": {"light": "#2570F2", "dark": "#5B8DEF",
           "deep": {"light": "#1A54C7", "dark": "#2563EB"},
           "soft": {"light": "#E8F0FE", "dark": "#1E3A5F"}},
    "绿": {"light": "#10B981", "dark": "#34D399",
           "deep": {"light": "#0B815A", "dark": "#0E9F6E"},
           "soft": {"light": "#D1FAE5", "dark": "#0F2E22"}},
    "紫": {"light": "#7C3AED", "dark": "#A78BFA",
           "deep": {"light": "#6025D0", "dark": "#7C5CE0"},
           "soft": {"light": "#EDE9FE", "dark": "#251A3F"}},
    "橙": {"light": "#EA580C", "dark": "#FB923C",
           "deep": {"light": "#C2410C", "dark": "#D96A1E"},
           "soft": {"light": "#FFEDD5", "dark": "#3A2415"}},
}

# ── 明暗基底（规范默认 Token）───────────────────────────────────────
_MODE_BASE = {
    "light": {
        "bg": "#F5F7FA", "panel": "#FFFFFF", "panel_alt": "#F7F9FC",
        "line": "#DEE0E3",
        "fg": "#1F2329", "muted": "#646A73", "faint": "#8F959E",
        "accent": "#2570F2", "accent_soft": "#E8F0FE",
        "ok": "#10B981", "warn": "#F59E0B", "err": "#EF4444", "info": "#0284C7",
        "success_soft": "#D1FAE5", "warn_soft": "#FEF3C7", "err_soft": "#FEE2E2",
        "neutral_soft": "#E5E7EB",
        "nav1": "#FFFFFF", "nav2": "#F5F7FA",
        "header1": "#FFFFFF", "header2": "#DEE0E3",
        "grad1": "#FFFFFF", "grad2": "#F5F7FA",
        "zebra": "#F7F9FC",
        "code_bg": "#0a1526",
    },
    "dark": {
        "bg": "#14161A", "panel": "#1C1F26", "panel_alt": "#17191F",
        "line": "#2A2E37",
        "fg": "#E8EAED", "muted": "#9AA0A6", "faint": "#6B7280",
        "accent": "#5B8DEF", "accent_soft": "#1E3A5F",
        "ok": "#34D399", "warn": "#FBBF24", "err": "#F87171", "info": "#38BDF8",
        "success_soft": "#0F2E22", "warn_soft": "#3A2E10", "err_soft": "#3A1616",
        "neutral_soft": "#26292F",
        "nav1": "#1C1F26", "nav2": "#17191F",
        "header1": "#1C1F26", "header2": "#2A2E37",
        "grad1": "#1C1F26", "grad2": "#14161A",
        "zebra": "#17191F",
        "code_bg": "#0a1526",
    },
}


class Theme:
    """当前主题：明/暗 + 主色。页面通过 theme.xxx 动态读取。"""

    def __init__(self, mode: str = "light", hue: str = "蓝"):
        self.hue = hue
        self.tokens = {}
        self.use_mode(mode, hue)

    def use_mode(self, mode: str, hue: str | None = None):
        if mode not in _MODE_BASE:
            raise ValueError(f"未知模式: {mode}")
        if hue is not None:
            self.hue = hue
        if self.hue not in PRIMARY_HUES:
            self.hue = "蓝"
        hue_def = PRIMARY_HUES[self.hue]
        t = dict(_MODE_BASE[mode])
        t.update({
            "mode": mode,
            "accent": hue_def[mode],
            "accent_soft": hue_def["soft"][mode],
            "accent_deep": hue_def["deep"][mode],
            "primary": hue_def[mode],
            # 兼容旧令牌名
            "header1": t["panel"], "header2": t["line"],
            "nav1": t["panel"], "nav2": t["bg"],
            "grad1": t["panel"], "grad2": t["bg"],
            "success": t["ok"], "warning": t["warn"], "danger": t["err"],
            "border": t["line"], "surface": t["panel"],
            "text_secondary": t["muted"],
            "zebra": t["panel_alt"],
        })
        self.tokens = t

    def use(self, name: str):
        """兼容旧接口：name 含 浅/亮 = light，否则 dark。"""
        self.use_mode("light" if ("浅" in name or "亮" in name or name == "light") else "dark")

    @property
    def mode(self) -> str:
        return self.tokens["mode"]

    def __getattr__(self, key):
        try:
            return self.tokens[key]
        except KeyError as e:
            raise AttributeError(f"未知设计令牌: {key}") from e


# 拓扑图厂商节点色板（数据可视化色，非 UI 装饰）
VENDOR_COLORS = {
    "huawei": "#e74c3c", "h3c": "#3498db", "cisco": "#2ecc71",
    "ruijie": "#f39c12", "mikrotik": "#2980b9", "vyos": "#9b59b6",
    "sonic": "#1abc9c", "linux": "#7f8c8d",
}

theme = Theme("light", "蓝")


def setup_ttk(root: tk.Tk | tk.Toplevel) -> None:
    """全局 ttk 样式：表格行高 40、标签页、复选框、输入框（六态基础）。"""
    style = ttk.Style(root)
    try:
        style.theme_use("clam")
    except Exception:
        pass
    t = theme
    style.configure(".", font=FONT)
    style.configure("Treeview", background=t.panel, foreground=t.fg,
                    fieldbackground=t.panel, rowheight=40, borderwidth=0)
    style.configure("Treeview.Heading", background=t.panel_alt, foreground=t.muted,
                    borderwidth=0, font=FONT_SMALL, padding=(8, 8))
    style.map("Treeview", background=[("selected", t.accent_soft)],
              foreground=[("selected", t.fg)])
    style.configure("TCheckbutton", background=t.bg, foreground=t.fg)
    style.map("TCheckbutton",
              background=[("active", t.bg)], foreground=[("active", t.accent)])
    style.configure("TNotebook", background=t.bg, borderwidth=0)
    style.configure("TNotebook.Tab", background=t.bg, foreground=t.muted,
                    padding=(12, 6), font=FONT)
    style.map("TNotebook.Tab",
              background=[("selected", t.panel)],
              foreground=[("selected", t.accent)])
    style.configure("TCombobox", fieldbackground=t.panel, background=t.panel,
                    foreground=t.fg, arrowcolor=t.muted, bordercolor=t.line,
                    lightcolor=t.panel, darkcolor=t.panel)
    style.map("TCombobox",
              bordercolor=[("focus", t.accent)],
              lightcolor=[("focus", t.accent)],
              fieldbackground=[("readonly", t.panel)])
    style.configure("TSpinbox", fieldbackground=t.panel, foreground=t.fg,
                    arrowcolor=t.muted, bordercolor=t.line)
    style.configure("TProgressbar", background=t.accent, troughcolor=t.panel_alt,
                    bordercolor=t.bg, lightcolor=t.accent, darkcolor=t.accent)

