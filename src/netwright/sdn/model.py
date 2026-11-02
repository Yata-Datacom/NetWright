"""model.py — 控制器拓扑图模型（节点 / 端口 / 链路）。

与 ``lib/controller/topology.Topology`` 的分工：
  * ``Topology`` 是**解析产物**（LLDP 文本 → Link），只服务采集；
  * ``NetworkGraph`` 是**控制器状态**（可合并多来源、可序列化、可做邻居查询与统计），
    北向 REST、拓扑页面、策略编译都读它。

链路来源（``Edge.kind``）：
  ``lldp``   —— 设备实测邻居
  ``ledger`` —— 台账导入的对接关系（虚线，未经设备确认）
  ``manual`` —— 人工补录
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

_INTERFACE_NORM = (
    (re.compile(r"^(?:Gig|Gi|GE)(\d.*)$", re.I), r"GigabitEthernet\1"),
    (re.compile(r"^(?:Ten|Te)(\d.*)$", re.I), r"TenGigabitEthernet\1"),
    (re.compile(r"^(?:Eth|Et)(\d.*)$", re.I), r"Ethernet\1"),
)
_HIGH_RISK_WORDS = ("shutdown", "undo ", "no ", "reset", "delete", "clear ")


def normalize_interface(name: str) -> str:
    """接口名归一化：Gi/GE/Gig → GigabitEthernet，Te/Ten → TenGigabitEthernet。"""
    name = (name or "").strip()
    for pattern, repl in _INTERFACE_NORM:
        if pattern.match(name):
            return pattern.sub(repl, name)
    return name


@dataclass
class Node:
    """拓扑节点（一台被纳管的设备）。"""

    name: str
    vendor: str = ""
    kind: str = "switch"          # switch / router / host / controller / unknown
    managed: bool = False         # 是否在设备清单里（有凭据）
    attrs: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {"id": self.name, "name": self.name, "vendor": self.vendor,
                "kind": self.kind, "managed": self.managed, "attrs": self.attrs}


@dataclass
class Edge:
    """无向链路（a/b 两端 + 端口 + 来源）。"""

    a: str
    b: str
    a_port: str = ""
    b_port: str = ""
    kind: str = "lldp"

    def key(self) -> tuple:
        """去重键：同一对端口只保留一条边（与方向无关）。"""
        port_a = normalize_interface(self.a_port)
        port_b = normalize_interface(self.b_port)
        return tuple(sorted([(self.a, port_a), (self.b, port_b)]))

    def to_dict(self) -> dict:
        return {"a": self.a, "b": self.b, "a_port": self.a_port,
                "b_port": self.b_port, "kind": self.kind}


class NetworkGraph:
    """可合并的网络图。所有写操作在调用方线程内完成（GUI 主线程或采集线程二选一）。"""

    def __init__(self):
        self.nodes: dict[str, Node] = {}
        self.edges: list[Edge] = []
        self._edge_keys: set[tuple] = set()

    # ── 构建 ──
    def add_node(self, name: str, vendor: str = "", kind: str = "switch",
                 managed: bool = False, **attrs) -> Node:
        node = self.nodes.get(name)
        if node is None:
            node = Node(name=name, vendor=vendor, kind=kind, managed=managed, attrs=dict(attrs))
            self.nodes[name] = node
        else:
            node.vendor = node.vendor or vendor
            if kind and node.kind in ("", "unknown"):
                node.kind = kind
            node.managed = node.managed or managed
            node.attrs.update(attrs)
        return node

    def add_edge(self, a: str, b: str, a_port: str = "", b_port: str = "",
                 kind: str = "lldp") -> Edge | None:
        if not a or not b or a == b:
            return None
        edge = Edge(a=a, b=b, a_port=a_port, b_port=b_port, kind=kind)
        key = edge.key()
        if key in self._edge_keys:
            # 同一对端口再次出现：LLDP 实测可以"升级"台账链路（虚线 → 实线）
            if kind == "lldp":
                for existing in self.edges:
                    if existing.key() == key and existing.kind != "lldp":
                        existing.kind = "lldp"
                        break
            return None
        self._edge_keys.add(key)
        self.edges.append(edge)
        if a not in self.nodes:
            self.add_node(a)
        if b not in self.nodes:
            self.add_node(b)
        return edge

    def merge(self, other: NetworkGraph) -> NetworkGraph:
        for node in other.nodes.values():
            self.add_node(node.name, node.vendor, node.kind, node.managed, **node.attrs)
        for edge in other.edges:
            self.add_edge(edge.a, edge.b, edge.a_port, edge.b_port, edge.kind)
        return self

    # ── 查询 ──
    def neighbors(self, name: str) -> list[tuple[str, str]]:
        """返回 [(邻居名, 本端端口)]。"""
        out = []
        for edge in self.edges:
            if edge.a == name:
                out.append((edge.b, edge.a_port))
            elif edge.b == name:
                out.append((edge.a, edge.b_port))
        return sorted(out)

    def degree(self, name: str) -> int:
        return sum(1 for e in self.edges if e.a == name or e.b == name)

    def isolated(self) -> list[str]:
        return sorted(n for n in self.nodes if self.degree(n) == 0)

    def stats(self) -> dict:
        by_vendor: dict[str, int] = {}
        for node in self.nodes.values():
            key = node.vendor or "unknown"
            by_vendor[key] = by_vendor.get(key, 0) + 1
        by_kind: dict[str, int] = {}
        for edge in self.edges:
            by_kind[edge.kind] = by_kind.get(edge.kind, 0) + 1
        return {"nodes": len(self.nodes), "links": len(self.edges),
                "managed": sum(1 for n in self.nodes.values() if n.managed),
                "isolated": len(self.isolated()),
                "by_vendor": by_vendor, "by_source": by_kind}

    # ── 序列化 ──
    def to_dict(self) -> dict:
        return {"nodes": [n.to_dict() for n in sorted(self.nodes.values(), key=lambda n: n.name)],
                "links": [e.to_dict() for e in self.edges],
                "stats": self.stats()}

    @classmethod
    def from_dict(cls, data: dict) -> NetworkGraph:
        graph = cls()
        for raw in data.get("nodes", []):
            name = str(raw.get("name") or raw.get("id") or "")
            if not name:
                continue
            graph.add_node(name, str(raw.get("vendor") or ""),
                           str(raw.get("kind") or "switch"),
                           bool(raw.get("managed")), **(raw.get("attrs") or {}))
        for raw in data.get("links", []):
            graph.add_edge(str(raw.get("a") or ""), str(raw.get("b") or ""),
                           str(raw.get("a_port") or ""), str(raw.get("b_port") or ""),
                           str(raw.get("kind") or "lldp"))
        return graph

    # ── 与既有模块互转 ──
    @classmethod
    def from_topology(cls, topology, inventory=None) -> NetworkGraph:
        """把解析出的 ``Topology``（+ 设备清单）转成控制器图。"""
        graph = cls()
        if topology is not None:
            for name in sorted(getattr(topology, "nodes", set())):
                graph.add_node(name)
            for edge in getattr(topology, "undirected_edges", lambda: [])():
                graph.add_edge(edge[0], edge[2], edge[1], edge[3], "lldp")
        if inventory is not None:
            for device in getattr(inventory, "devices", []):
                name = getattr(device, "display_name", None) or device.host
                graph.add_node(name, getattr(device, "vendor", ""), "switch", True,
                               host=getattr(device, "host", ""),
                               protocol=getattr(device, "protocol", "ssh"))
        return graph

    def add_ledger_links(self, links) -> int:
        """台账链路入图（虚线来源）；返回新增条数。"""
        added = 0
        for link in links:
            if self.add_edge(str(link.device_host), str(link.peer_host),
                             str(link.local_intf), str(link.peer_intf), "ledger"):
                added += 1
        return added


def is_high_risk(command: str) -> bool:
    """命令风险粗判：含 shutdown/undo/no/reset 等破坏性动词。"""
    low = (command or "").lower()
    return any(word in low for word in _HIGH_RISK_WORDS)
