"""history.py — 巡检/盘点结果持久化（JSONL），供趋势可视化。

文件：netwright_history_inspection.jsonl（每行一条摘要）。
"""
from __future__ import annotations

import json
import os
import sys
import threading
from datetime import datetime

_lock = threading.Lock()


def _base_dir() -> str:
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


def history_path(kind: str) -> str:
    return os.path.join(_base_dir(), f"netwright_history_{kind}.jsonl")


def append_history(kind: str, entry: dict) -> None:
    entry = {"time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), **entry}
    try:
        with _lock:
            with open(history_path(kind), "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except OSError:
        pass


def load_history(kind: str, limit: int = 60) -> list[dict]:
    try:
        with _lock:
            with open(history_path(kind), "r", encoding="utf-8") as f:
                lines = f.readlines()
    except OSError:
        return []
    out = []
    for line in lines[-limit:]:
        try:
            out.append(json.loads(line))
        except ValueError:
            continue
    return out


def extract_series(entries: list[dict], metric: str) -> list[tuple[str, float]]:
    """从历史条目提取折线数据 [(时间短标签, 数值)]。"""
    series = []
    for e in entries:
        label = e.get("time", "")[-8:]     # HH:MM:SS
        value = e.get(metric)
        if value is None:
            continue
        try:
            series.append((label, float(value)))
        except (TypeError, ValueError):
            continue
    return series


def save_snapshot(kind: str, data: dict) -> bool:
    path = os.path.join(_base_dir(), f"netwright_snapshot_{kind}.json")
    try:
        with _lock:
            with open(path, "w", encoding="utf-8") as f:
                json.dump({"time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                           **data}, f, ensure_ascii=False, indent=2)
        return True
    except OSError:
        return False


def load_snapshot(kind: str) -> dict:
    path = os.path.join(_base_dir(), f"netwright_snapshot_{kind}.json")
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}
