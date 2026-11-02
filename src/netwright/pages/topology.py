"""拓扑工作区 —— 控制器主视图（DLUX 式拓扑画布）。

布局：左侧画布（可缩放/拖拽/点选）+ 右侧节点检查器 + 底部图例与统计。
数据：``app.controller_store.graph``（LLDP 实线 ∪ 台账虚线），
发现动作复用 ``lib.controller.deploy.discover_topology``，结果并回控制器图。

画布坐标系：世界坐标（逻辑布局，围绕原点）→ 视图变换（缩放 + 平移）→ 屏幕。
之所以不直接布局在屏幕坐标，是为了缩放/平移时不用重算布局。
"""
from __future__ import annotations

import math
import threading
import tkinter as tk

from netwright.lib.controller import topology as topo_mod
from netwright.theme import FONT_SMALL, VENDOR_COLORS, theme
from netwright.widgets import (KeyValue, Page, SectionCard, WButton, page_header)

CANVAS_BG = "topo_bg"

KIND_LABEL = {"switch": "交换机", "router": "路由器", "host": "主机",
              "controller": "控制器", "unknown": "未知"}


class TopologyPage(Page):
    """拓扑画布页面。"""

    def __init__(self, master, app):
        super().__init__(master, app)
        hdr = page_header(self, "拓扑", "控制器实时拓扑：LLDP 实测链路（实线）+ 台账链路（虚线）",
                          "控制器 / 拓扑")
        self.btn_discover = WButton(hdr.actions, text="⟳ 从设备发现", command=self.discover)
        self.btn_discover.pack(side=tk.LEFT, padx=(0, 6))
        self.cmb_layout = tk.StringVar(value="力导向")
        layout_menu = tk.OptionMenu(hdr.actions, self.cmb_layout, "力导向", "环形", "分层",
                                    command=lambda _v: self.relayout())
        layout_menu.config(bg=theme.panel, fg=theme.fg, relief=tk.FLAT, bd=0,
                           highlightthickness=1, highlightbackground=theme.line,
                           activebackground=theme.panel_alt, font=FONT_SMALL,
                           cursor="hand2", padx=8, pady=4)
        layout_menu["menu"].config(font=FONT_SMALL)
        layout_menu.pack(side=tk.LEFT, padx=(0, 6))
        WButton(hdr.actions, text="⤢ 适配窗口", command=self.fit).pack(side=tk.LEFT, padx=(0, 6))
        WButton(hdr.actions, text="刷新", command=self.refresh).pack(side=tk.LEFT)

        self.var_stat = tk.StringVar(value="加载中…")

        body = tk.Frame(self, bg=theme.bg)
        body.pack(fill=tk.BOTH, expand=True, padx=20, pady=(0, 18))
        body.columnconfigure(0, weight=1)
        body.columnconfigure(1, weight=0, minsize=300)
        body.rowconfigure(0, weight=1)

        card = SectionCard(body, title="拓扑画布", desc="滚轮缩放 · 拖拽平移 · 单击节点查看详情")
        card.grid(row=0, column=0, sticky="nsew", padx=(0, 12))
        self.canvas = tk.Canvas(card.body, bg=theme.topo_bg, highlightthickness=0, bd=0)
        self.canvas.pack(fill=tk.BOTH, expand=True)
        self.canvas.bind("<Configure>", lambda _e: self._draw())
        self.canvas.bind("<MouseWheel>", self._on_wheel)
        self.canvas.bind("<ButtonPress-1>", self._on_press)
        self.canvas.bind("<B1-Motion>", self._on_drag)
        self.canvas.bind("<ButtonRelease-1>", self._on_release)
        self.canvas.bind("<Motion>", self._on_motion)

        # 图例：画布底部的横向条带（DLUX 习惯把图例放在画布下沿）
        legend = tk.Frame(card.body, bg=theme.panel)
        legend.pack(fill=tk.X, pady=(8, 0))
        tk.Frame(legend, bg=theme.line, height=1).pack(fill=tk.X, pady=(0, 6))
        self.legend_box = tk.Frame(legend, bg=theme.panel)
        self.legend_box.pack(fill=tk.X)

        side = tk.Frame(body, bg=theme.bg)
        side.grid(row=0, column=1, sticky="nsew")

        stat_card = SectionCard(side, title="概览")
        stat_card.pack(fill=tk.X, pady=(0, 12))
        tk.Label(stat_card.body, textvariable=self.var_stat, bg=theme.panel,
                 fg=theme.fg, font=FONT_SMALL, justify=tk.LEFT, anchor="w",
                 wraplength=250).pack(fill=tk.X)

        self.inspector = SectionCard(side, title="节点详情")
        self.inspector.pack(fill=tk.BOTH, expand=True)
        self.inspector_hint = tk.Label(
            self.inspector.body, text="未选择节点\n\n在画布上单击任意节点查看属性与邻居",
            bg=theme.panel, fg=theme.faint, font=FONT_SMALL, justify=tk.LEFT, anchor="w")
        self.inspector_hint.pack(fill=tk.X)

        # 视图状态
        self._pos: dict[str, tuple[float, float]] = {}
        self._zoom = 1.0
        self._pan = [0.0, 0.0]
        self._selected: str | None = None
        self._hover: str | None = None
        self._drag_origin = None
        self._drag_moved = False
        self._canvas_size = (0, 0)
        self._refresh_soon()

    # ── 数据刷新 ──────────────────────────────────────────────────
    def _refresh_soon(self):
        self.after(50, self.refresh)

    def refresh(self):
        """同步清单 → 图，然后重算布局并重绘。"""
        store = getattr(self.app, "controller_store", None)
        if store is None:
            return
        store.sync_inventory(publish=False)
        stats = store.graph.stats()
        self.var_stat.set(
            f"节点：{stats['nodes']}\n链路：{stats['links']}\n"
            f"纳管：{stats['managed']}    孤立：{stats['isolated']}\n"
            f"链路来源：LLDP {stats['by_source'].get('lldp', 0)} / "
            f"台账 {stats['by_source'].get('ledger', 0)}")
        self._relayout_silent()
        self._draw()
        self._render_legend()
        self._render_inspector()

    def _render_legend(self):
        """画布下沿的横向图例：第一行链路样式，第二行厂商色板。"""
        for child in self.legend_box.winfo_children():
            child.destroy()
        line_row = tk.Frame(self.legend_box, bg=theme.panel)
        line_row.pack(fill=tk.X)
        vendor_row = tk.Frame(self.legend_box, bg=theme.panel)
        vendor_row.pack(fill=tk.X, pady=(4, 0))

        def add_line(label: str, dashed: bool):
            row = tk.Frame(line_row, bg=theme.panel)
            row.pack(side=tk.LEFT, padx=(0, 18))
            c = tk.Canvas(row, width=26, height=10, bg=theme.panel, highlightthickness=0)
            c.pack(side=tk.LEFT)
            c.create_line(0, 5, 26, 5, fill=theme.muted, width=2,
                          dash=(4, 3) if dashed else ())
            tk.Label(row, text=label, bg=theme.panel, fg=theme.muted,
                     font=FONT_SMALL).pack(side=tk.LEFT, padx=(5, 0))

        add_line("LLDP 实测链路", False)
        add_line("台账链路", True)

        vendors = sorted({(n.vendor or "generic")
                          for n in self.app.controller_store.graph.nodes.values()})
        if not vendors:
            tk.Label(vendor_row, text="尚无节点", bg=theme.panel, fg=theme.faint,
                     font=FONT_SMALL).pack(side=tk.LEFT)
        for vendor in vendors:
            row = tk.Frame(vendor_row, bg=theme.panel)
            row.pack(side=tk.LEFT, padx=(0, 14))
            dot = tk.Canvas(row, width=10, height=10, bg=theme.panel, highlightthickness=0)
            dot.pack(side=tk.LEFT)
            dot.create_oval(1, 1, 9, 9,
                            fill=VENDOR_COLORS.get(vendor, VENDOR_COLORS["generic"]),
                            outline="")
            tk.Label(row, text=vendor, bg=theme.panel, fg=theme.muted,
                     font=FONT_SMALL).pack(side=tk.LEFT, padx=(6, 0))

    def _relayout_silent(self):
        graph = self.app.controller_store.graph
        names = sorted(graph.nodes)
        if not names:
            self._pos = {}
            return
        mode = self.cmb_layout.get()
        if mode == "环形":
            self._pos = _layout_ring(names)
        elif mode == "分层":
            self._pos = _layout_layers(graph)
        else:
            self._pos = _layout_force(graph)
        self._fit_scale()

    def relayout(self):
        self._relayout_silent()
        self._draw()

    def fit(self):
        self._zoom = 1.0
        self._pan = [0.0, 0.0]
        self._fit_scale()
        self._draw()

    def _fit_scale(self):
        """把世界坐标缩放到画布内（留 60px 边距），并重置视图平移。"""
        w, h = self._canvas_size
        if not self._pos or w < 40 or h < 40:
            return
        xs = [p[0] for p in self._pos.values()]
        ys = [p[1] for p in self._pos.values()]
        span_x = max(1.0, max(xs) - min(xs))
        span_y = max(1.0, max(ys) - min(ys))
        self._base_scale = min((w - 120) / span_x, (h - 120) / span_y)
        self._center = ((max(xs) + min(xs)) / 2, (max(ys) + min(ys)) / 2)

    # ── 坐标变换 ──────────────────────────────────────────────────
    def _screen(self, name: str) -> tuple[float, float]:
        x, y = self._pos.get(name, (0.0, 0.0))
        cx, cy = getattr(self, "_center", (0.0, 0.0))
        base = getattr(self, "_base_scale", 1.0) * self._zoom
        w, h = self._canvas_size
        return (w / 2 + (x - cx) * base + self._pan[0],
                h / 2 + (y - cy) * base + self._pan[1])

    def _hit(self, sx: float, sy: float) -> str | None:
        best, best_d = None, 18.0
        for name in self._pos:
            px, py = self._screen(name)
            d = math.hypot(px - sx, py - sy)
            if d < best_d:
                best, best_d = name, d
        return best

    # ── 绘制 ──────────────────────────────────────────────────────
    def _draw(self):
        c = self.canvas
        if not c.winfo_exists():
            return
        w, h = c.winfo_width(), c.winfo_height()
        if (w, h) != self._canvas_size:
            self._canvas_size = (w, h)
            self._fit_scale()
        c.delete("all")
        self._draw_grid(w, h)
        graph = self.app.controller_store.graph
        if not self._pos:
            c.create_text(w / 2, h / 2 - 10, text="拓扑为空",
                          fill=theme.muted, font=("Microsoft YaHei UI", 12))
            c.create_text(w / 2, h / 2 + 16,
                          text="在「设备清单」添加设备，或点右上角「从设备发现」",
                          fill=theme.faint, font=FONT_SMALL)
            return
        # 链路
        for edge in graph.edges:
            if edge.a not in self._pos or edge.b not in self._pos:
                continue
            x1, y1 = self._screen(edge.a)
            x2, y2 = self._screen(edge.b)
            hot = self._selected in (edge.a, edge.b)
            color = theme.accent if hot else (
                theme.line if edge.kind == "ledger" else theme.muted)
            width = 2 if hot else 1
            dash = (4, 3) if edge.kind == "ledger" else ()
            c.create_line(x1, y1, x2, y2, fill=color, width=width, dash=dash,
                          tags=("edge", f"edge:{edge.a}", f"edge:{edge.b}"))
            if hot and edge.a_port and edge.b_port:
                c.create_text((x1 + x2) / 2, (y1 + y2) / 2 - 8,
                              text=f"{edge.a_port} ↔ {edge.b_port}",
                              fill=theme.muted, font=("Consolas", 8))
        # 节点
        for name in sorted(self._pos):
            node = graph.nodes.get(name)
            vendor = getattr(node, "vendor", "") or "generic"
            color = VENDOR_COLORS.get(vendor, VENDOR_COLORS["generic"])
            x, y = self._screen(name)
            selected = name == self._selected
            hovered = name == self._hover
            r = 11 if selected else (10 if hovered else 9)
            if selected:
                c.create_oval(x - r - 6, y - r - 6, x + r + 6, y + r + 6,
                              outline=theme.accent, width=2, dash=(3, 2))
            c.create_oval(x - r, y - r, x + r, y + r, fill=color,
                          outline=theme.panel, width=2, tags=("node", f"node:{name}"))
            if getattr(node, "managed", False):
                # 纳管标记：节点中心白点（不压边，避免看起来像缺口）
                c.create_oval(x - 2.2, y - 2.2, x + 2.2, y + 2.2,
                              fill="#FFFFFF", outline="")
            label = name if len(name) <= 18 else name[:17] + "…"
            c.create_text(x, y + r + 10, text=label, fill=theme.fg,
                          font=("Microsoft YaHei UI", 9 if selected else 8),
                          tags=("node", f"node:{name}"))

    def _draw_grid(self, w: int, h: int):
        """点阵网格（用线段而不是上千个圆点，拖动重绘才不卡）。"""
        step = 40
        color = theme.topo_grid
        for x in range(step, w, step):
            self.canvas.create_line(x, 0, x, h, fill=color, width=1, tags=("grid",))
        for y in range(step, h, step):
            self.canvas.create_line(0, y, w, y, fill=color, width=1, tags=("grid",))

    # ── 交互 ──────────────────────────────────────────────────────
    def _on_wheel(self, event):
        if not self._pos:
            return
        factor = 1.15 if event.delta > 0 else 1 / 1.15
        self._zoom = max(0.25, min(4.0, self._zoom * factor))
        self._draw()

    def _on_press(self, event):
        self._drag_origin = (event.x, event.y, list(self._pan))
        self._drag_moved = False
        name = self._hit(event.x, event.y)
        if name:
            self._selected = name
            self._render_inspector()
            self._draw()

    def _on_drag(self, event):
        if self._drag_origin is None:
            return
        x0, y0, pan0 = self._drag_origin
        dx, dy = event.x - x0, event.y - y0
        if abs(dx) + abs(dy) > 3:
            self._drag_moved = True
        self._pan = [pan0[0] + dx, pan0[1] + dy]
        self._draw()

    def _on_release(self, _event):
        self._drag_origin = None

    def _on_motion(self, event):
        name = self._hit(event.x, event.y)
        if name != self._hover:
            self._hover = name
            self.canvas.config(cursor="hand2" if name else "arrow")
            self._draw()

    # ── 检查器 ────────────────────────────────────────────────────
    def _render_inspector(self):
        for child in self.inspector.body.winfo_children():
            child.destroy()
        graph = self.app.controller_store.graph
        name = self._selected
        if not name or name not in graph.nodes:
            tk.Label(self.inspector.body, text="未选择节点\n\n在画布上单击节点查看属性与邻居",
                     bg=theme.panel, fg=theme.faint, font=FONT_SMALL,
                     justify=tk.LEFT, anchor="w").pack(fill=tk.X)
            return
        node = graph.nodes[name]
        vendor = node.vendor or "generic"
        KeyValue(self.inspector.body, "节点", name, width=7).pack(fill=tk.X, pady=1)
        row = tk.Frame(self.inspector.body, bg=theme.panel)
        row.pack(fill=tk.X, pady=1)
        tk.Label(row, text="厂商", width=7, anchor="w", bg=theme.panel,
                 fg=theme.muted, font=FONT_SMALL).pack(side=tk.LEFT)
        dot = tk.Canvas(row, width=10, height=10, bg=theme.panel, highlightthickness=0)
        dot.pack(side=tk.LEFT)
        dot.create_oval(1, 1, 9, 9, fill=VENDOR_COLORS.get(vendor, VENDOR_COLORS["generic"]),
                        outline="")
        tk.Label(row, text=f" {vendor}", bg=theme.panel, fg=theme.fg,
                 font=FONT_SMALL).pack(side=tk.LEFT)
        KeyValue(self.inspector.body, "类型", KIND_LABEL.get(node.kind, node.kind),
                 width=7).pack(fill=tk.X, pady=1)
        KeyValue(self.inspector.body, "纳管", "是（有凭据）" if node.managed else "否（仅发现）",
                 width=7).pack(fill=tk.X, pady=1)
        KeyValue(self.inspector.body, "度数", str(graph.degree(name)),
                 width=7).pack(fill=tk.X, pady=1)
        if node.attrs.get("host"):
            KeyValue(self.inspector.body, "地址", node.attrs["host"], width=7).pack(fill=tk.X, pady=1)

        tk.Frame(self.inspector.body, bg=theme.line, height=1).pack(fill=tk.X, pady=8)
        tk.Label(self.inspector.body, text="邻居", bg=theme.panel, fg=theme.muted,
                 font=FONT_SMALL, anchor="w").pack(fill=tk.X)
        neighbors = graph.neighbors(name)
        if not neighbors:
            tk.Label(self.inspector.body, text="孤立节点（无链路）", bg=theme.panel,
                     fg=theme.faint, font=FONT_SMALL, anchor="w").pack(fill=tk.X, pady=4)
        for peer, port in neighbors:
            line = tk.Frame(self.inspector.body, bg=theme.panel)
            line.pack(fill=tk.X, pady=1)
            tk.Label(line, text=f"• {peer}", bg=theme.panel, fg=theme.fg,
                     font=FONT_SMALL, anchor="w").pack(side=tk.LEFT)
            tk.Label(line, text=port or "", bg=theme.panel, fg=theme.faint,
                     font=("Consolas", 8)).pack(side=tk.RIGHT)

    # ── 发现（后台线程 + 主线程回填）──────────────────────────────
    def discover(self):
        devices = [d for d in self.app.inventory.devices
                   if topo_mod.DISCOVERY_COMMANDS.get(d.vendor)]
        if not devices:
            self.app.set_status("没有可发现拓扑的设备（需要华为/思科/H3C/锐捷）")
            return
        self.btn_discover.set_loading(True, "发现中…")
        self.app.set_status(f"正在从 {len(devices)} 台设备采集邻居…")

        def worker():
            from netwright.lib.controller import deploy as deploy_mod
            try:
                topo = deploy_mod.discover_topology(devices)
                self.app.after(0, lambda: self._discover_done(topo, None))
            except Exception as exc:      # noqa: BLE001
                self.app.after(0, lambda e=exc: self._discover_done(None, e))

        threading.Thread(target=worker, daemon=True).start()

    def _discover_done(self, topo, error):
        self.btn_discover.set_loading(False)
        if error is not None:
            self.app.set_status(f"发现失败：{error}")
            return
        store = self.app.controller_store
        if topo is not None:
            self.app.controller_state.topology = topo
            store.apply_topology(topo)
        store.sync_inventory()
        self.refresh()
        stats = store.graph.stats()
        self.app.set_status(f"拓扑已更新：{stats['nodes']} 节点 / {stats['links']} 链路")


