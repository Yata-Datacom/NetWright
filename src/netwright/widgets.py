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

import math

import tkinter as tk
from tkinter import ttk

from .theme import FONT, FONT_BOLD, FONT_SMALL, theme


def _lerp(c1: str, c2: str, t: float) -> str:
    """两个 #rrggbb 颜色之间线性插值。"""
    r1, g1, b1 = int(c1[1:3], 16), int(c1[3:5], 16), int(c1[5:7], 16)
    r2, g2, b2 = int(c2[1:3], 16), int(c2[3:5], 16), int(c2[5:7], 16)
    return "#{:02x}{:02x}{:02x}".format(
        int(r1 + (r2 - r1) * t), int(g1 + (g2 - g1) * t), int(b1 + (b2 - b1) * t))


class GradientFrame(tk.Canvas):
    """渐变背景容器：横向/纵向线性渐变，随尺寸变化重绘。

    性能设计：
      * 按 4px 分块绘制（视觉无损，绘制对象数量减 75%）；
      * 尺寸未变化时跳过重绘；
      * <Configure> 高频触发时用 after(16ms) 合并为一次绘制（防抖）。
    """

    _STEP = 4  # 渐变分块像素

    def __init__(self, master, c1: str, c2: str, direction: str = "h", **kw):
        super().__init__(master, highlightthickness=0, bd=0, **kw)
        self._c1, self._c2, self._dir = c1, c2, direction
        self._last_size = (0, 0)
        self._pending = False
        self.bind("<Configure>", self._on_configure)

    def set_colors(self, c1: str, c2: str):
        self._c1, self._c2 = c1, c2
        self._last_size = (0, 0)  # 强制重绘
        self.repaint()

    def _on_configure(self, _event=None):
        if self._pending:
            return
        self._pending = True
        self.after(16, self._debounced_repaint)

    def _debounced_repaint(self):
        self._pending = False
        if not self.winfo_exists():
            return
        size = (self.winfo_width(), self.winfo_height())
        if size == self._last_size:
            return
        self.repaint()

    def repaint(self):
        if not self.winfo_exists():
            return
        w = max(self.winfo_width(), 1)
        h = max(self.winfo_height(), 1)
        self._last_size = (w, h)
        self.delete("all")
        n = h if self._dir == "v" else w
        step = self._STEP
        for i in range(0, n, step):
            color = _lerp(self._c1, self._c2, i / max(1, n - 1))
            if self._dir == "v":
                self.create_line(0, i, w, i + step, fill=color)
            else:
                self.create_line(i, 0, i + step, h, fill=color)


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


class WButton(tk.Button):
    """语义化按钮：按传入的语义色自动保证前景/背景对比度。

    规则：
      * bg 为 accent/ok/warn/err 等强色 → 白字、active 加深
      * 其余（panel/accent_soft/未指定）→ ghost 样式：panel 底 + 边框 + 正常字色
      * 明暗主题切换重建界面后自动跟随令牌
    """

    def __init__(self, master, **kw):
        bg = kw.pop("bg", None)
        fg = kw.pop("fg", None)
        ab = kw.pop("activebackground", None)
        af = kw.pop("activeforeground", None)
        deep = getattr(theme, "accent_deep", theme.accent)
        strong = {theme.accent: (deep, "#ffffff"),
                  deep: (deep, "#ffffff"),
                  theme.ok: (theme.ok, "#ffffff"),
                  theme.warn: (theme.warn, "#1c1200"),
                  theme.err: (theme.err, "#ffffff"),
                  theme.header1: (theme.header1, "#ffffff"),
                  theme.header2: (theme.header2, "#ffffff")}
        if bg in strong:
            use_bg, use_fg = strong[bg]
            kw["activebackground"] = ab or theme.accent_soft
            kw["activeforeground"] = af or use_fg
            kw["disabledforeground"] = "#ffffff"
        else:
            use_bg = theme.panel
            use_fg = fg or theme.fg
            kw["highlightbackground"] = theme.line
            kw["highlightthickness"] = 1
            kw["activebackground"] = ab or theme.accent_soft
            kw["activeforeground"] = af or theme.fg
        kw["bg"] = use_bg
        kw["fg"] = use_fg
        kw.setdefault("relief", tk.FLAT)
        kw.setdefault("cursor", "hand2")
        kw.setdefault("font", FONT)
        super().__init__(master, **kw)




