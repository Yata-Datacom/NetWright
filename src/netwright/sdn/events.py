"""events.py — 控制器事件总线（线程安全，进程内）。

设计取舍：
  * 控制器在 GUI 里以线程跑采集/下发，事件必须能从任意线程发布；
  * 订阅者（页面）只在 Tk 主线程渲染，因此总线本身不做 UI 调度，
    由页面用 ``app.after`` 自行切回主线程；
  * 环形缓冲保留最近 N 条，供北向 REST 与「事件」页回放；
  * 订阅回调异常一律吞掉并记进 ``dropped``，绝不因为一个坏订阅者拖垮采集线程。

主题（topic）约定：``<资源>.<动作>``，例如 ``device.up`` / ``link.down`` /
``topology.changed`` / ``policy.compiled`` / ``southbound.error``。
"""
from __future__ import annotations

import threading
import time
from collections import deque
from dataclasses import dataclass, field
from itertools import count

SEVERITIES = ("info", "warning", "critical")

SEVERITY_RANK = {"info": 0, "warning": 1, "critical": 2}


@dataclass(frozen=True)
class Event:
    """一条控制器事件（不可变，便于跨线程传递与快照）。"""

    topic: str
    message: str
    severity: str = "info"
    source: str = ""
    data: dict = field(default_factory=dict)
    ts: float = field(default_factory=time.time)
    id: int = 0

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "topic": self.topic,
            "severity": self.severity,
            "message": self.message,
            "source": self.source,
            "data": self.data,
            "ts": self.ts,
            "time": time.strftime("%H:%M:%S", time.localtime(self.ts)),
        }


class EventBus:
    """进程内发布/订阅总线 + 环形历史。"""

    def __init__(self, history: int = 500):
        self._lock = threading.RLock()
        self._history: deque[Event] = deque(maxlen=max(10, history))
        self._subs: list[tuple[str, object]] = []   # (topic_prefix, callback)
        self._ids = count(1)
        self.dropped = 0

    # ── 订阅 ──
    def subscribe(self, callback, topic_prefix: str = ""):
        """订阅；``topic_prefix=""`` 表示全部。返回取消订阅函数。"""
        entry = (topic_prefix or "", callback)
        with self._lock:
            self._subs.append(entry)

        def unsubscribe():
            with self._lock:
                if entry in self._subs:
                    self._subs.remove(entry)

        return unsubscribe

    # ── 发布 ──
    def publish(self, topic: str, message: str, severity: str = "info",
                source: str = "", **data) -> Event:
        if severity not in SEVERITIES:
            severity = "info"
        with self._lock:
            ev = Event(topic=topic, message=message, severity=severity,
                       source=source, data=dict(data), id=next(self._ids))
            self._history.append(ev)
            targets = [cb for prefix, cb in self._subs if not prefix or topic.startswith(prefix)]
        for cb in targets:
            try:
                cb(ev)
            except Exception:      # noqa: BLE001  单个订阅者异常不影响发布方
                with self._lock:
                    self.dropped += 1
        return ev

    # ── 查询 ──
    def snapshot(self, limit: int = 100, min_severity: str | None = None,
                 topic: str = "") -> list[Event]:
        floor = SEVERITY_RANK.get(min_severity or "", -1)
        with self._lock:
            items = list(self._history)
        out = [e for e in items
               if (not topic or e.topic.startswith(topic))
               and SEVERITY_RANK.get(e.severity, 0) >= floor]
        return out[-max(1, limit):][::-1]      # 最新在前

    def counts(self) -> dict:
        with self._lock:
            items = list(self._history)
        out = {"total": len(items)}
        for sev in SEVERITIES:
            out[sev] = sum(1 for e in items if e.severity == sev)
        return out

    def clear(self):
        with self._lock:
            self._history.clear()

    def __len__(self) -> int:
        return len(self._history)
