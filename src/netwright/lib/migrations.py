"""migrations.py — 配置/数据结构版本与迁移（v4.0 的"可升级"承诺）。

为什么需要：v4 之前设置文件是"缺键就取默认"，看起来省事，但一旦某个版本改了
键名或含义，老用户的文件会半新半旧、行为不可预测。v4 起引入 ``schema_version``：

  * 启动时读取版本，落后就按顺序迁移（只增不改语义）；
  * 迁移前**先备份** ``settings.json`` 为 ``.bak``，失败可回滚；
  * 迁移只做"补齐+改名"，绝不删除用户不认识的键（未来版本写入的键要保留）。
"""
from __future__ import annotations

import os
import shutil
import time

SCHEMA_VERSION = 4

# v4 需要存在、且旧版本可能缺失的键 → 默认值
_V4_KEYS = {
    "schema_version": SCHEMA_VERSION,
    "drift_daily": False,
    "drift_hours": 24,
    "api_tokens": {},
    "backup_dir": "",
    "backup_keep": 30,
    "log_level": "WARNING",
    "syslog_port": 5140,
    "trap_port": 1162,
    "rest_port": 8899,
    "auto_refresh": True,
}

# 历史键名 → 新键名（只加不改，避免老文件行为漂移）
_RENAMES = {"theme": "theme_mode"}


def current_version(settings: dict) -> int:
    try:
        return int(settings.get("schema_version", 3))
    except (TypeError, ValueError):
        return 3


def migrate(settings: dict, base_dir: str | None = None) -> dict:
    """把 settings 就地迁移到 ``SCHEMA_VERSION``；返回迁移报告。

    返回：``{"from": 3, "to": 4, "applied": [...], "backup": "path|''"}``
    """
    start = current_version(settings)
    report = {"from": start, "to": start, "applied": [], "backup": ""}
    if start >= SCHEMA_VERSION:
        report["to"] = start
        return report

    if base_dir:
        source = os.path.join(base_dir, "netwright_settings.json")
        if os.path.exists(source):
            stamp = time.strftime("%Y%m%d-%H%M%S")
            backup = f"{source}.v{start}.{stamp}.bak"
            try:
                shutil.copy2(source, backup)
                report["backup"] = backup
            except OSError:
                report["backup"] = ""

    for old, new in _RENAMES.items():
        if old in settings and new not in settings:
            settings[new] = settings.pop(old)
            report["applied"].append(f"rename {old}->{new}")

    for key, default in _V4_KEYS.items():
        if key not in settings:
            settings[key] = default() if callable(default) else default
            report["applied"].append(f"add {key}")

    settings["schema_version"] = SCHEMA_VERSION
    report["to"] = SCHEMA_VERSION
    report["applied"].append(f"schema_version {start}->{SCHEMA_VERSION}")
    return report


def ensure_current(settings: dict, base_dir: str | None = None,
                   save=None) -> dict:
    """启动时调用：迁移并落盘（``save`` 传入 save_settings 以免循环依赖）。"""
    report = migrate(settings, base_dir)
    if report["applied"] and save is not None and base_dir:
        try:
            save(settings, base_dir)
        except Exception:      # noqa: BLE001  迁移失败不该阻止程序启动
            pass
    return report