# ══════════════════════════════════════════════════════════════════════
# 云控制台规范组件（Tag / Skeleton / Toast / Drawer / ScrollFrame）
# ══════════════════════════════════════════════════════════════════════

class Tag(tk.Label):
    """状态标签：soft 底 + 强色字 + 文字标签（不只靠颜色区分）。"""

    KINDS = {
        "ok": ("success_soft", "success", "✓ 正常"),
        "success": ("success_soft", "success", "✓ 成功"),
        "warn": ("warn_soft", "warn", "▲ 待复核"),
        "error": ("err_soft", "err", "✖ 失败"),
        "info": ("accent_soft", "accent", "ℹ 信息"),
        "new": ("warn_soft", "warn", "★ 新增"),
        "known": ("success_soft", "success", "✓ 已知"),
        "online": ("success_soft", "success", "● 在线"),
        "offline": ("neutral_soft", "muted", "○ 离线"),
    }

    def __init__(self, master, text: str = "", kind: str = "info", **kw):
        soft = getattr(theme, f"{self.KINDS.get(kind, ('accent_soft',))[0]}",
                       theme.accent_soft)
        strong = getattr(theme, self.KINDS.get(kind, ("", "accent"))[1], theme.accent)
        default_text = self.KINDS.get(kind, ("", "", text))[2]
        super().__init__(master, text=text or default_text, bg=soft, fg=strong,
                         padx=8, pady=2, font=FONT_SMALL, **kw)

    def set_kind(self, text: str, kind: str):
        soft = getattr(theme, f"{self.KINDS.get(kind, ('accent_soft',))[0]}",
                       theme.accent_soft)
        strong = getattr(theme, self.KINDS.get(kind, ("", "accent"))[1], theme.accent)
        self.config(text=text, bg=soft, fg=strong)


class Skeleton(tk.Frame):
    """加载骨架屏：若干灰色占位条，模拟内容块。"""

    def __init__(self, master, rows: int = 4, width: int = 0):
        super().__init__(master, bg=theme.panel)
        self._bars: list[tk.Frame] = []
        for i in range(rows):
            bar = tk.Frame(self, bg=theme.panel_alt, height=14)
            if width:
                bar.configure(width=width)
                bar.pack(anchor="w", padx=16, pady=8)
            else:
                bar.pack(anchor="w", padx=16, pady=8, fill=tk.X)
            self._bars.append(bar)

    @staticmethod
    def attach(parent, rows: int = 4) -> "Skeleton":
        sk = Skeleton(parent, rows=rows)
        sk.pack(fill=tk.X, padx=10, pady=10)
        return sk

    def destroy(self):  # noqa: D102
        super().destroy()


class Toast(tk.Toplevel):
    """应用内通知（右下角，自动消失）——替代成功/提示类 messagebox。"""

    KIND_BG = {"ok": "success", "err": "danger", "warn": "warn", "info": "accent"}
    KIND_ICON = {"ok": "✓", "err": "✖", "warn": "▲", "info": "ℹ"}

    def __init__(self, app, text: str, kind: str = "info", ms: int = 2600):
        super().__init__(app)
        self.overrideredirect(True)
        bg = getattr(theme, self.KIND_BG.get(kind, "accent"))
        fg = "#ffffff" if kind != "warn" else "#1c1200"
        tk.Label(self, text=f" {self.KIND_ICON.get(kind, '')} {text} ",
                 bg=bg, fg=fg, font=FONT, padx=16, pady=10).pack()
        self.update_idletasks()
        x = app.winfo_x() + app.winfo_width() - self.winfo_width() - 24
        y = app.winfo_y() + app.winfo_height() - self.winfo_height() - 44
        self.geometry(f"+{x}+{y}")
        self.after(ms, self.destroy)


def toast(app, text: str, kind: str = "info", ms: int = 2600) -> None:
    try:
        Toast(app, text, kind, ms)
    except tk.TclError:
        pass


class Drawer(tk.Toplevel):
    """右侧抽屉（480/560px）：编辑表单/详情首选容器。

    用法：Drawer(parent, title, width)；内容放 self.body；close() 关闭。
    """

    def __init__(self, parent, title: str, width: int = 480):
        super().__init__(parent)
        self.title(title)
        self.configure(bg=theme.panel)
        self.transient(parent)
        parent_x = parent.winfo_x()
        parent_w = parent.winfo_width()
        parent_h = parent.winfo_height()
        w = width if width in (480, 560) else 480
        h = max(480, int(parent_h * 0.92))
        x = parent_x + parent_w - w - 12
        y = parent.winfo_y() + 30
        self.geometry(f"{w}x{h}+{x}+{y}")
        self.body = tk.Frame(self, bg=theme.panel)
        self.body.pack(fill=tk.BOTH, expand=True, padx=16, pady=12)
        self.protocol("WM_DELETE_WINDOW", self.close)
        self.bind("<Escape>", lambda e: self.close())

    def close(self):
        self.destroy()


