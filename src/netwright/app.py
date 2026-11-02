"""
NetWright — SDN 控制器控制台（应用壳）
======================================

职责只有四件事：**外壳导航 / 主题系统 / 页面装配 / 设置持久化**。
业务逻辑分布在三层：

  ``netwright.sdn``           控制器内核：事件总线、图模型、策略编译、南向适配器、REST v2
  ``netwright.lib``           纯逻辑：清单、巡检、生成、计算、既有意图下发
  ``netwright.pages``         工作区页面：只做装配与展示

视觉骨架（对齐 OpenDaylight DLUX 一类控制器控制台）：
  深色顶栏（品牌 + 控制器状态 + 时钟 + 主题）
  深色分组侧栏（控制器 / 资源 / 运维，可折叠成图标条）
  浅色内容区（白卡片 + 大表格 + 拓扑画布）
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
from netwright import __version__  # noqa: E402
from netwright import demo as demo_mod  # noqa: E402
from netwright.lib.controller.restapi import ControllerAPI, ControllerState  # noqa: E402
from netwright.lib.inventory import Inventory  # noqa: E402
from netwright.lib.settings import load_settings, save_settings  # noqa: E402
from netwright.paths import resource_dir  # noqa: E402
from netwright.pages import NAV_GROUPS, PAGE_REGISTRY  # noqa: E402
from netwright.pages.help import show_help  # noqa: E402
from netwright.sdn import ControllerStore, EventBus  # noqa: E402
from netwright.sdn.auth import TokenAuth  # noqa: E402
from netwright.sdn.backup import ConfigBackup  # noqa: E402
from netwright.theme import (  # noqa: E402
    FONT_SMALL, PRIMARY_HUES, SIDEBAR_COLLAPSED_W, SIDEBAR_W, TOPBAR_H,
    setup_ttk, theme,
)
from netwright.widgets import StatusDot  # noqa: E402

# 各工作区的"刷新入口"：自动刷新与 F5 走同一套，避免每个页面各写一套
PAGE_REFRESH = {
    "dashboard": "refresh",
    "topology": "refresh",
    "events": "refresh",
    "inventory": "refresh",
    "inspect": "refresh_devices",
    "discovery": "refresh",
}

AUTO_REFRESH_MS = 10_000       # 10 秒自动刷新（可在顶栏关掉）


class LazyPages(dict):
    """页面惰性容器（R11）：页面在第一次被访问时才构建。

    保持 ``app.pages[key]`` 的既有写法：``__getitem__`` 缺 key 时按需构建一次；
    ``get`` / ``in`` / 迭代都不触发构建——所以"已构建"与"已访问"是同一集合，
    冷启动只建当前页，启动时间不再被没点开的页面吃掉。
    """

    def __init__(self, app):
        super().__init__()
        self.app = app

    def __missing__(self, key):
        page = self.app._ensure_page(key)
        if page is None:
            raise KeyError(key)
        return page


class NetWrightApp(tk.Tk):
    """主窗口：深色控制台外壳 + 浅色内容区 + 控制器内核。"""

    def __init__(self):
        super().__init__()
        self.title(f"NetWright SDN Console v{__version__}")
        self.geometry("1280x820")
        self.minsize(1080, 700)
        self.base_dir = BASE_DIR

        # ── 设置（含主题记忆）──
        self.settings = load_settings(BASE_DIR)
        theme.use_mode(self.settings.get("theme_mode", "dark"),
                       self.settings.get("theme_hue", "蓝"))
        self.configure(bg=theme.bg)
        self.option_add("*Font", ("Microsoft YaHei UI", 10))
        setup_ttk(self)
        ico = os.path.join(resource_dir("assets"), "icon.ico")
        if os.path.isfile(ico):
            try:
                self.iconbitmap(ico)
            except Exception:
                pass

        # ── 控制器内核 ──
        self.inventory = Inventory()
        self.event_bus = EventBus()
        self.api_auth = TokenAuth.from_settings(self.settings)
        self.controller_store = ControllerStore(
            self.inventory, self.event_bus, auth=self.api_auth,
            backups=ConfigBackup(BASE_DIR, self.event_bus))
        save_settings(self.settings, BASE_DIR)
        self.controller_state = ControllerState(self.inventory, self.controller_store)
        self.controller_api = ControllerAPI(self.controller_state,
                                            port=int(self.settings.get("rest_port", 8899)))
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        # ── 外壳 ──
        self._active_key = self.settings.get("last_page", "dashboard")
        self.nav_collapsed = bool(self.settings.get("nav_collapsed", False))
        self.auto_refresh = bool(self.settings.get("auto_refresh", True))
        self._auto_job = None
        self._help_dialog = None
        self._nav_items: dict[str, tk.Frame] = {}
        self._build_shell()
        self.show(self._active_key if self._active_key in PAGE_REGISTRY else "dashboard")
        self._tick_clock()
        self._bind_shortcuts()
        self._schedule_auto_refresh()
        self.event_bus.publish("controller.started",
                               f"控制器已启动 · REST v2 就绪于 127.0.0.1:{self.controller_api.port}",
                               source="app", version=__version__)

    # ══════════════════════════════════════════════════════════════════
    # 外壳装配
    # ══════════════════════════════════════════════════════════════════
    def _build_shell(self):
        self._build_topbar()
        self._build_main()

    def _build_topbar(self):
        """52px 深色顶栏：品牌 / 控制器状态 / 页面标题 / 时钟 / 主题。"""
        self.top = tk.Frame(self, bg=theme.chrome, height=TOPBAR_H)
        self.top.pack(fill=tk.X)
        self.top.pack_propagate(False)

        self.var_status = tk.StringVar(value="就绪")
        self.var_clock = tk.StringVar(value="")
        self.var_ptitle = tk.StringVar(value="")
        self.var_updated = tk.StringVar(value="")

        # 折叠按钮
        tk.Button(self.top, text="☰", bg=theme.chrome, fg=theme.chrome_muted,
                  activebackground=theme.chrome_alt, activeforeground=theme.chrome_fg,
                  relief=tk.FLAT, font=("", 12), width=3, cursor="hand2",
                  bd=0, command=self.toggle_nav).pack(side=tk.LEFT, padx=(6, 2))

        # 品牌
        brand = tk.Frame(self.top, bg=theme.chrome)
        brand.pack(side=tk.LEFT, padx=(2, 14))
        self._logo = tk.Canvas(brand, width=22, height=22, bg=theme.chrome,
                               highlightthickness=0, bd=0)
        self._logo.pack(side=tk.LEFT)
        self._draw_logo()
        tk.Label(brand, text="NetWright", bg=theme.chrome, fg=theme.chrome_fg,
                 font=("Microsoft YaHei UI", 12, "bold")).pack(side=tk.LEFT, padx=(7, 6))
        tk.Label(brand, text="SDN", bg=theme.chrome_accent, fg="#FFFFFF",
                 font=("Microsoft YaHei UI", 8, "bold"), padx=5, pady=1).pack(side=tk.LEFT)

        # 分隔 + 页面标题
        tk.Frame(self.top, bg=theme.chrome_line, width=1, height=22).pack(
            side=tk.LEFT, padx=(6, 12))
        tk.Label(self.top, textvariable=self.var_ptitle, bg=theme.chrome,
                 fg=theme.chrome_muted, font=FONT_SMALL).pack(side=tk.LEFT)

        # 右侧：时钟 / 状态 / 集群 / 主题
        tk.Label(self.top, textvariable=self.var_clock, bg=theme.chrome,
                 fg=theme.chrome_muted, font=FONT_SMALL).pack(side=tk.RIGHT, padx=(0, 14))
        tk.Label(self.top, textvariable=self.var_updated, bg=theme.chrome,
                 fg=theme.chrome_muted, font=FONT_SMALL).pack(side=tk.RIGHT, padx=(0, 8))
        self.status_dot = StatusDot(self.top, text="控制器在线", tone="ok",
                                    bg=theme.chrome)
        self.status_dot.pack(side=tk.RIGHT, padx=(0, 12))
        tk.Label(self.top, textvariable=self.var_status, bg=theme.chrome,
                 fg=theme.chrome_muted, font=FONT_SMALL).pack(side=tk.RIGHT, padx=(0, 12))

        self.mb_hue = tk.Menubutton(self.top, text="◈ 主色", bg=theme.chrome,
                                    fg=theme.chrome_muted, relief=tk.FLAT,
                                    activebackground=theme.chrome_alt,
                                    activeforeground=theme.chrome_fg,
                                    font=FONT_SMALL, cursor="hand2", bd=0)
        hue_menu = tk.Menu(self.mb_hue, tearoff=0, font=FONT_SMALL)
        for hue in PRIMARY_HUES:
            mark = "●" if hue == theme.hue else "○"
            hue_menu.add_command(label=f"{mark} {hue}色", command=lambda h=hue: self.apply_theme(theme.mode, h))
        self.mb_hue["menu"] = hue_menu
        self.mb_hue.pack(side=tk.RIGHT, padx=(0, 6))

        self.btn_mode = tk.Button(self.top, text=self._mode_label(), bg=theme.chrome,
                                  fg=theme.chrome_muted, relief=tk.FLAT, bd=0,
                                  activebackground=theme.chrome_alt,
                                  activeforeground=theme.chrome_fg,
                                  font=FONT_SMALL, cursor="hand2",
                                  command=self.toggle_mode)
        self.btn_mode.pack(side=tk.RIGHT, padx=(0, 6))

        tk.Button(self.top, text="?  引导", bg=theme.chrome, fg=theme.chrome_muted,
                  relief=tk.FLAT, bd=0, activebackground=theme.chrome_alt,
                  activeforeground=theme.chrome_fg, font=FONT_SMALL, cursor="hand2",
                  command=self.open_help).pack(side=tk.RIGHT, padx=(0, 10))

        self.var_auto = tk.BooleanVar(value=self.auto_refresh)
        tk.Checkbutton(self.top, text="自动 10s", variable=self.var_auto,
                       command=self.toggle_auto_refresh,
                       bg=theme.chrome, fg=theme.chrome_muted,
                       selectcolor=theme.chrome_alt,
                       activebackground=theme.chrome, activeforeground=theme.chrome_fg,
                       highlightthickness=0, bd=0, font=FONT_SMALL,
                       cursor="hand2").pack(side=tk.RIGHT, padx=(0, 10))

    def _draw_logo(self):
        """品牌标记：控制器枢纽 + 三个环绕节点（与 assets/logo.png 同一套造型）。"""
        c = self._logo
        c.delete("all")
        accent = theme.chrome_accent
        cx = cy = 11
        orbit = 6.6
        nodes = [(cx, cy - orbit), (cx - orbit * 0.92, cy + orbit * 0.7),
                 (cx + orbit * 0.92, cy + orbit * 0.7)]
        for nx, ny in nodes:
            c.create_line(cx, cy, nx, ny, fill=accent, width=1.4)
        c.create_line(*nodes[0], *nodes[1], fill=theme.chrome_line, width=1)
        c.create_line(*nodes[1], *nodes[2], fill=theme.chrome_line, width=1)
        c.create_line(*nodes[2], *nodes[0], fill=theme.chrome_line, width=1)
        for nx, ny in nodes:
            c.create_oval(nx - 2.6, ny - 2.6, nx + 2.6, ny + 2.6,
                          fill=accent, outline="")
            c.create_oval(nx - 1.1, ny - 1.1, nx + 1.1, ny + 1.1,
                          fill=theme.chrome, outline="")
        c.create_oval(cx - 3.6, cy - 3.6, cx + 3.6, cy + 3.6, fill=accent, outline="")
        c.create_oval(cx - 1.4, cy - 1.4, cx + 1.4, cy + 1.4, fill="#FFFFFF", outline="")

    def _build_main(self):
        main = tk.Frame(self, bg=theme.bg)
        self.main_frame = main
        main.pack(fill=tk.BOTH, expand=True)

        self.rail = tk.Frame(main, bg=theme.chrome_alt,
                             width=SIDEBAR_COLLAPSED_W if self.nav_collapsed else SIDEBAR_W)
        self.rail.pack(side=tk.LEFT, fill=tk.Y)
        self.rail.pack_propagate(False)
        self.container = tk.Frame(main, bg=theme.bg)
        self.container.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self._build_nav()
        self.pages = LazyPages(self)

    def _ensure_page(self, key):
        """按需构建页面（R11，幂等）：已构建直接返回；未构建构建一次并缓存。"""
        page = self.pages.get(key)          # dict.get 不触发 __missing__
        if page is not None:
            return page
        if key not in PAGE_REGISTRY:
            return None
        _label, _icon, cls = PAGE_REGISTRY[key]
        page = cls(self.container, self)
        self.pages[key] = page
        return page

    # ── 侧栏导航 ──────────────────────────────────────────────────
    def _build_nav(self):
        for child in self.rail.winfo_children():
            child.destroy()
        self._nav_items = {}
        collapsed = self.nav_collapsed
        pad_x = 8 if collapsed else 12
        for group, items in NAV_GROUPS:
            if not collapsed:
                tk.Label(self.rail, text=group.upper(), bg=theme.chrome_alt,
                         fg=theme.chrome_muted,
                         font=("Microsoft YaHei UI", 8), anchor="w").pack(
                    fill=tk.X, padx=14, pady=(14, 4))
            for key, label, icon in items:
                row = tk.Frame(self.rail, bg=theme.chrome_alt, cursor="hand2")
                row.pack(fill=tk.X, padx=pad_x, pady=1)
                bar = tk.Frame(row, bg=theme.chrome_alt, width=3)
                bar.pack(side=tk.LEFT, fill=tk.Y)
                icon_lbl = tk.Label(row, text=icon, bg=theme.chrome_alt,
                                    fg=theme.chrome_muted,
                                    font=("Microsoft YaHei UI", 11),
                                    width=3 if collapsed else 2)
                icon_lbl.pack(side=tk.LEFT, padx=(8 if not collapsed else 0, 0))
                text_lbl = None
                if not collapsed:
                    text_lbl = tk.Label(row, text=label, bg=theme.chrome_alt,
                                        fg=theme.chrome_fg, anchor="w",
                                        font=("Microsoft YaHei UI", 10), pady=9)
                    text_lbl.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(2, 8))
                else:
                    icon_lbl.pack_configure(pady=10)
                self._nav_items[key] = row
                row._bar = bar            # type: ignore[attr-defined]
                row._icon = icon_lbl      # type: ignore[attr-defined]
                row._text = text_lbl      # type: ignore[attr-defined]
                for widget in (row, icon_lbl) + ((text_lbl,) if text_lbl else ()):
                    widget.bind("<Button-1>", lambda _e, k=key: self.show(k))
                    widget.bind("<Enter>", lambda _e, k=key: self._hover_nav(k, True))
                    widget.bind("<Leave>", lambda _e, k=key: self._hover_nav(k, False))
        tk.Label(self.rail, text=f"v{__version__}", bg=theme.chrome_alt,
                 fg="#546A80", font=("Microsoft YaHei UI", 8)).pack(side=tk.BOTTOM, pady=10)

    def _hover_nav(self, key: str, entering: bool):
        row = self._nav_items.get(key)
        if row is None:
            return
        if key == self._active_key:
            return
        bg = theme.chrome if entering else theme.chrome_alt
        row.config(bg=bg)
        for child in row.winfo_children():
            try:
                child.config(bg=bg)
            except tk.TclError:
                pass

    def _paint_active(self):
        for key, row in self._nav_items.items():
            active = key == self._active_key
            bg = theme.chrome if active else theme.chrome_alt
            row.config(bg=bg)
            for child in row.winfo_children():
                try:
                    child.config(bg=bg)
                except tk.TclError:
                    pass
            row._bar.config(bg=theme.chrome_accent if active else bg)  # type: ignore[attr-defined]
            row._icon.config(fg=theme.chrome_fg if active else theme.chrome_muted)  # type: ignore[attr-defined]
            if row._text is not None:  # type: ignore[attr-defined]
                row._text.config(fg=theme.chrome_fg if active else "#B7C7D8",  # type: ignore[attr-defined]
                                 font=("Microsoft YaHei UI", 10, "bold" if active else "normal"))

    def toggle_nav(self):
        self.nav_collapsed = not self.nav_collapsed
        self.settings["nav_collapsed"] = self.nav_collapsed
        self.rail.config(width=SIDEBAR_COLLAPSED_W if self.nav_collapsed else SIDEBAR_W)
        self._build_nav()
        self._paint_active()

    # ══════════════════════════════════════════════════════════════════
    # 主题
    # ══════════════════════════════════════════════════════════════════
    def _mode_label(self) -> str:
        return "☀ 浅色" if theme.mode == "dark" else "🌙 深色"

    def toggle_mode(self):
        self.apply_theme("dark" if theme.mode == "light" else "light", theme.hue)

    def apply_theme(self, mode_or_name: str, hue: str | None = None):
        mode = mode_or_name if mode_or_name in ("light", "dark") else (
            "light" if ("浅" in mode_or_name or "亮" in mode_or_name) else "dark")
        theme.use_mode(mode, hue)
        self.settings["theme_mode"] = theme.mode
        self.settings["theme_hue"] = theme.hue
        save_settings(self.settings, BASE_DIR)
        setup_ttk(self)
        self.configure(bg=theme.bg)

        old_pages = getattr(self, "pages", {})
        old_top = getattr(self, "top", None)
        old_main = getattr(self, "main_frame", None)

        # 先建新外壳，再销毁旧的（避免中途重绘闪烁）。
        # R11：页面容器换成空 LazyPages——只有当前页会随 show() 重建，
        # 没访问过的页面不花构建时间（下次 show 时按需重建，天然带新主题）。
        self._build_topbar()
        self._build_main()
        self._paint_active()

        for page in old_pages.values():
            page.destroy()
        if old_top is not None:
            old_top.destroy()
        if old_main is not None:
            old_main.destroy()

        self.show(self._active_key if self._active_key in PAGE_REGISTRY else "dashboard")
        self.set_status(f"主题已切换：{'深色' if theme.mode == 'dark' else '浅色'} · {theme.hue}色")

    # ══════════════════════════════════════════════════════════════════
    # 工作区切换
    # ══════════════════════════════════════════════════════════════════
    def show(self, key: str):
        if key not in PAGE_REGISTRY:
            return
        page = self.pages[key]              # 未构建时由 LazyPages 按需构建
        for k, built in self.pages.items():
            if k == key:
                built.place(relx=0, rely=0, relwidth=1, relheight=1)
            else:
                built.place_forget()
        self._active_key = key
        self.var_ptitle.set(PAGE_REGISTRY[key][0] if key in PAGE_REGISTRY else "")
        self._paint_active()
        hook = PAGE_REFRESH.get(key)
        if hook and hasattr(page, hook):
            try:
                getattr(page, hook)()
            except Exception:      # noqa: BLE001  单页刷新失败不应拦住导航
                pass
        if hasattr(page, "on_show"):
            page.on_show()
        self.set_status("就绪")

    def clear_demo_data(self) -> int:
        """清除演示设备/链路并同步图与页面（载入与清除成对出现）。"""
        removed = demo_mod.clear(self.inventory)
        self.controller_store.graph.clear()
        self.controller_store.sync_inventory()
        for key in ("dashboard", "inventory", "topology"):
            page = self.pages.get(key)
            hook = PAGE_REFRESH.get(key)
            if page is not None and hook and hasattr(page, hook):
                try:
                    getattr(page, hook)()
                except Exception:      # noqa: BLE001
                    pass
        self.event_bus.publish("demo.cleared", f"已清除 {removed} 台演示设备", source="app")
        self.set_status(f"演示数据已清除：{removed} 台设备")
        return removed

    def refresh_dashboard(self):
        page = self.pages.get("dashboard")
        if page is not None and hasattr(page, "refresh"):
            page.refresh()

    # ── 刷新（手动 F5 / 自动 10s 共用同一入口）────────────────────
    def refresh_current(self, silent: bool = True):
        """刷新当前工作区；刷新失败不打断用户操作。"""
        page = self.pages.get(self._active_key)
        if page is None:
            return False
        hook = PAGE_REFRESH.get(self._active_key)
        fn = getattr(page, hook, None) if hook else None
        if fn is None:
            return False
        if getattr(page, "_busy", False):
            return False
        try:
            fn()
        except Exception:      # noqa: BLE001  自动刷新绝不能把界面带崩
            return False
        self.var_updated.set(datetime.now().strftime("%H:%M:%S"))
        if not silent:
            self.set_status(f"已刷新 · {self.var_updated.get()}")
        return True

    def toggle_auto_refresh(self):
        self.auto_refresh = bool(self.var_auto.get())
        self.settings["auto_refresh"] = self.auto_refresh
        save_settings(self.settings, BASE_DIR)
        if self.auto_refresh:
            self._schedule_auto_refresh()
            self.set_status("已开启自动刷新（10 秒）")
        else:
            self._cancel_auto_refresh()
            self.set_status("已关闭自动刷新，可用 F5 手动刷新")

    def _schedule_auto_refresh(self):
        self._cancel_auto_refresh()
        if self.auto_refresh:
            self._auto_job = self.after(AUTO_REFRESH_MS, self._auto_tick)

    def _cancel_auto_refresh(self):
        if self._auto_job is not None:
            try:
                self.after_cancel(self._auto_job)
            except tk.TclError:
                pass
            self._auto_job = None

    def _auto_tick(self):
        self._auto_job = None
        try:
            self.refresh_current(silent=True)
        finally:
            if self.auto_refresh:
                self._schedule_auto_refresh()

    # ── 帮助 / 快捷键 ─────────────────────────────────────────────
    def open_help(self):
        return show_help(self)

    # ── API token（v2 写接口鉴权）──────────────────────────────────
    def rotate_api_token(self) -> str:
        token = self.api_auth.rotate()
        self.settings["api_token"] = token
        save_settings(self.settings, BASE_DIR)
        self.event_bus.publish("api.token_rotated", "REST API token 已轮换（旧 token 立即失效）",
                               source="app")
        return token

    def _bind_shortcuts(self):
        self.bind("<F5>", lambda _e: self.refresh_current(silent=False))
        self.bind("<Control-h>", lambda _e: self.open_help())
        self.bind("<Control-H>", lambda _e: self.open_help())
        keys = list(PAGE_REGISTRY)
        for i, key in enumerate(keys[:9], start=1):
            self.bind(f"<Control-Key-{i}>", lambda _e, k=key: self.show(k))

    def set_status(self, text: str):
        self.var_status.set(text)

    def _tick_clock(self):
        self.var_clock.set(datetime.now().strftime("%Y-%m-%d %H:%M"))
        self.after(30_000, self._tick_clock)

    def _on_close(self):
        self._cancel_auto_refresh()
        dialog = getattr(self, "_help_dialog", None)
        if dialog is not None:
            try:
                dialog.destroy()
            except tk.TclError:
                pass
        try:
            self.controller_api.stop()
        except Exception:
            pass
        try:
            self.controller_store.save(BASE_DIR)
        except Exception:
            pass
        self.settings["last_page"] = getattr(self, "_active_key", "dashboard")
        save_settings(self.settings, BASE_DIR)
        self.destroy()


def main() -> None:
    app = NetWrightApp()
    app.mainloop()


if __name__ == "__main__":
    main()
