"""B/F/G 三个控制器扩展的测试：定时漂移、路径追踪、异步任务。"""
from __future__ import annotations

import os
import sys


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from netwright.sdn.model import NetworkGraph
from netwright.sdn.pathtrace import describe_path, shortest_path
from netwright.sdn.schedule import IntervalJob, drift_scan
from netwright.sdn.tasks import TaskManager


# ── F 路径追踪 ──
def _graph() -> NetworkGraph:
    graph = NetworkGraph()
    graph.add_edge("core", "sw1", "Gi0/1", "Gi0/2")
    graph.add_edge("sw1", "sw2", "Gi0/3", "Gi0/1")
    graph.add_edge("core", "sw2", "Gi0/4", "Gi0/2")
    return graph


def test_path_prefers_shortest_hops():
    result = shortest_path(_graph(), "core", "sw2")
    assert result["reachable"]
    assert result["hops"] == 1
    assert result["nodes"] == ["core", "sw2"]


def test_path_through_two_hops():
    remove = shortest_path(_graph(), "sw1", "sw2")
    assert remove["nodes"] == ["sw1", "sw2"]
    # 排除直连后必须绕行
    bypass = shortest_path(_graph(), "sw1", "sw2", avoid={"sw1", "sw2"})
    assert not bypass["reachable"]


def test_path_unreachable_and_missing_nodes():
    graph = NetworkGraph()
    graph.add_node("a")
    assert not shortest_path(graph, "a", "b")["reachable"]
    assert not shortest_path(graph, "a", "a", avoid={"a"})["reachable"]


def test_describe_path_is_human_readable():
    assert describe_path(shortest_path(_graph(), "core", "sw2")).startswith("core → sw2")


# ── B 定时漂移 ──
class FakeClock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now

    def advance(self, seconds):
        self.now += seconds


def test_interval_job_runs_only_when_due():
    clock = FakeClock()
    calls = []
    job = IntervalJob("drift", lambda: calls.append(1) or {"changed": False},
                      interval=60, clock=clock)
    assert job.run()["ran"] is True
    assert job.run()["ran"] is False, "未到期不应重复执行"
    clock.advance(61)
    assert job.run()["ran"] is True
    assert len(calls) == 2


def test_interval_job_swallows_and_records_error():
    clock = FakeClock()
    def boom():
        raise RuntimeError("设备超时")
    job = IntervalJob("drift", boom, interval=10, clock=clock)
    result = job.run()
    assert result["ran"] and not result["ok"]
    assert "设备超时" in job.last_error
    assert job.run()["ran"] is False, "失败后仍按间隔等待"


class _Device:
    def __init__(self, host):
        self.host = host
        self.hostname = host
        self.display_name = host


class _Inventory:
    def __init__(self, devices):
        self.devices = devices


class _Store:
    def __init__(self, devices, drift_hosts=()):
        self.inventory = _Inventory(devices)
        self._drift = set(drift_hosts)

    def compare_live(self, device):
        if device.host == "boom":
            raise RuntimeError("连接失败")
        return {"changed": device.host in self._drift,
                "diff": f"--- {device.host}\n+ new line"}


def test_drift_scan_reports_only_changed_and_errors():
    store = _Store([_Device("sw1"), _Device("sw2"), _Device("boom")], drift_hosts={"sw2"})
    result = drift_scan(store)
    assert result["scanned"] == 3
    assert [d["device"] for d in result["drifted"]] == ["sw2"]
    assert result["errors"][0]["device"] == "boom"


# ── G 异步任务 ──
def test_task_manager_completes_and_returns_result():
    manager = TaskManager(workers=2)
    try:
        task_id = manager.submit("slow", lambda value: value * 2, 21)
        record = manager.wait(task_id, timeout=5)
        assert record["state"] == "done" and record["result"] == 42
        assert manager.get(task_id)["name"] == "slow"
    finally:
        manager.shutdown()


def test_task_manager_captures_failure():
    manager = TaskManager(workers=1)
    try:
        def boom():
            raise ValueError("坏输入")
        record = manager.wait(manager.submit("bad", boom), timeout=5)
        assert record["state"] == "failed"
        assert "坏输入" in record["error"]
    finally:
        manager.shutdown()


def test_task_manager_trims_history():
    manager = TaskManager(workers=1, max_tasks=5)
    try:
        ids = [manager.submit("t", lambda: None) for _ in range(8)]
        for task_id in ids:
            manager.wait(task_id, timeout=3)
        assert len(manager.list(limit=50)) == 5
        assert manager.get(ids[0]) is None
    finally:
        manager.shutdown()
