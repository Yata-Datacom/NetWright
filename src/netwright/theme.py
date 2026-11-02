"""theme.py — 全局设计令牌（DLUX / 云控制台规范）。

视觉基调（对齐 OpenDaylight DLUX 一类控制器控制台）：
  * 深色外壳（chrome）：顶栏 + 左侧一级导航，固定深藏青，明暗模式都保持深色；
  * 浅色内容区（canvas）：白卡片 + 细边框 + 8px 网格留白，让拓扑与表格当主角；
  * 主色只用于交互与状态，不做装饰性渐变。

规范要点：
  * 色彩集中于此，组件禁止硬编码色值；
  * 间距 8px 网格：4/8/12/16/24/32/48（SPACE 常量）；
  * 字阶（px→Tk pt 近似）：12px≈9pt / 14px≈10pt / 16px≈12pt / 20px≈14pt / 24px≈16pt；
  * 状态色语义绑定：success=稳定/完成，warning=降级/待复核，danger=阻断/失败；
  * 无渐变、无玻璃拟态、无装饰插图。

兼容层：保留 pages 既有令牌名（bg/panel/fg/muted/accent/nav1/nav2/header1…），
值映射到新规范，保证业务页面零改动即可换肤。
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
FONT_NAV = ("Microsoft YaHei UI", 10)
FONT_NAV_GROUP = ("Microsoft YaHei UI", 8)

# ── 布局度量（外壳骨架）───────────────────────────────────────────────
TOPBAR_H = 52        # 顶栏高度
SIDEBAR_W = 224      # 侧栏展开宽度
SIDEBAR_COLLAPSED_W = 64
CONTENT_PAD = 20     # 内容区外边距

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

# ── 深色外壳（两模式共用，暗模式再压暗一档）──────────────────────────
_CHROME = {
    "light": {"chrome": "#0E1B2A", "chrome_alt": "#132A40", "chrome_line": "#1E3A52",
              "chrome_fg": "#E8F1FA", "chrome_muted": "#8FA6BE"},
    "dark": {"chrome": "#080F18", "chrome_alt": "#0F1F30", "chrome_line": "#1B3145",
             "chrome_fg": "#E8F1FA", "chrome_muted": "#8299B1"},
}

# ── 明暗基底（内容区 Token）─────────────────────────────────────────
_MODE_BASE = {
    "light": {
        "bg": "#F5F7FA", "panel": "#FFFFFF", "panel_alt": "#F0F3F8",
        "line": "#E1E6EE",
        "fg": "#1B2430", "muted": "#5B6675", "faint": "#8A94A3",
        "accent": "#2570F2", "accent_soft": "#E8F0FE",
        "ok": "#0E9F6E", "warn": "#D97706", "err": "#DC2626", "info": "#0284C7",
        "success_soft": "#DCFCE7", "warn_soft": "#FEF3C7", "err_soft": "#FEE2E2",
        "neutral_soft": "#EDF0F5",
        "nav1": "#FFFFFF", "nav2": "#F5F7FA",
        "header1": "#FFFFFF", "header2": "#E1E6EE",
        "grad1": "#FFFFFF", "grad2": "#F5F7FA",
        "zebra": "#F7F9FC",
        "code_bg": "#0B1726",
        "topo_bg": "#FFFFFF", "topo_grid": "#EDF1F7",
    },
    "dark": {
        "bg": "#0F1216", "panel": "#171B21", "panel_alt": "#1C2129",
        "line": "#2A303A",
        "fg": "#E8EAED", "muted": "#9AA3AF", "faint": "#6B7280",
        "accent": "#5B8DEF", "accent_soft": "#1E3A5F",
        "ok": "#34D399", "warn": "#FBBF24", "err": "#F87171", "info": "#38BDF8",
        "success_soft": "#0F2E22", "warn_soft": "#3A2E10", "err_soft": "#3A1616",
        "neutral_soft": "#232833",
        "nav1": "#171B21", "nav2": "#0F1216",
        "header1": "#171B21", "header2": "#2A303A",
        "grad1": "#171B21", "grad2": "#0F1216",
        "zebra": "#1B2027",
        "code_bg": "#0a1526",
        "topo_bg": "#12161C", "topo_grid": "#1B212B",
    },
}


class Theme:
    """当前主题：明/暗 + 主色。页面通过 theme.xxx 动态读取。"""

    def __init__(self, mode: str = "light", hue: str = "蓝"):
        self.hue = hue
        self.tokens: dict[str, object] = {}
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
        t.update(_CHROME[mode])
        t.update({
            "mode": mode,
            "accent": hue_def[mode],
            "accent_soft": hue_def["soft"][mode],
            "accent_deep": hue_def["deep"][mode],
            "primary": hue_def[mode],
            # 外壳主色高亮（深色底上会更亮一点才够对比）
            "chrome_accent": hue_def["dark"],
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

    def toggle_mode(self) -> str:
        """明暗互换并返回新模式。"""
        self.use_mode("dark" if self.mode == "light" else "light", self.hue)
        return self.mode

    @property
    def mode(self) -> str:
        return self.tokens["mode"]  # type: ignore[return-value]

    def __getattr__(self, key):
        try:
            return self.tokens[key]
        except KeyError as e:
            raise AttributeError(f"未知设计令牌: {key}") from e


# 拓扑图厂商节点色板（数据可视化色，非 UI 装饰）
VENDOR_COLORS = {
    "huawei": "#E5534B", "h3c": "#3B82F6", "cisco": "#22C55E",
    "ruijie": "#F59E0B", "mikrotik": "#0EA5E9", "vyos": "#A855F7",
    "sonic": "#14B8A6", "linux": "#64748B", "generic": "#94A3B8",
    "huawei_ac": "#FB7185", "h3c_ac": "#60A5FA", "cisco_wlc": "#4ADE80",
}

theme = Theme("light", "蓝")


def setup_ttk(root: tk.Tk | tk.Toplevel) -> None:
    """全局 ttk 样式：表格行高 36、标签页、复选框、输入框（六态基础）。"""
    style = ttk.Style(root)
    try:
        style.theme_use("clam")
    except Exception:
        pass
    t = theme
    style.configure(".", font=FONT)
    style.configure("Treeview", background=t.panel, foreground=t.fg,
                    fieldbackground=t.panel, rowheight=36, borderwidth=0)
    style.configure("Treeview.Heading", background=t.panel_alt, foreground=t.muted,
                    borderwidth=0, font=FONT_SMALL, padding=(10, 8))
    style.map("Treeview.Heading", background=[("active", t.panel_alt)])
    style.map("Treeview", background=[("selected", t.accent_soft)],
              foreground=[("selected", t.fg)])
    style.configure("TCheckbutton", background=t.bg, foreground=t.fg)
    style.map("TCheckbutton",
              background=[("active", t.bg)], foreground=[("active", t.accent)])
    style.configure("TNotebook", background=t.bg, borderwidth=0)
    style.configure("TNotebook.Tab", background=t.bg, foreground=t.muted,
                    padding=(14, 7), font=FONT)
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
    style.configure("TSeparator", background=t.line)
    # 卡片内滚动条：细、无箭头感
    style.configure("Vertical.TScrollbar", background=t.panel_alt, troughcolor=t.bg,
                    bordercolor=t.bg, arrowcolor=t.muted, width=10)
