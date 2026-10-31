"""widgets.py — 可复用 UI 组件库（云控制台风格，渐变为主视觉）。

  page_header  页面标题区（标题 + 说明 + 品牌强调线 + 右侧动作槽）
  Card         白色卡片容器（统一边框/圆角感/内边距）
  StatCard     总览统计卡（大数字 + 标签 + 打开按钮，顶部强调条）
  PillLabel    状态徽章（语义色：ok/warn/err/info）
  make_table   标准数据表（表头/列宽/斑马纹一次配好）
  EmptyState   空状态占位
"""
from __future__ import annotations

import os

import tkinter as tk
from tkinter import ttk

from .theme import FONT_BOLD, FONT_SMALL, theme


def _lerp(c1: str, c2: str, t: float) -> str:
    """两个 #rrggbb 颜色之间线性插值。"""
    r1, g1, b1 = int(c1[1:3], 16), int(c1[3:5], 16), int(c1[5:7], 16)
    r2, g2, b2 = int(c2[1:3], 16), int(c2[3:5], 16), int(c2[5:7], 16)
    return "#{:02x}{:02x}{:02x}".format(
        int(r1 + (r2 - r1) * t), int(g1 + (g2 - g1) * t), int(b1 + (b2 - b1) * t))


class GradientFrame(tk.Canvas):
    """渐变背景容器：横向/纵向线性渐变，随尺寸变化重绘。

    用途：顶栏品牌渐变、侧栏导航渐变、每页页头带、卡片强调条。
    """

    def __init__(self, master, c1: str, c2: str, direction: str = "h", **kw):
        super().__init__(master, highlightthickness=0, bd=0, **kw)
        self._c1, self._c2, self._dir = c1, c2, direction
        self.bind("<Configure>", lambda e: self.repaint())

    def set_colors(self, c1: str, c2: str):
        self._c1, self._c2 = c1, c2
        self.repaint()

    def repaint(self):
        self.delete("all")
        w = max(self.winfo_width(), 1)
        h = max(self.winfo_height(), 1)
        n = h if self._dir == "v" else w
        for i in range(n):
            color = _lerp(self._c1, self._c2, i / max(1, n - 1))
            if self._dir == "v":
                self.create_line(0, i, w, i, fill=color)
            else:
                self.create_line(i, 0, i, h, fill=color)


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
    """页面标题区：品牌渐变带（accent 横向渐变）+ 白字标题/说明。"""
    bar = GradientFrame(parent, theme.header1, theme.header2, direction="h", height=64)
    bar.pack(fill=tk.X)
    bar.pack_propagate(False)
    tk.Label(bar, text=title, bg=theme.header1, fg="#ffffff",
             font=("Microsoft YaHei UI", 15, "bold")).pack(anchor="w", padx=20, pady=(10, 0))
    tk.Label(bar, text=desc, bg=theme.header1, fg="#dbe7ff",
             font=FONT_SMALL).pack(anchor="w", padx=20, pady=(2, 10))


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


StatCard = stat_card  # 类名别名（历史接口）


_wall_cache: dict[tuple, "tk.PhotoImage"] = {}


def draw_wallpaper(path: str, w: int, h: int):
    """把用户图片裁剪铺满 (w,h) 并转 PhotoImage；PIL 缺失/文件无效返回 None。

    结果按 (路径, 宽, 高) 缓存，避免窗口拖动时反复缩放。
    """
    if not path or w < 10 or h < 10:
        return None
    try:
        from PIL import Image, ImageOps, ImageTk
    except ImportError:
        return None
    if not os.path.isfile(path):
        return None
    key = (os.path.abspath(path), w, h)
    if key in _wall_cache:
        return _wall_cache[key]
    try:
        with Image.open(path) as im:
            im = ImageOps.exif_transpose(im).convert("RGB")
            fitted = ImageOps.fit(im, (w, h))
            photo = ImageTk.PhotoImage(fitted)
    except Exception:
        return None
    _wall_cache[key] = photo
    return photo


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
