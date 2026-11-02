"""store.py — 控制器状态仓库（拓扑图 + 策略 + 运行统计）。

单一事实来源：GUI 页面、北向 REST、事件全部读写这一份状态，避免"页面各自缓存"。
线程模型：调用方持锁语义由自身保证（GUI 主线程写，采集线程只读快照）；
``snapshot()`` 返回纯 dict，可安全跨线程传给 REST 线程。
"""
from __future__ import annotations

import json
import os
import threading
import time

from .events import EventBus
from .model import NetworkGraph
from .policy import CompileResult, PolicyCompiler
from .southbound import default_registry

FILENAME = "netwright_controller.json"
MAX_POLICIES = 500


class ControllerStore:
    """控制器内核状态。"""

    def __init__(self, inventory, bus: EventBus | None = None, registry=None):
        self.inventory = inventory
        # 注意：不能写 ``bus or EventBus()`` —— EventBus 定义了 __len__，
        # 空总线是 falsy，会被悄悄换成另一条总线（页面与内核就看不到彼此的事件）。
        self.bus = bus if bus is not None else EventBus()
        self.registry = registry or default_registry(self.bus)
        self.compiler = PolicyCompiler(self.bus)
        self.graph = NetworkGraph()
        self.policies: dict[str, object] = {}
        self.started_at = time.time()
        self.last_topology_at: float | None = None
        self.last_discovery_at: float | None = None
        self._lock = threading.RLock()
        self.sync_inventory(publish=False)

    # ── 设备 → 图 ──
    def sync_inventory(self, publish: bool = True) -> NetworkGraph:
        """把设备清单同步进图（保留已发现的 LLDP 边）。"""
        with self._lock:
            for device in getattr(self.inventory, "devices", []):
                name = getattr(device, "display_name", None) or device.host
                self.graph.add_node(name, getattr(device, "vendor", ""), "switch", True,
                                    host=getattr(device, "host", ""),
                                    protocol=getattr(device, "protocol", "ssh"),
                                    port=getattr(device, "port", 0))
            ledger_added = self.graph.add_ledger_links(getattr(self.inventory, "links", []))
        if publish:
            self.bus.publish("inventory.synced",
                             f"设备清单同步完成：{len(self.graph.nodes)} 个节点，"
                             f"台账链路新增 {ledger_added} 条",
                             source="store", nodes=len(self.graph.nodes), ledger=ledger_added)
        return self.graph

    # ── 拓扑 ──
    def apply_topology(self, topology, publish: bool = True) -> NetworkGraph:
        """把一次 LLDP 采集结果并入图（幂等：重复发现不会重复边）。"""
        with self._lock:
            discovered = NetworkGraph.from_topology(topology, self.inventory)
            before_links = len(self.graph.edges)
            self.graph.merge(discovered)
            self.last_topology_at = time.time()
            new_links = len(self.graph.edges) - before_links
            stats = self.graph.stats()
        if publish:
            self.bus.publish("topology.changed",
                             f"拓扑更新：{stats['nodes']} 节点 / {stats['links']} 链路"
                             f"（本次新增 {new_links}）",
                             source="topology", nodes=stats["nodes"],
                             links=stats["links"], new_links=new_links)
        return self.graph

    # ── 策略 ──
    def compile(self, intent_key: str, params: dict, devices: list | None = None) -> CompileResult:
        """编译意图 → 策略，并入库存（不连设备）。"""
        targets = list(devices if devices is not None else self.inventory.devices)
        result = self.compiler.compile(intent_key, params, targets)
        with self._lock:
            for policy in result.policies:
                self.policies[policy.id] = policy
            if len(self.policies) > MAX_POLICIES:
                for stale in list(self.policies)[:len(self.policies) - MAX_POLICIES]:
                    self.policies.pop(stale, None)
        return result

    def recent_policies(self, limit: int = 50) -> list:
        with self._lock:
            items = sorted(self.policies.values(), key=lambda p: p.created, reverse=True)
        return items[:limit]

    # ── 统计 / 快照 ──
    def summary(self) -> dict:
        graph_stats = self.graph.stats()
        return {
            "nodes": graph_stats["nodes"],
            "links": graph_stats["links"],
            "managed": graph_stats["managed"],
            "isolated": graph_stats["isolated"],
            "by_vendor": graph_stats["by_vendor"],
            "by_source": graph_stats["by_source"],
            "policies": len(self.policies),
            "events": self.bus.counts(),
            "southbound": len(self.registry),
            "uptime_s": int(time.time() - self.started_at),
            "last_topology_at": self.last_topology_at,
        }

    def snapshot(self, limit: int = 80) -> dict:
        """跨线程安全的只读快照（北向 REST 与页面刷新共用）。"""
        return {
            "summary": self.summary(),
            "topology": self.graph.to_dict(),
            "policies": [p.to_dict() for p in self.recent_policies(limit)],
            "events": [e.to_dict() for e in self.bus.snapshot(limit)],
            "southbound": self.registry.describe(),
        }

    # ── 持久化（拓扑与策略，便于重启后仍有上下文；不含凭据）──
    def save(self, base_dir: str) -> bool:
        path = os.path.join(base_dir, FILENAME)
        payload = {"version": 1,
                   "saved_at": time.time(),
                   "topology": self.graph.to_dict(),
                   "policies": [p.to_dict() for p in self.recent_policies(200)]}
        tmp = path + ".tmp"
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, indent=2)
            os.replace(tmp, path)
            return True
        except OSError:
            return False

    def load(self, base_dir: str) -> bool:
        path = os.path.join(base_dir, FILENAME)
        try:
            with open(path, encoding="utf-8") as f:
                payload = json.load(f)
        except (OSError, ValueError):
            return False
        graph = NetworkGraph.from_dict(payload.get("topology") or {})
        with self._lock:
            self.graph.merge(graph)
            self.last_topology_at = payload.get("saved_at")
        return True
