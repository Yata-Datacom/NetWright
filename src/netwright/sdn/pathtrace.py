"""pathtrace.py — 拓扑路径追踪（F）：源到目的经过哪些设备/链路。

只读分析，不下发任何命令：
  * 房间图（NetworkGraph）上做 BFS 最短路，返回节点序列与边序列；
  * 不可达返回 ``reachable=False`` 并给出原因，不猜"大概走这条"；
  * 支持排除节点（例如排除某台已隔离设备再算）。
"""
from __future__ import annotations

from collections import deque


def shortest_path(graph, src: str, dst: str, avoid: set[str] | None = None) -> dict:
    """BFS 最短路；返回 {reachable, nodes, edges, hops, reason}。"""
    avoid = set(avoid or ())
    if src in avoid or dst in avoid:
        return {"reachable": False, "nodes": [], "edges": [], "hops": 0,
                "reason": "起点或终点被排除"}
    if src not in graph.nodes or dst not in graph.nodes:
        return {"reachable": False, "nodes": [], "edges": [], "hops": 0,
                "reason": "起点或终点不在拓扑里"}
    if src == dst:
        return {"reachable": True, "nodes": [src], "edges": [], "hops": 0, "reason": ""}

    adjacency: dict[str, list[tuple[str, object]]] = {name: [] for name in graph.nodes}
    for edge in graph.edges:
        if edge.a in avoid or edge.b in avoid:
            continue
        adjacency.setdefault(edge.a, []).append((edge.b, edge))
        adjacency.setdefault(edge.b, []).append((edge.a, edge))

    prev: dict[str, tuple[str, object]] = {}
    seen = {src}
    queue = deque([src])
    while queue:
        current = queue.popleft()
        for neighbor, edge in adjacency.get(current, ()):
            if neighbor in seen:
                continue
            seen.add(neighbor)
            prev[neighbor] = (current, edge)
            if neighbor == dst:
                queue.clear()
                break
            queue.append(neighbor)

    if dst not in prev:
        return {"reachable": False, "nodes": [], "edges": [], "hops": 0,
                "reason": "拓扑中不存在连通路径"}
    nodes, edges = [dst], []
    cursor = dst
    while cursor != src:
        parent, edge = prev[cursor]
        edges.append(edge)
        nodes.append(parent)
        cursor = parent
    nodes.reverse()
    edges.reverse()
    return {"reachable": True, "nodes": nodes, "edges": edges,
            "hops": len(edges), "reason": ""}


def describe_path(result: dict) -> str:
    """把路径转成运维能读的一句话。"""
    if not result["reachable"]:
        return f"不可达：{result['reason']}"
    if result["hops"] == 0:
        return "起点与终点相同"
    return " → ".join(result["nodes"]) + f"（{result['hops']} 跳）"
