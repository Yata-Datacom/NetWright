"""deploy.py — 部署流水线：意图 → Dry-Run 计划 →（确认）→ SSH 下发 → 审计日志。"""
from __future__ import annotations

import json
import os
import sys
import threading
from datetime import datetime

from . import intents as intents_mod

AUDIT_FILE = "netforge_audit.log"
_lock = threading.Lock()


def _base_dir() -> str:
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def audit_path() -> str:
    return os.path.join(_base_dir(), AUDIT_FILE)


def _audit(entry: dict):
    entry = {"time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), **entry}
    try:
        with _lock:
            with open(audit_path(), "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except OSError:
        pass


def audit_tail(limit: int = 100) -> list[dict]:
    try:
        with _lock:
            with open(audit_path(), "r", encoding="utf-8") as f:
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


def dry_run(intent_key: str, intent: dict, devices: list) -> dict:
    """Dry-Run：把意图渲染成每台设备的命令计划，绝不连设备。

    :param devices: inventory.Device 列表
    :return: {"intent_key", "plan": [{"device", "vendor", "commands"}], "skipped": [...]}
    """
    plan, skipped = [], []
    for dev in devices:
        try:
            cmds = intents_mod.render_intent(intent_key, intent, dev.vendor)
        except ValueError as e:
            # 参数校验失败 → 全局报错；厂商不支持 → 该设备跳过
            if "暂不支持厂商" in str(e):
                skipped.append(f"{dev.display_name}: {e}")
                continue
            raise
        plan.append({"device": dev.display_name, "host": dev.host,
                     "vendor": dev.vendor, "commands": cmds})
    return {"intent_key": intent_key, "plan": plan, "skipped": skipped}


def apply(intent_key: str, intent: dict, devices: list, timeout: float = 15.0,
          progress=None) -> dict:
    """真实下发：逐台 SSH 执行意图命令，逐条记录审计。调用方自行放线程。

    :return: {"results": [{"device","status","outputs","error"}], "skipped"}
    """
    plan = dry_run(intent_key, intent, devices)
    results = []
    done = 0
    from ..ssh_client import run_commands
    for entry in plan["plan"]:
        dev = next((d for d in devices if d.display_name == entry["device"]), None)
        if dev is None:
            continue
        out = {"device": entry["device"], "status": "OK", "outputs": [], "error": ""}
        try:
            for title, cmd, output, err in run_commands(dev, entry["commands"], timeout=timeout):
                out["outputs"].append({"command": cmd, "output": output[:2000],
                                       "error": err})
                if err:
                    out["status"] = "WARNING"
        except Exception as e:
            out["status"], out["error"] = "FAILED", str(e)
        results.append(out)
        _audit({"action": "intent.apply", "intent": intent_key,
                "params": {k: v for k, v in intent.items() if "password" not in k.lower()},
                "device": entry["device"], "vendor": entry["vendor"],
                "commands": entry["commands"], "status": out["status"]})
        done += 1
        if progress:
            progress(done, len(plan["plan"]))
    for s in plan["skipped"]:
        _audit({"action": "intent.apply", "intent": intent_key, "skipped": s, "status": "SKIPPED"})
    return {"results": results, "skipped": plan["skipped"]}


def discover_topology(devices: list, timeout: float = 12.0, progress=None) -> "object":
    """SSH 采集各设备 LLDP/CDP 邻居 → 构建拓扑（阻塞；调用方放线程）。

    不支持拓扑发现命令的厂商（linux/generic）自动跳过。
    """
    from .. import ssh_client
    from . import topology as topo_mod

    outputs = []
    total = len(devices)
    done = 0
    for dev in devices:
        cmds = topo_mod.DISCOVERY_COMMANDS.get(dev.vendor)
        if not cmds:
            done += 1
            continue
        try:
            parts = []
            for title, cmd, output, err in ssh_client.run_commands(dev, cmds, timeout=timeout):
                parts.append(output)
            outputs.append((dev.display_name, dev.vendor, "\n".join(parts)))
        except Exception:
            pass  # 单台失败不影响整体拓扑
        done += 1
        if progress:
            progress(done, total)
    return topo_mod.build_topology(outputs)
