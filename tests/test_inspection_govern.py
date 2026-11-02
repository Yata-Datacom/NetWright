"""R7 巡检治理契约测试：可取消（2 秒收尾）/ 并发可配 / 取消后可再次开始。"""

from __future__ import annotations

import os
import sys
import threading
import time
from types import SimpleNamespace

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)


import netwright.lib.inspector as insp
from netwright.lib.inspector import CommandResult, DeviceResult, run_batch

SCHEME = {"huawei": [f"cmd{i}" for i in range(1, 6)]}      # 5 条命令


def _devices(n: int) -> list:
    return [SimpleNamespace(host=f"192.0.2.{i}", vendor="huawei",
                            display_name=f"D{i:02d}") for i in range(1, n + 1)]


def _slow_run_device(release: threading.Event, gate_first: float = 0.0):
    """可编程的慢设备：阻塞到 release；返回一个干净的 OK 结果。"""
    def fake(device, scheme_commands, timeout=15.0, port=None):
        release.wait(timeout=5)
        cmds = [CommandResult(title="巡检", command=c, output="ok")
                for c in scheme_commands]
        return DeviceResult(host=device.host, vendor=device.vendor,
                            status="OK", commands=cmds, cost_ms=1)
    return fake


def _staggered_run_device(delay: float = 0.05):
    """每台耗时 delay 秒后完成：够进度上报几轮，也够在半路取消。"""
    def fake(device, scheme_commands, timeout=15.0, port=None):
        end = time.perf_counter() + delay
        while time.perf_counter() < end:
            time.sleep(0.01)
        cmds = [CommandResult(title="巡检", command=c, output="ok")
                for c in scheme_commands]
        return DeviceResult(host=device.host, vendor=device.vendor,
                            status="OK", commands=cmds, cost_ms=1)
    return fake


def test_cancel_finishes_within_two_seconds(monkeypatch):
    """并发 20 台 × 5 条命令的 mock 场景：取消后 2 秒内线程池收尾。"""
    release = threading.Event()
    monkeypatch.setattr(insp, "run_device", _slow_run_device(release))
    cancel = threading.Event()
    timer = threading.Timer(0.4, cancel.set)
    timer.start()
    try:
        started = time.perf_counter()
        results, skipped = run_batch(_devices(20), SCHEME, workers=5,
                                     cancel=cancel.is_set)
        elapsed = time.perf_counter() - started
    finally:
        release.set()
        timer.cancel()
    assert elapsed < 2.0, f"取消后 {elapsed:.2f}s 才收尾（要求 < 2s）"
    assert len(results) < 20, "取消后不应再等全部设备"
    assert any("已取消" in s for s in skipped), "跳过列表要注明取消"
    assert any("未巡检" in s for s in skipped)


def test_cancel_before_start_returns_immediately(monkeypatch):
    release = threading.Event()
    monkeypatch.setattr(insp, "run_device", _slow_run_device(release))
    cancel = threading.Event()
    cancel.set()                                  # 一开始就要求取消
    started = time.perf_counter()
    results, skipped = run_batch(_devices(20), SCHEME, workers=5,
                                 cancel=cancel.is_set)
    elapsed = time.perf_counter() - started
    release.set()
    assert elapsed < 2.0
    assert results == []
    assert any("已取消" in s for s in skipped)


def test_no_cancel_runs_everything(monkeypatch):
    """回归：不取消时 20 台全部完成（取消探针是可选参数）。"""
    release = threading.Event()
    release.set()
    monkeypatch.setattr(insp, "run_device", _slow_run_device(release))
    results, skipped = run_batch(_devices(20), SCHEME, workers=5)
    assert len(results) == 20
    assert not any("已取消" in s for s in skipped)


def test_progress_stops_after_cancel(monkeypatch):
    """取消后不再上报进度：progress 的最后一条 == 实际完成台数（< 总数）。"""
    monkeypatch.setattr(insp, "run_device", _staggered_run_device(0.05))
    cancel = threading.Event()
    seen = []
    timer = threading.Timer(0.15, cancel.set)
    timer.start()
    try:
        results, skipped = run_batch(_devices(20), SCHEME, workers=4,
                                     progress=lambda d, t: seen.append((d, t)),
                                     cancel=cancel.is_set)
    finally:
        timer.cancel()
    assert seen, "取消前应有进度上报"
    if any("已取消" in s for s in skipped):
        assert len(results) < 20
        assert seen[-1][0] == len(results), \
            "进度应停在取消时已完成的台数（之后不再上报）"
