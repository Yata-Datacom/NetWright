"""policy.py — 意图 → 策略编译（控制器的"北向意图、南向命令"转换层）。

一层薄但关键的抽象：
  * 意图（Intent）是**人话**：VLAN 部署、Trunk 放行、OSPF 邻居……
  * 策略（Policy）是**可审计、可预演、可比较**的产物：每台设备一串命令 + 风险等级；
  * 下发（Deploy）只消费 Policy，不再碰意图，于是 dry-run / 审批 / 回滚都能复用同一份产物。

与 ``lib/controller/deploy.py`` 的分工：deploy 负责"连设备执行"，
本模块只负责"把意图编译成策略"，不产生任何网络副作用。
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from itertools import count

from ..lib.controller import intents as intents_mod
from .model import is_high_risk
from .openflow_plan import flows_for

RISK_ORDER = {"low": 0, "high": 1}

# 模块级 id 计数器：PolicyCompiler 可能被多处短生命周期地创建
# （lifecycle.create 每次都新建一个），实例级计数器会让不同批次的策略
# 撞 id，后一批的运行档案覆盖前一批（self.runs[policy.id]）。
_IDS = count(1)


def next_policy_id(prefix: str = "pol") -> str:
    """全局唯一策略 id：pol-0001 / tpl-0002 …（进程内单调）。"""
    return f"{prefix}-{next(_IDS):04d}"


@dataclass(frozen=True)
class Policy:
    """一条针对单台设备的编译结果。"""

    id: str
    intent_key: str
    intent_title: str
    params: dict
    device: str              # display_name
    host: str
    vendor: str
    commands: tuple
    risk: str = "low"
    flows: tuple = ()        # R4：OpenFlow flow 计划（无流表语义的意图为空元组）
    created: float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        return {"id": self.id, "intent_key": self.intent_key,
                "intent_title": self.intent_title, "params": self.params,
                "device": self.device, "host": self.host, "vendor": self.vendor,
                "commands": list(self.commands), "risk": self.risk,
                "flows": list(self.flows),
                "created": self.created,
                "time": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(self.created))}


@dataclass
class CompileResult:
    """一次编译的完整结果（含被跳过的设备与错误）。"""

    intent_key: str = ""
    intent_title: str = ""
    policies: list = field(default_factory=list)
    skipped: list = field(default_factory=list)
    errors: list = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors

    @property
    def commands_total(self) -> int:
        return sum(len(p.commands) for p in self.policies)

    @property
    def highest_risk(self) -> str:
        return max((p.risk for p in self.policies), key=lambda r: RISK_ORDER.get(r, 0),
                   default="low")

    def to_dict(self) -> dict:
        return {"intent_key": self.intent_key, "intent_title": self.intent_title,
                "ok": self.ok, "commands_total": self.commands_total,
                "highest_risk": self.highest_risk,
                "policies": [p.to_dict() for p in self.policies],
                "skipped": list(self.skipped), "errors": list(self.errors)}


class PolicyCompiler:
    """把意图编译成每台设备的策略；不连设备、不写磁盘。"""

    def __init__(self, bus=None):
        self.bus = bus

    def catalog(self) -> list[dict]:
        """意图目录（供 UI 下拉与 REST 使用）。"""
        return intents_mod.list_intents()

    def compile(self, intent_key: str, params: dict, devices: list) -> CompileResult:
        """编译意图到设备集合。

        :raises ValueError: 意图类型不存在（全局错误，直接抛）。
        """
        item = intents_mod.INTENTS.get(intent_key)
        if item is None:
            raise ValueError(f"未知意图类型: {intent_key}")
        title = item["spec"].title
        result = CompileResult(intent_key=intent_key, intent_title=title)

        for device in devices:
            vendor = getattr(device, "vendor", "") or "generic"
            name = getattr(device, "display_name", None) or getattr(device, "host", "?")
            try:
                commands = intents_mod.render_intent(intent_key, params, vendor)
            except ValueError as exc:
                message = str(exc)
                if "暂不支持厂商" in message:
                    result.skipped.append(f"{name}（{vendor}）: {message}")
                else:
                    entry = f"{name}: {message}"
                    if entry not in result.errors:
                        result.errors.append(entry)
                continue
            if not commands:
                result.skipped.append(f"{name}: 该意图未生成任何命令")
                continue
            risk = "high" if any(is_high_risk(c) for c in commands) else "low"
            result.policies.append(Policy(
                id=next_policy_id("pol"),
                intent_key=intent_key, intent_title=title,
                params={k: v for k, v in params.items() if not k.startswith("_")},
                device=name, host=getattr(device, "host", ""), vendor=vendor,
                commands=tuple(commands), risk=risk,
                flows=tuple(flows_for(intent_key, params, vendor))))

        if self.bus is not None:
            self.bus.publish(
                "policy.compiled",
                f"{title}: 编译出 {len(result.policies)} 条策略"
                f"（{result.commands_total} 条命令，风险 {result.highest_risk}）",
                severity="warning" if (result.errors or result.highest_risk == "high") else "info",
                source="policy", intent=intent_key,
                policies=len(result.policies), commands=result.commands_total,
                errors=len(result.errors))
        return result
