"""schedule.py — 定时漂移巡检（B）：到点扫描配置漂移，只报变化。

不引入第三方调度库：一个可注入时钟的 ``IntervalJob`` 就够用，也方便测试
（把时钟换成假对象，立刻触发下一次到期）。

注意：本模块**不做网络重试**，失败就记录并等下一轮；网络设备偶发超时
不应该让调度器堆积任务。
"""
from __future__ import annotations

import time

DEFAULT_DRIFT_INTERVAL = 24 * 3600


class IntervalJob:
    def __init__(self, name: str, fn, interval: float = DEFAULT_DRIFT_INTERVAL,
                 clock=time.monotonic):
        self.name = name
        self.fn = fn
        self.interval = max(1.0, float(interval))
        self.clock = clock
        self.last_run: float | None = None
        self.last_result = None
        self.last_error = ""

    def due(self, now: float | None = None) -> bool:
        current = self.clock() if now is None else now
        return self.last_run is None or (current - self.last_run) >= self.interval

    def run(self, now: float | None = None) -> dict:
        """到期则执行一次；未到期返回 {"ran": False}。异常被捕获并记录。"""
        if not self.due(now):
            return {"ran": False, "next_in": round(self.interval
                                                   - (self.clock() - self.last_run), 1)}
        self.last_run = self.clock() if now is None else now
        try:
            self.last_result = self.fn()
            self.last_error = ""
            return {"ran": True, "ok": True, "result": self.last_result}
        except Exception as exc:      # noqa: BLE001  单轮失败不中断调度
            self.last_error = f"{type(exc).__name__}: {exc}"
            return {"ran": True, "ok": False, "error": self.last_error}

    def next_due_in(self) -> float:
        if self.last_run is None:
            return 0.0
        return max(0.0, self.interval - (self.clock() - self.last_run))


def drift_scan(store, device_hosts: list[str] | None = None) -> dict:
    """对全部设备做一次"与现网对比"，只返回有漂移的设备。"""
    devices = list(store.inventory.devices)
    if device_hosts:
        wanted = set(device_hosts)
        devices = [d for d in devices if d.host in wanted]
    drifted = []
    errors = []
    for device in devices:
        try:
            result = store.compare_live(device)
        except Exception as exc:      # noqa: BLE001  单台失败不影响整轮
            errors.append({"device": device.host, "error": f"{type(exc).__name__}: {exc}"})
            continue
        if result.get("changed"):
            drifted.append({"device": device.host, "hostname": getattr(device, "display_name", ""),
                            "diff": result.get("diff", "")[:400]})
    return {"scanned": len(devices), "drifted": drifted, "errors": errors,
            "changed": bool(drifted)}
