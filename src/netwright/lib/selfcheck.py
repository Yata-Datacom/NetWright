"""selfcheck.py — 环境自检：打包后"打不开/没模板/端口被占"的第一诊断入口。

设计：只读检查，不改任何东西；每项都给 ``hint``（怎么修），而不是只报失败。
CLI 入口见 ``tools/diagnose.py``。
"""
from __future__ import annotations

import os
import socket
import sys

from .. import __version__
from ..paths import data_dir, is_frozen, resource_dir


def _version() -> dict:
    return {"name": "版本", "ok": True, "detail": __version__,
            "hint": ""}


def _templates() -> dict:
    from . import generator

    try:
        templates = generator.list_builtin_templates()
    except Exception as exc:      # noqa: BLE001
        return {"name": "模板库", "ok": False, "detail": f"读取失败：{exc}",
                "hint": "确认 templates/ 目录与 library.json 存在（打包时 datas 要包含 templates）"}
    ok = len(templates) >= 100
    return {"name": "模板库", "ok": ok, "detail": f"{len(templates)} 个模板",
            "hint": "" if ok else "模板数量异常，可能是打包时漏了 templates/ 或 library.json 损坏"}


def _assets() -> dict:
    icon = os.path.join(resource_dir("assets"), "icon.ico")
    exists = os.path.exists(icon)
    return {"name": "图标资源", "ok": exists,
            "detail": icon if exists else "缺少 assets/icon.ico",
            "hint": "" if exists else "打包时 datas 需要包含 assets/"}


def _data_writable() -> dict:
    folder = data_dir()
    probe = os.path.join(folder, ".write_probe")
    try:
        with open(probe, "w", encoding="utf-8") as handle:
            handle.write("ok")
        os.remove(probe)
        return {"name": "数据目录可写", "ok": True, "detail": folder, "hint": ""}
    except OSError as exc:
        return {"name": "数据目录可写", "ok": False, "detail": f"{folder}：{exc}",
                "hint": "把程序放到有写权限的目录（不要放 Program Files）"}


def _backups_writable() -> dict:
    folder = os.path.join(data_dir(), "backups")
    try:
        os.makedirs(folder, exist_ok=True)
        probe = os.path.join(folder, ".write_probe")
        with open(probe, "w", encoding="utf-8") as handle:
            handle.write("ok")
        os.remove(probe)
        return {"name": "备份目录可写", "ok": True, "detail": folder, "hint": ""}
    except OSError as exc:
        return {"name": "备份目录可写", "ok": False, "detail": f"{folder}：{exc}",
                "hint": "检查磁盘空间/权限，或在设置页改备份目录"}


def port_free(port: int, host: str = "127.0.0.1") -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind((host, port))
            return True
        except OSError:
            return False


def _rest_port(settings: dict | None) -> dict:
    port = int((settings or {}).get("rest_port", 8899))
    free = port_free(port)
    return {"name": f"REST 端口 {port}", "ok": True if free else False,
            "detail": "空闲" if free else "已被占用（可能是本程序已在运行）",
            "hint": "" if free else f"关掉占用 {port} 的程序，或在设置页换端口"}


def _paramiko() -> dict:
    from . import HAS_SSH

    return {"name": "SSH 支持", "ok": True,
            "detail": "已安装 paramiko" if HAS_SSH else "未安装（仅 Telnet/CLI 可用）",
            "hint": "" if HAS_SSH else "需要 SSH 巡检时：pip install paramiko"}


def _python() -> dict:
    version = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    return {"name": "运行环境", "ok": True,
            "detail": f"Python {version}（{'打包版' if is_frozen() else '源码'}）",
            "hint": ""}


def run_checks(settings: dict | None = None) -> list[dict]:
    """跑全部检查；单项异常不影响其他项。"""
    checks = []
    for check in (_version, _python, _templates, _assets, _data_writable,
                  _backups_writable, _paramiko):
        try:
            checks.append(check())
        except Exception as exc:      # noqa: BLE001
            checks.append({"name": check.__name__.strip("_"), "ok": False,
                           "detail": f"{type(exc).__name__}: {exc}",
                           "hint": "这是程序缺陷，请把这段输出反馈给维护者"})
    try:
        checks.append(_rest_port(settings))
    except Exception as exc:          # noqa: BLE001
        checks.append({"name": "REST 端口", "ok": False, "detail": str(exc),
                       "hint": "检查设置里的 rest_port 是否为整数"})
    return checks


def summarize(checks: list[dict]) -> tuple[bool, str]:
    failed = [c for c in checks if not c["ok"]]
    if not failed:
        return True, f"全部 {len(checks)} 项通过"
    return False, f"{len(failed)}/{len(checks)} 项不通过：" + "、".join(c["name"] for c in failed)
