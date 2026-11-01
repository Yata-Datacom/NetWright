"""settings.py — 应用设置持久化（netwright_settings.json，exe/仓库根目录）。"""
from __future__ import annotations

import json
import os

FILENAME = "netwright_settings.json"
DEFAULTS = {"theme": "深空蓝 · 暗", "rest_port": 8899, "last_page": "dashboard"}


def settings_path(base_dir: str) -> str:
    return os.path.join(base_dir, FILENAME)


def load_settings(base_dir: str) -> dict:
    data = dict(DEFAULTS)
    try:
        with open(settings_path(base_dir), "r", encoding="utf-8") as f:
            data.update(json.load(f))
    except (OSError, ValueError):
        pass
    return data


def save_settings(settings: dict, base_dir: str) -> bool:
    path = settings_path(base_dir)
    tmp = path + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(settings, f, ensure_ascii=False, indent=2)
        os.replace(tmp, path)
        return True
    except OSError:
        return False