# ══════════════════════════════════════════════════════════════════════
# 布局算法（纯函数，便于单测）
# ══════════════════════════════════════════════════════════════════════

def _layout_ring(names: list[str]) -> dict[str, tuple[float, float]]:
    """环形布局：适合星型/小型网络。"""
    n = max(1, len(names))
    radius = 60.0 * n / (2 * math.pi) + 40
    return {name: (radius * math.cos(2 * math.pi * i / n),
                   radius * math.sin(2 * math.pi * i / n))
            for i, name in enumerate(names)}


def _layout_layers(graph) -> dict[str, tuple[float, float]]:
    """分层布局：按 BFS 距离从最高度数节点铺开（近核心在上，末端在下）。"""
    names = sorted(graph.nodes)
    if not names:
        return {}
    root = max(names, key=graph.degree)
    depth = {root: 0}
    frontier = [root]
    while frontier:
        nxt = []
        for name in frontier:
            for peer, _port in graph.neighbors(name):
                if peer not in depth:
                    depth[peer] = depth[name] + 1
                    nxt.append(peer)
        frontier = nxt
    for name in names:                       # 不连通节点单独一层
        depth.setdefault(name, max(depth.values(), default=0) + 1)
    rows: dict[int, list[str]] = {}
    for name, level in depth.items():
        rows.setdefault(level, []).append(name)
    pos: dict[str, tuple[float, float]] = {}
    for level, row in rows.items():
        row.sort()
        for i, name in enumerate(row):
            pos[name] = ((i - (len(row) - 1) / 2) * 110.0, level * 90.0)
    return pos


