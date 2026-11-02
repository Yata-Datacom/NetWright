"""性能回归：力导向布局在大图上必须有响应（不能"点了没反应"）。"""
from __future__ import annotations

import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from netwright.pages.topology import _layout_force
from netwright.sdn.model import NetworkGraph


def _star_graph(nodes: int) -> NetworkGraph:
    graph = NetworkGraph()
    for index in range(1, nodes):
        graph.add_edge("core", f"sw-{index}", f"Gi0/{index}", "Gi0/1")
    return graph


def test_layout_force_scales_to_200_nodes():
    """200 节点：迭代次数自适应后应在 5 秒内出图（慢机器也够用）。"""
    graph = _star_graph(200)
    started = time.monotonic()
    positions = _layout_force(graph)
    elapsed = time.monotonic() - started
    assert len(positions) == 200
    assert elapsed < 5.0, f"200 节点布局耗时 {elapsed:.1f}s，超出预算"


def test_layout_force_small_graph_keeps_quality():
    """小图仍走完整迭代（结果稳定、可复现）。"""
    graph = _star_graph(6)
    first = _layout_force(graph)
    second = _layout_force(graph)
    assert first == second, "同图两次布局结果应完全一致（确定性）"
