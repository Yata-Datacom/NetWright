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
from .lifecycle import IntentLifecycle
from .model import NetworkGraph
from .policy import CompileResult, PolicyCompiler
from .sources import SnmpTrapListener, SyslogListener
from .southbound import default_registry

FILENAME = "netwright_controller.json"
MAX_POLICIES = 500


class ControllerStore:
    """控制器内核状态。"""

    def __init__(self, inventory, bus: EventBus | None = None, registry=None,
                 auth=None, backups=None):
        self.inventory = inventory
        # 注意：不能写 ``bus or EventBus()`` —— EventBus 定义了 __len__，
        # 空总线是 falsy，会被悄悄换成另一条总线（页面与内核就看不到彼此的事件）。
        self.bus = bus if bus is not None else EventBus()
        self.registry = registry or default_registry(self.bus)
        self.compiler = PolicyCompiler(self.bus)
        self.auth = auth
        self.backups = backups        # sdn.backup.ConfigBackup（可选，无则不落盘）
        self.lifecycle = IntentLifecycle(self)
        # 事件源（默认不启动，端口可能与系统服务冲突；由 UI/REST 显式开启）
        self.syslog = SyslogListener(self.bus)
        self.snmp_trap = SnmpTrapListener(self.bus)
        self.node_flash: dict[str, float] = {}
        self._bus_unsub = self.bus.subscribe(self._on_network_event,
                                             topic_prefix="")
        self.graph = NetworkGraph()
        self.policies: dict[str, object] = {}
        self.started_at = time.time()
        self.last_topology_at: float | None = None
        self.last_discovery_at: float | None = None
        self._lock = threading.RLock()
        self.sync_inventory(publish=False)

    # ── 配置备份 ──
    def backup_device(self, device, timeout: float = 20.0) -> dict:
        """读设备配置并落一份快照；返回快照信息。"""
        if self.backups is None:
            raise RuntimeError("未配置备份目录（ControllerStore.backups 为空）")
        adapter = self.registry.for_device(device)
        if adapter is None:
            raise RuntimeError(f"没有匹配 {getattr(device, 'protocol', '?')} 的南向适配器")
        if not hasattr(adapter, "read_config"):
            raise RuntimeError(f"{adapter.protocol} 适配器不支持配置回读")
        text = adapter.read_config(device, timeout=timeout)
        if not (text or "").strip():
            raise RuntimeError("设备返回空配置（命令不被支持或权限不足）")
        entry = self.backups.save(device.display_name, text,
                                  note=f"{getattr(device, 'host', '')} via {adapter.protocol}")
        return entry.to_dict()

    def backup_summary(self) -> dict:
        if self.backups is None:
            return {"enabled": False, "devices": [], "count": 0}
        devices = self.backups.devices()
        return {"enabled": True, "devices": devices, "count": len(devices),
                "root": self.backups.root}

    def compare_live(self, device, timeout: float = 20.0) -> dict:
        """读现网配置并与最近一次快照对比（不写新快照）。"""
        if self.backups is None:
            raise RuntimeError("未配置备份目录（ControllerStore.backups 为空）")
        adapter = self.registry.for_device(device)
        if adapter is None:
            raise RuntimeError(f"没有匹配 {getattr(device, 'protocol', '?')} 的南向适配器")
        text = adapter.read_config(device, timeout=timeout)
        if not (text or "").strip():
            raise RuntimeError("设备返回空配置（命令不被支持或权限不足）")
        name = device.display_name
        diff = self.backups.diff_against(name, text)
        self.bus.publish(
            "config.drift",
            f"{name}: 现网配置与最近快照{'有差异' if diff else '一致'}",
            severity="warning" if diff else "info",
            source="backup", device=name, changed=bool(diff))
        return {"device": name, "has_changes": bool(diff), "diff": diff}

    # ── 事件源（syslog / snmp trap）──
    def start_syslog(self, port: int | None = None) -> dict:
        if port:
            self.syslog.port = port
        self.syslog.start()
        self.bus.publish("source.started", f"Syslog 监听已启动：UDP {self.syslog.bound_port}",
                         source="store", port=self.syslog.bound_port)
        return self.listener_status()

    def start_snmp_trap(self, port: int | None = None) -> dict:
        if port:
            self.snmp_trap.port = port
        self.snmp_trap.start()
        self.bus.publish("source.started",
                         f"SNMP Trap 监听已启动：UDP {self.snmp_trap.bound_port}",
                         source="store", port=self.snmp_trap.bound_port)
        return self.listener_status()

    def stop_listeners(self) -> dict:
        self.syslog.stop()
        self.snmp_trap.stop()
        return self.listener_status()

    def listener_status(self) -> dict:
        return {
            "syslog": {"running": self.syslog.running, "port": self.syslog.bound_port,
                       "received": self.syslog.received},
            "snmp_trap": {"running": self.snmp_trap.running,
                          "port": self.snmp_trap.bound_port,
                          "received": self.snmp_trap.received},
        }

    def _on_network_event(self, event) -> None:
        """网络状态类事件 → 记录"哪个节点刚变化过"，供拓扑做增量高亮。"""
        if not event.topic.startswith(("link.", "device.", "syslog.", "snmp.")):
            return
        candidates = []
        # 事件源各有自己的字段名：syslog 用 device_host，SNMP 用 trap_source，
        # 控制器内部事件用 device/source —— 这里统一收口，别漏键。
        for key in ("device", "host", "device_host", "source", "trap_source",
                    "node", "peer", "title"):
            value = (event.data or {}).get(key)
            if value:
                candidates.append(str(value))
        if not candidates:
            return
        now = time.time()
        with self._lock:
            for name in self.graph.nodes:
                for candidate in candidates:
                    if candidate == name or name.endswith(candidate) or candidate in name:
                        self.node_flash[name] = now
                        break
        # 只保留最近 5 分钟的闪烁记录，避免字典无限增长
        with self._lock:
            cutoff = now - 300
            self.node_flash = {k: v for k, v in self.node_flash.items() if v >= cutoff}

    def flashed_nodes(self, within: float = 90.0) -> dict:
        """最近 ``within`` 秒内变化过的节点 → 变化时间。"""
        cutoff = time.time() - within
        with self._lock:
            return {k: v for k, v in self.node_flash.items() if v >= cutoff}

    def close(self) -> None:
        try:
            self._bus_unsub()
        except Exception:      # noqa: BLE001
            pass
        self.stop_listeners()

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
            "sources": self.listener_status(),
            "flash": len(self.flashed_nodes()),
            "uptime_s": int(time.time() - self.started_at),
            "last_topology_at": self.last_topology_at,
        }

    def snapshot(self, limit: int = 80) -> dict:
        """跨线程安全的只读快照（北向 REST 与页面刷新共用）。"""
        return {
            "summary": self.summary(),
            "topology": self.graph.to_dict(),
            "policies": [p.to_dict() for p in self.recent_policies(limit)],
            "intents": self.lifecycle.snapshot(limit),
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
