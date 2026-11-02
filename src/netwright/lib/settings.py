"""settings.py — 应用设置持久化（netwright_settings.json，exe/仓库根目录）。"""
from __future__ import annotations

import json
import os

FILENAME = "netwright_settings.json"
LEGACY_FILENAME = "netforge_settings.json"    # 3.4 更名前的旧文件，首次启动自动迁移
DEFAULTS = {
    "theme_mode": "dark",
    "theme_hue": "蓝",
    "rest_port": 8899,
    "last_page": "dashboard",
    "auto_refresh": True,
    "nav_collapsed": False,
}


def settings_path(base_dir: str) -> str:
    return os.path.join(base_dir, FILENAME)


def load_settings(base_dir: str) -> dict:
    path = settings_path(base_dir)
    if not os.path.exists(path):
        legacy = os.path.join(base_dir, LEGACY_FILENAME)
        if os.path.isfile(legacy):
            path = legacy
    raw: dict = {}
    try:
        with open(path, encoding="utf-8") as f:
            loaded = json.load(f)
        if isinstance(loaded, dict):
            raw = loaded
    except (OSError, ValueError):
        raw = {}

    data = dict(DEFAULTS)
    # 旧版本遗留的 "theme": "深空蓝 · 暗" → 能推出明暗就迁到 theme_mode
    legacy_theme = str(raw.get("theme") or "")
    if legacy_theme and "theme_mode" not in raw:
        data["theme_mode"] = "light" if ("浅" in legacy_theme or "亮" in legacy_theme) else "dark"
    data.update({k: v for k, v in raw.items() if k != "theme"})
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
