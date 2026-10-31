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
from netforge.widgets import GradientFrame  # noqa: E402


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

        self._build_chrome()
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

        # 主体：渐变侧栏 + 工作区
        main = tk.Frame(self, bg=theme.bg)
        main.pack(fill=tk.BOTH, expand=True)
        self.rail = GradientFrame(main, theme.nav1, theme.nav2, "v", width=172)
        self.rail.pack(side=tk.LEFT, fill=tk.Y)
        self.rail.pack_propagate(False)
        self._build_nav(self.rail)

        self.container = tk.Frame(main, bg=theme.bg)
        self.container.pack(fill=tk.BOTH, expand=True)
        self.pages = {key: cls(self.container, self)
                      for key, (_n, _i, cls) in PAGE_REGISTRY.items()}

    # ── 侧栏导航（hover 反馈 + 选中强调）───────────────────────────
    def _build_nav(self, rail: tk.Frame):
        tk.Label(rail, text="  工作区", bg=theme.nav1, fg=theme.muted,
                 font=FONT_SMALL, anchor="w").pack(fill=tk.X, pady=(10, 2))
        self._nav_buttons: dict[str, tk.Label] = {}
        self._active_key = "dashboard"
        for key, (name, icon, _cls) in PAGE_REGISTRY.items():
            btn = tk.Label(rail, text=f"  {icon}  {name}", bg=theme.nav1, fg=theme.muted,
                           font=("Microsoft YaHei UI", 11), anchor="w", pady=9,
                           cursor="hand2")
            btn.pack(fill=tk.X)
            btn.bind("<Button-1>", lambda e, k=key: self.show(k))
            btn.bind("<Enter>", lambda e, b=btn: b.config(fg="white")
                     if self._active_key != b.nav_key else None)
            btn.bind("<Leave>", lambda e, b=btn: b.config(fg=theme.muted)
                     if self._active_key != b.nav_key else None)
            btn.nav_key = key
            self._nav_buttons[key] = btn
        tk.Frame(rail, bg=theme.line, height=1).pack(fill=tk.X, padx=10, pady=8)
        tk.Label(rail, text=f"v{__version__}", bg=theme.nav2, fg=theme.muted,
                 font=FONT_SMALL).pack(side=tk.BOTTOM, pady=10)

    def _highlight_nav(self, key: str):
        self._active_key = key
        for k, btn in self._nav_buttons.items():
            active = k == key
            btn.config(bg=theme.accent if active else theme.nav1,
                       fg="white" if active else theme.muted,
                       font=("Microsoft YaHei UI", 11, "bold" if active else "normal"))

    # ── 主题切换（重建 chrome + 页面）─────────────────────────────
    def apply_theme(self, name: str):
        theme.use(name)
        self.settings["theme"] = name
        save_settings(self.settings, BASE_DIR)
        # 销毁旧界面
        for page in self.pages.values():
            page.destroy()
        self.top.destroy()
        self.rail.destroy()
        self.container.destroy()
        setup_ttk(self)
        self.configure(bg=theme.bg)
        self._build_chrome()
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
        self._highlight_nav(key)
        hooks = {"dashboard": "refresh", "inventory": "refresh",
                 "inspect": "refresh_devices"}
        hook = hooks.get(key)
        if hook and hasattr(self.pages[key], hook):
            getattr(self.pages[key], hook)()
        self.settings["last_page"] = key
        save_settings(self.settings, BASE_DIR)
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
        save_settings(self.settings, BASE_DIR)
        self.destroy()


def main() -> None:
    app = NetForgeApp()
    app.mainloop()


if __name__ == "__main__":
    main()
