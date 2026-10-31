"""
NetForge — 网络工程师工作台（应用壳）
=====================================

职责仅四件事：导航壳 / 主题系统（6 套配色，明暗 + 渐变）/ 页面装配 / 设置持久化。
业务逻辑全部在 ``netforge.lib``（纯逻辑）与 ``netforge.pages``（工作区页面）。

工作区（由 pages.PAGE_REGISTRY 驱动）：
  总览 / 设备清单 / 控制器 / 批量巡检 / 配置生成 / 工具箱 / 命令速查
"""
from __future__ import annotations

import os
import sys
import tkinter as tk
from datetime import datetime

if getattr(sys, "frozen", False):
    BASE_DIR = os.path.dirname(os.path.abspath(sys.executable))
else:
    BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    _SRC = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if _SRC not in sys.path:
        sys.path.insert(0, _SRC)

from netforge import __version__  # noqa: E402
from netforge.lib.controller.restapi import ControllerAPI, ControllerState  # noqa: E402
from netforge.lib.inventory import Inventory  # noqa: E402
from netforge.lib.settings import load_settings, save_settings  # noqa: E402
from netforge.pages import PAGE_REGISTRY  # noqa: E402
from netforge.theme import (  # noqa: E402
    FONT_SMALL, THEMES, setup_ttk, theme,
)
from netforge.widgets import GradientFrame, _lerp, draw_wallpaper  # noqa: E402


