"""tasks.py — 异步任务（G）：长任务返回 task_id，REST 可轮询进度。

为什么需要：巡检/备份/批量下发动辄几十秒，HTTP 直接等会超时，也没法显示进度。
这里用线程池 + 内存表，任务状态只保留最近 200 条（重启即清空，不持久化——
真正需要审计的动作已经写进 audit 日志，两套东西不要混）。
"""
from __future__ import annotations

import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor

MAX_TASKS = 200


class TaskManager:
    def __init__(self, workers: int = 4, max_tasks: int = MAX_TASKS):
        self._pool = ThreadPoolExecutor(max_workers=max(1, workers),
                                        thread_name_prefix="task")
        self._lock = threading.Lock()
        self._tasks: dict[str, dict] = {}
        self._order: list[str] = []
        self._max = max_tasks

    def submit(self, name: str, fn, *args, **kwargs) -> str:
        task_id = uuid.uuid4().hex[:16]
        record = {"id": task_id, "name": name, "state": "pending",
                  "started": None, "finished": None, "result": None, "error": ""}
        with self._lock:
            self._tasks[task_id] = record
            self._order.append(task_id)
            self._trim()
        self._pool.submit(self._run, task_id, fn, args, kwargs)
        return task_id

    def _run(self, task_id: str, fn, args: tuple, kwargs: dict) -> None:
        with self._lock:
            record = self._tasks.get(task_id)
            if record is None:
                return
            record["state"] = "running"
            record["started"] = time.time()
        try:
            result = fn(*args, **kwargs)
            with self._lock:
                record["state"] = "done"
                record["result"] = result
        except Exception as exc:      # noqa: BLE001  任务失败要带原因返回给调用方
            with self._lock:
                record["state"] = "failed"
                record["error"] = f"{type(exc).__name__}: {exc}"
        finally:
            with self._lock:
                record["finished"] = time.time()

    def _trim(self) -> None:
        while len(self._order) > self._max:
            oldest = self._order.pop(0)
            self._tasks.pop(oldest, None)

    def get(self, task_id: str) -> dict | None:
        with self._lock:
            record = self._tasks.get(task_id)
            return dict(record) if record else None

    def list(self, limit: int = 20) -> list[dict]:
        with self._lock:
            ids = self._order[-limit:]
            return [dict(self._tasks[i]) for i in reversed(ids) if i in self._tasks]

    def wait(self, task_id: str, timeout: float = 30.0) -> dict | None:
        """测试/脚本用：轮询到完成或超时。"""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            record = self.get(task_id)
            if record and record["state"] in ("done", "failed"):
                return record
            time.sleep(0.02)
        return self.get(task_id)

    def shutdown(self) -> None:
        self._pool.shutdown(wait=False, cancel_futures=True)
