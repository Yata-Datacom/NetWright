"""timeline.py — 把"事件 + 配置快照 + 意图运行"合成一条按时间排序的排障时间线。

为什么需要它：排障时的问题是"**那会儿发生了什么**"，而三类信息平时散在三个页面：
  * 事件流：链路中断、登录失败、配置漂移；
  * 配置快照：什么时候备份过、配置何时变化；
  * 意图运行档案：谁在什么时候对哪台设备下发了什么、结果如何。

本模块只做聚合与排序，不产生新状态；数据量上限由调用方控制（默认 120 条）。
"""
from __future__ import annotations

import time
from dataclasses import dataclass

KIND_LABEL = {"event": "事件", "backup": "配置快照", "intent": "意图运行"}
SEVERITY_RANK = {"info": 0, "warning": 1, "critical": 2}


@dataclass
class TimelineItem:
    ts: float
    kind: str
    device: str
    title: str
    detail: str = ""
    severity: str = "info"

    @property
    def time_text(self) -> str:
        return time.strftime("%m-%d %H:%M:%S", time.localtime(self.ts))

    @property
    def kind_label(self) -> str:
        return KIND_LABEL.get(self.kind, self.kind)

    def to_dict(self) -> dict:
        return {"ts": self.ts, "time": self.time_text, "kind": self.kind,
                "kind_label": self.kind_label,
                "device": self.device, "title": self.title,
                "detail": self.detail, "severity": self.severity}


def build_timeline(store, limit: int = 120,
                   max_backup_devices: int = 30,
                   backups_per_device: int = 10) -> list[TimelineItem]:
    """聚合三类来源，按时间倒序返回。"""
    limit = max(1, int(limit))
    items: list[TimelineItem] = []

    # 1) 事件流
    for event in store.bus.snapshot(limit=limit * 2):
        items.append(TimelineItem(
            ts=event.ts, kind="event", device=str((event.data or {}).get("device", "")),
            title=event.message, detail=event.topic, severity=event.severity))

    # 2) 配置快照（每台设备只取最近几份，避免大目录把时间线淹没）
    backups = getattr(store, "backups", None)
    if backups is not None:
        for device in backups.devices()[:max_backup_devices]:
            for entry in backups.history(device)[:backups_per_device]:
                items.append(TimelineItem(
                    ts=entry.ts, kind="backup", device=device,
                    title=f"配置快照 {entry.filename}",
                    detail=f"{entry.size // 1024} KB", severity="info"))

    # 3) 意图运行档案
    lifecycle = getattr(store, "lifecycle", None)
    if lifecycle is not None:
        for run in lifecycle.recent(limit):
            severity = "warning" if run.state in ("failed", "rollback_blocked") else "info"
            items.append(TimelineItem(
                ts=run.updated, kind="intent", device=run.device,
                title=f"{getattr(run.policy, 'intent_title', '')} · {run.state}",
                detail=f"档案 {run.id}", severity=severity))

    items.sort(key=lambda i: i.ts, reverse=True)
    return items[:limit]