class NetForgeApp(tk.Tk):
    """主窗口：渐变顶栏 + 渐变侧栏导航 + 工作区容器 + 主题系统。"""

    def __init__(self):
        super().__init__()
        self.title(f"NetForge — 网络工程师工作台 v{__version__}")
        self.geometry("1120x760")
        self.minsize(1000, 660)

        # ── 设置（含主题记忆）──
        self.settings = load_settings(BASE_DIR)
        theme.use(self.settings.get("theme", theme.name))
        self.configure(bg=theme.bg)
        self.option_add("*Font", ("Microsoft YaHei UI", 10))
        setup_ttk(self)
        ico = os.path.join(BASE_DIR, "assets", "icon.ico")
        if os.path.isfile(ico):
            try:
                self.iconbitmap(ico)
            except Exception:
                pass

        # ── 共享状态 ──
        self.inventory = Inventory()
        self.controller_state = ControllerState(self.inventory)
        self.controller_api = ControllerAPI(self.controller_state,
                                            port=int(self.settings.get("rest_port", 8899)))
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        self._active_key = "dashboard"
        self._build_chrome()
        self._build_main()
        self._apply_wallpaper()
        self.show(self.settings.get("last_page", "dashboard"))

    # ── 界面装配（主题切换时整体重建）───────────────────────────────
    def _build_chrome(self):
        # 顶栏：品牌横向渐变
        self.top = GradientFrame(self, theme.header1, theme.header2, "h", height=58)
        self.top.pack(fill=tk.X)
        self.top.pack_propagate(False)
        tk.Label(self.top, text="⛏", bg=theme.header1, fg="white",
                 font=("", 16)).pack(side=tk.LEFT, padx=(16, 8))
        tk.Label(self.top, text="NetForge", bg=theme.header1, fg="white",
                 font=("", 14, "bold")).pack(side=tk.LEFT)
        tk.Label(self.top, text="网络工程师工作台", bg=theme.header1,
                 fg="#d7e2f5", font=FONT_SMALL).pack(side=tk.LEFT, padx=(10, 0))

        self.var_status = tk.StringVar(value="就绪")
        self.var_clock = tk.StringVar(value="")
        tk.Label(self.top, textvariable=self.var_clock, bg=theme.header1,
                 fg="#c9d6ee", font=FONT_SMALL).pack(side=tk.RIGHT, padx=14)
        tk.Label(self.top, textvariable=self.var_status, bg=theme.header1,
                 fg="white", font=FONT_SMALL).pack(side=tk.RIGHT, padx=14)

        # 主题选择：🎨 菜单（明暗 × 6 配色）
        self.mb_theme = tk.Menubutton(self.top, text="🎨 配色", bg=theme.header1,
                                      fg="white", relief=tk.FLAT, font=FONT_SMALL,
                                      activebackground=theme.header2, cursor="hand2")
        menu = tk.Menu(self.mb_theme, tearoff=0, font=FONT_SMALL)
        for name in THEMES:
            menu.add_command(label=name,
                             command=lambda n=name: self.apply_theme(n))
        menu.add_separator()
        menu.add_command(label=f"✓ 当前：{theme.name}", state=tk.DISABLED)
        self.mb_theme["menu"] = menu
        self.mb_theme.pack(side=tk.RIGHT, padx=(0, 12))

        self.mb_wall = tk.Menubutton(self.top, text="🖼 壁纸", bg=theme.header1,
                                     fg="white", relief=tk.FLAT, font=FONT_SMALL,
                                     activebackground=theme.header2, cursor="hand2")
        wall_menu = tk.Menu(self.mb_wall, tearoff=0, font=FONT_SMALL)
        wall_menu.add_command(label="上传壁纸…", command=self.upload_wallpaper)
        wall_menu.add_command(label="清除壁纸（恢复渐变）", command=lambda: self.set_wallpaper(None))
        self.mb_wall["menu"] = wall_menu
        self.mb_wall.pack(side=tk.RIGHT, padx=(0, 8))

    def upload_wallpaper(self):
        from tkinter import filedialog
        path = filedialog.askopenfilename(
            title="选择壁纸图片",
            filetypes=[("图片", "*.png *.jpg *.jpeg *.bmp *.webp"), ("全部", "*.*")])
        if path:
            self.set_wallpaper(path)

    def _build_main(self):
        """侧栏（渐变/壁纸自绘）+ 工作区容器 + 页面装配。"""
        main = tk.Frame(self, bg=theme.bg)
        main.pack(fill=tk.BOTH, expand=True)
        self.rail = tk.Canvas(main, width=172, highlightthickness=0, bd=0,
                              bg=theme.nav1)
        self.rail.pack(side=tk.LEFT, fill=tk.Y)
        self.container = tk.Frame(main, bg=theme.bg)
        self.container.pack(fill=tk.BOTH, expand=True)
        self.pages = {key: cls(self.container, self)
                      for key, (_n, _i, cls) in PAGE_REGISTRY.items()}
        self._build_nav(self.rail)
        self._apply_wallpaper()

    # ── 侧栏导航（Canvas 自绘：渐变/壁纸背景 + hover/选中）──────────
    def _build_nav(self, rail: tk.Canvas):
        self._nav_rects: dict[str, int] = {}
        self._nav_texts: dict[str, int] = {}
        rail.bind("<Configure>", lambda e: self._repaint_nav(full=True))
        rail.bind("<Motion>", self._nav_hover)
        rail.bind("<Leave>", lambda e: self._repaint_nav())
        rail.bind("<Button-1>", self._nav_click)
        self._repaint_nav()

    def _repaint_nav(self, full: bool = False):
        """重绘侧栏。背景只在尺寸变化或强制时重绘；条目/高亮每次重画（轻量）。"""
        rail = self.rail
        if not rail.winfo_exists():
            return
        w = max(rail.winfo_width(), 172)
        h = max(rail.winfo_height(), 600)
        size = (w, h)
        wp = self.settings.get("wallpaper") if hasattr(self, "settings") else ""
        if full or size != getattr(self, "_nav_bg_size", None) or                 wp != getattr(self, "_nav_bg_wp", None):
            rail.delete("bg")
            img = draw_wallpaper(wp, w, h) if wp else None
            if img is not None:
                rail.create_image(0, 0, image=img, anchor="nw", tags="bg")
                self._nav_wall_ref = img
            else:
                step = 4
                for y in range(0, h, step):
                    rail.create_line(0, y, w, y + step,
                                     fill=_lerp(theme.nav1, theme.nav2, y / max(1, h - 1)),
                                     tags="bg")
            self._nav_bg_size = size
            self._nav_bg_wp = wp
        rail.delete("items")
        y = 12
        rail.create_text(14, y, text="工 作 区", anchor="w", fill=theme.muted,
                         font=FONT_SMALL, tags="items")
        y += 34
        for key, (name, icon, _cls) in PAGE_REGISTRY.items():
            active = key == getattr(self, "_active_key", "")
            hover = key == getattr(self, "_hover_key", "")
            if active:
                rail.create_rectangle(8, y - 4, w - 8, y + 30,
                                      fill=theme.accent, outline="", width=0,
                                      tags="items")
            elif hover:
                rail.create_rectangle(8, y - 4, w - 8, y + 30,
                                      fill=_lerp(theme.nav1, "#ffffff", 0.10),
                                      outline="", width=0, tags="items")
            fg = "#ffffff" if active or hover else theme.muted
            rail.create_text(18, y + 12, text=f"{icon}  {name}", anchor="w",
                             fill=fg,
                             font=("Microsoft YaHei UI", 11,
                                   "bold" if active else "normal"),
                             tags=("items", f"nav:{key}"))
            self._nav_rects[key] = y
            y += 38
        rail.create_text(w / 2, h - 22, text=f"v{__version__}", fill=theme.muted,
                         font=FONT_SMALL, tags="items")
        rail.tag_lower("bg")

    def _nav_hit(self, y: int) -> str | None:
        for key, top in self._nav_rects.items():
            if top - 6 <= y <= top + 32:
                return key
        return None

    def _nav_hover(self, e):
        key = self._nav_hit(e.y)
        if key != getattr(self, "_hover_key", None):
            self._hover_key = key
            self._repaint_nav()          # 仅重绘条目层，背景保留

    def _nav_click(self, e):
        key = self._nav_hit(e.y)
        if key:
            self.show(key)

    def _apply_wallpaper(self):
        """侧栏应用壁纸（若有）；随窗口尺寸重绘。"""
        self.rail.bind("<Configure>", lambda e: self._repaint_nav())
        self._repaint_nav()

    def set_wallpaper(self, path: str | None):
        """上传/清除壁纸（持久化到设置）。"""
        self.settings["wallpaper"] = path or ""
        save_settings(self.settings, BASE_DIR)
        self._apply_wallpaper()
        self.set_status("壁纸已设置" if path else "壁纸已清除（恢复渐变）")

    # ── 主题切换（先建后销，避免悬挂引用）─────────────────────────
    def _highlight_nav(self, key: str):
        self._active_key = key
        self._repaint_nav()

    def apply_theme(self, name: str):
        theme.use(name)
        self.settings["theme"] = name
        save_settings(self.settings, BASE_DIR)
        setup_ttk(self)
        self.configure(bg=theme.bg)

        old_pages, old_top, old_rail, old_container = (
            self.pages, self.top, self.rail, self.container)
        # 先建新界面
        self._active_key = "dashboard"
        self._build_chrome()
        self._build_main()
        self._highlight_nav(self._active_key)
        # 再销毁旧界面
        for page in old_pages.values():
            page.destroy()
        old_top.destroy()
        old_rail.destroy()
        old_container.destroy()
        self.show(self._active_key)
        self.set_status(f"配色已切换：{name}")

    # ── 工作区切换 ─────────────────────────────────────────────────
    def show(self, key: str):
        if key not in self.pages:
            return
        for k, page in self.pages.items():
            if k == key:
                page.place(relx=0, rely=0, relwidth=1, relheight=1)
            else:
                page.place_forget()
        self._repaint_nav()
        hooks = {"dashboard": "refresh", "inventory": "refresh",
                 "inspect": "refresh_devices"}
        hook = hooks.get(key)
        if hook and hasattr(self.pages[key], hook):
            getattr(self.pages[key], hook)()
        self.set_status("就绪")

    # ── 状态 ───────────────────────────────────────────────────────
    def refresh_dashboard(self):
        self.pages["dashboard"].refresh()

    def set_status(self, text: str):
        self.var_status.set(text)

    def _tick_clock(self):
        self.var_clock.set(datetime.now().strftime("%Y-%m-%d %H:%M"))
        self.after(30_000, self._tick_clock)

    def _on_close(self):
        try:
            self.controller_api.stop()
        except Exception:
            pass
        self.settings["last_page"] = getattr(self, "_active_key", "dashboard")
        save_settings(self.settings, BASE_DIR)
        self.destroy()


def main() -> None:
    app = NetForgeApp()
    app.mainloop()


if __name__ == "__main__":
    main()