def _layout_force(graph, iterations: int = 240) -> dict[str, tuple[float, float]]:
    """Fruchterman-Reingold 力导向布局（确定性初始位置，结果可复现）。"""
    names = sorted(graph.nodes)
    if not names:
        return {}
    if len(names) == 1:
        return {names[0]: (0.0, 0.0)}
    pos: dict[str, list[float]] = {}
    for i, name in enumerate(names):        # 黄金角螺旋，避免初始重叠
        angle = i * 2.399963
        radius = 26.0 * math.sqrt(i + 1)
        pos[name] = [radius * math.cos(angle), radius * math.sin(angle)]
    edges = [(e.a, e.b) for e in graph.edges if e.a in pos and e.b in pos]
    n = len(names)
    area = 1.0 * n * n * 900
    k = math.sqrt(area / n)
    temperature = k * 0.9
    cooling = 0.96
    for _ in range(iterations):
        disp = {name: [0.0, 0.0] for name in names}
        for i, a in enumerate(names):
            for b in names[i + 1:]:
                dx = pos[a][0] - pos[b][0]
                dy = pos[a][1] - pos[b][1]
                dist = max(0.01, math.hypot(dx, dy))
                force = (k * k) / dist
                ux, uy = dx / dist, dy / dist
                disp[a][0] += ux * force
                disp[a][1] += uy * force
                disp[b][0] -= ux * force
                disp[b][1] -= uy * force
        for a, b in edges:
            dx = pos[a][0] - pos[b][0]
            dy = pos[a][1] - pos[b][1]
            dist = max(0.01, math.hypot(dx, dy))
            force = (dist * dist) / k
            ux, uy = dx / dist, dy / dist
            disp[a][0] -= ux * force
            disp[a][1] -= uy * force
            disp[b][0] += ux * force
            disp[b][1] += uy * force
        for name in names:
            dx, dy = disp[name]
            dist = max(0.01, math.hypot(dx, dy))
            step = min(dist, temperature)
            pos[name][0] += dx / dist * step
            pos[name][1] += dy / dist * step
            pos[name][0] = max(-4000.0, min(4000.0, pos[name][0]))
            pos[name][1] = max(-4000.0, min(4000.0, pos[name][1]))
        temperature *= cooling
    return {name: (round(x, 2), round(y, 2)) for name, (x, y) in pos.items()}
