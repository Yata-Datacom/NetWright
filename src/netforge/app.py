"""
NetForge — 网络工程师工作台（应用壳）
=====================================

职责仅三件事：导航壳 / 全局主题 / 页面装配。业务逻辑全部在
``netforge.lib``（纯逻辑）与 ``netforge.pages``（工作区页面）。

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
from netforge.pages import PAGE_REGISTRY  # noqa: E402
from netforge.theme import FG, FONT_SMALL, LINE, MUTED, NAVY, setup_ttk, theme  # noqa: E402


class NetForgeApp(tk.Tk):
    """主窗口：顶栏 + 侧栏导航 + 工作区容器 + 底部状态栏。"""

    def __init__(self):
        super().__init__()
        self.title(f"NetForge — 网络工程师工作台 v{__version__}")
        self.geometry("1120x760")
        self.minsize(1000, 660)
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
        self.controller_api = ControllerAPI(self.controller_state)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        # ── 顶栏 ──
        top = tk.Frame(self, bg=NAVY, height=58)
        top.pack(fill=tk.X)
        top.pack_propagate(False)
        tk.Frame(top, bg=theme.accent, width=3).pack(side=tk.LEFT, fill=tk.Y)
        tk.Label(top, text="⛏", bg=NAVY, fg=FG, font=("", 16)).pack(side=tk.LEFT, padx=(14, 8))
        tk.Label(top, text="NetForge", bg=NAVY, fg=FG, font=("", 14, "bold")).pack(side=tk.LEFT)
        tk.Label(top, text="网络工程师工作台", bg=NAVY, fg=MUTED,
                 font=FONT_SMALL).pack(side=tk.LEFT, padx=(10, 0))
        self.var_status = tk.StringVar(value="就绪")
        self.var_clock = tk.StringVar(value="")
        tk.Label(top, textvariable=self.var_clock, bg=NAVY, fg=MUTED,
                 font=FONT_SMALL).pack(side=tk.RIGHT, padx=14)
        tk.Label(top, textvariable=self.var_status, bg=NAVY, fg=FG,
                 font=FONT_SMALL).pack(side=tk.RIGHT, padx=14)
        self._tick_clock()

        # ── 主体：侧栏 + 工作区 ──
        main = tk.Frame(self, bg=theme.bg)
        main.pack(fill=tk.BOTH, expand=True)
        rail = tk.Frame(main, bg=NAVY, width=172)
        rail.pack(side=tk.LEFT, fill=tk.Y)
        rail.pack_propagate(False)
        self._build_nav(rail)

        self.pages = {key: cls(main, self) for key, (_n, _i, cls) in PAGE_REGISTRY.items()}
        self.show("dashboard")

    # ── 侧栏导航（hover 反馈 + 选中指示条）─────────────────────────
    def _build_nav(self, rail: tk.Frame):
        tk.Label(rail, text="  工作区", bg=NAVY, fg=MUTED, font=FONT_SMALL,
                 anchor="w").pack(fill=tk.X, pady=(10, 2))
        self._nav_buttons: dict[str, tk.Label] = {}
        for key, (name, icon, _cls) in PAGE_REGISTRY.items():
            btn = tk.Label(rail, text=f"  {icon}  {name}", bg=NAVY, fg=MUTED,
                           font=("Microsoft YaHei UI", 11), anchor="w", pady=9,
                           cursor="hand2")
            btn.pack(fill=tk.X)
            btn.bind("<Button-1>", lambda e, k=key: self.show(k))
            btn.bind("<Enter>", lambda e, b=btn: b.config(fg="white")
                     if b.cget("bg") == NAVY else None)
            btn.bind("<Leave>", lambda e, b=btn, k=key: b.config(fg=MUTED)
                     if self._active_key != k else None)
            self._nav_buttons[key] = btn
        tk.Frame(rail, bg=LINE, height=1).pack(fill=tk.X, padx=10, pady=8)
        tk.Label(rail, text=f"v{__version__}", bg=NAVY, fg=MUTED,
                 font=FONT_SMALL).pack(side=tk.BOTTOM, pady=10)
        self._active_key = "dashboard"

    def _highlight_nav(self, key: str):
        self._active_key = key
        for k, btn in self._nav_buttons.items():
            active = k == key
            btn.config(bg=theme.accent if active else NAVY,
                       fg="white" if active else MUTED,
                       font=("Microsoft YaHei UI", 11, "bold" if active else "normal"))

    # ── 工作区切换 ─────────────────────────────────────────────────
    def show(self, key: str):
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
        self.set_status("就绪")

    # ── 状态栏 ─────────────────────────────────────────────────────
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
        self.destroy()


def main() -> None:
    app = NetForgeApp()
    app.mainloop()


if __name__ == "__main__":
    main()