class ScrollFrame(tk.Frame):
    """纵向滚动容器：内容放 self.inner（业务控件包一层即可内部滚动）。"""

    def __init__(self, master, **kw):
        super().__init__(master, bg=theme.bg, **kw)
        self.canvas = tk.Canvas(self, bg=theme.bg, highlightthickness=0)
        self.vsb = ttk.Scrollbar(self, orient=tk.VERTICAL, command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=self.vsb.set)
        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.vsb.pack(side=tk.RIGHT, fill=tk.Y)
        self.inner = tk.Frame(self.canvas, bg=theme.bg)
        self._win = self.canvas.create_window((0, 0), window=self.inner, anchor="nw")
        self.inner.bind("<Configure>", self._on_inner)
        self.canvas.bind("<Configure>", self._on_canvas)

    def _on_inner(self, _e):
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def _on_canvas(self, e):
        self.canvas.itemconfigure(self._win, width=e.width)



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
_WALL_CACHE_MAX = 3      # resize 时只保留最近几个尺寸的壁纸


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
    while len(_wall_cache) > _WALL_CACHE_MAX:      # 防止 resize 时缓存无限膨胀
        _wall_cache.pop(next(iter(_wall_cache)))
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


def draw_line_chart(canvas: tk.Canvas, series: list[tuple[str, float]],
                    color: str | None = None, title: str = "",
                    empty_text: str = "暂无历史数据") -> None:
    """在 Canvas 上绘制简易折线趋势图（坐标轴/网格/末值标注，纯 Token 配色）。"""
    canvas.delete("all")
    fg, muted, line = theme.fg, theme.muted, theme.line
    color = color or theme.accent
    w = max(canvas.winfo_width(), 400)
    h = max(canvas.winfo_height(), 240)
    pad_l, pad_r, pad_t, pad_b = 48, 20, 34, 34
    if not series:
        canvas.create_text(w / 2, h / 2, text=empty_text, fill=muted, font=FONT_SMALL)
        return
    values = [v for _l, v in series]
    vmin, vmax = min(values), max(values)
    if vmax == vmin:
        vmax = vmin + 1
    span = vmax - vmin
    x0, y0, x1, y1 = pad_l, pad_t, w - pad_r, h - pad_b
    canvas.create_line(x0, y0 - 6, x0, y1, fill=line)
    canvas.create_line(x0, y1, x1 + 6, y1, fill=line)
    for frac in (0, 0.5, 1.0):
        gy = y0 + (y1 - y0) * frac
        canvas.create_line(x0, gy, x1, gy, fill=line, dash=(2, 3))
        canvas.create_text(x0 - 6, gy, text=f"{vmax - span * frac:.0f}",
                           fill=muted, font=FONT_SMALL, anchor="e")
    n = len(series)
    def px(i):
        return x0 + (x1 - x0) * (i / max(1, n - 1))

    def py(v):
        return y1 - (y1 - y0) * ((v - vmin) / span)
    pts = []
    for i, (_label, v) in enumerate(series):
        pts += [px(i), py(v)]
    if n > 1:
        canvas.create_line(pts, fill=color, width=2, smooth=True)
    for i, (_label, v) in enumerate(series):
        r = 3
        canvas.create_oval(px(i) - r, py(v) - r, px(i) + r, py(v) + r,
                           fill=color, outline="")
    _lx, lv = series[-1]
    canvas.create_text(px(n - 1), py(lv) - 12, text=f"{lv:.0f}", fill=color,
                       font=FONT_SMALL)
    stride = max(1, math.ceil(n / 8))
    for i, (label, _v) in enumerate(series):
        if i % stride == 0 or i == n - 1:
            canvas.create_text(px(i), y1 + 12, text=label, fill=muted,
                               font=FONT_SMALL, angle=-30)
    if title:
        canvas.create_text(w / 2, 12, text=title, fill=fg, font=FONT_BOLD)
