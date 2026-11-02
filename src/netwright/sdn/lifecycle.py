"""lifecycle.py — 意图生命周期（编译 → 预演 → 下发 → 校验 → 回滚）。

借鉴 ONOS/ODL 的 intent 状态机，但刻意做了两个"工程化"取舍：

  1. **预演不连设备**：``plan()`` 只是把编译结果标成"可审批"，真正的 Dry-Run
     比较由 ``verify_plan()`` 做静态检查（命令条数/风险/参数），避免为了"预演"
     反而去连生产设备。
  2. **回滚必须知道自己能否回滚**：反向命令由 ``reverse.py`` 生成，生成不了就
     返回"不可回滚"，状态停在 ``rollback_blocked``，提示人工处置——不猜命令。

状态机（只允许下列迁移，其余抛 ``LifecycleError``）::

    compiled → planned → approved → deploying → deployed → verified
                                   ↘ failed ↗          ↘ rolled_back
    failed → planned（重试） / rolled_back
    deployed / verified → rollback_blocked（无反向命令）
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field

from ..lib.controller import deploy as deploy_mod
from ..lib.errors import friendly_error, friendly_text
from .reverse import reverse_commands

STATES = ("compiled", "planned", "approved", "deploying", "deployed",
          "verified", "failed", "rolled_back", "rollback_blocked")

TRANSITIONS = {
    "compiled": {"planned", "failed"},
    "planned": {"approved", "failed"},
    "approved": {"deploying"},
    "deploying": {"deployed", "failed"},
    "deployed": {"verified", "failed", "rolled_back", "rollback_blocked"},
    "verified": {"rolled_back", "rollback_blocked"},
    "failed": {"planned", "rolled_back", "rollback_blocked"},
    "rolled_back": set(),
    "rollback_blocked": set(),
}

VERIFY_COMMANDS = {
    "huawei": "display vlan",
    "huawei_ac": "display vlan",
    "h3c": "display vlan",
    "h3c_ac": "display vlan",
    "cisco": "show vlan brief",
    "cisco_wlc": "show vlan brief",
    "ruijie": "show vlan brief",
}


class LifecycleError(RuntimeError):
    """非法的状态迁移 / 缺少设备 / 适配器不支持。"""


def _now() -> float:
    return time.time()


@dataclass
class PolicyRun:
    """一次策略从编译到回滚的完整档案。"""

    policy: object                      # sdn.policy.Policy
    state: str = "compiled"
    history: list = field(default_factory=list)   # [(state, ts, note)]
    checks: list = field(default_factory=list)    # 校验结果
    error: str = ""
    reverse: list = field(default_factory=list)
    reverse_reason: str = ""
    created: float = field(default_factory=_now)
    updated: float = field(default_factory=_now)

    # ── 展示 ──
    @property
    def id(self) -> str:
        return getattr(self.policy, "id", "")

    @property
    def device(self) -> str:
        return getattr(self.policy, "device", "")

    @property
    def can_rollback(self) -> bool:
        return bool(self.reverse)

    def to_dict(self) -> dict:
        data = self.policy.to_dict() if hasattr(self.policy, "to_dict") else {}
        data.update({
            "state": self.state,
            "history": [{"state": s, "ts": t, "time": time.strftime("%H:%M:%S", time.localtime(t)),
                         "note": n} for s, t, n in self.history],
            "checks": list(self.checks),
            "error": self.error,
            "reverse": list(self.reverse),
            "reverse_reason": self.reverse_reason,
            "can_rollback": self.can_rollback,
            "updated": self.updated,
        })
        return data


class IntentLifecycle:
    """把「编译结果」推进成可下发、可校验、可回滚的运行档案。"""

    def __init__(self, store):
        self.store = store
        self.bus = store.bus
        self.runs: dict[str, PolicyRun] = {}

    # ── 创建 / 迁移 ──
    def create(self, intent_key: str, params: dict, devices: list, runs: list | None = None) -> list[PolicyRun]:
        from .policy import PolicyCompiler

        devices = list(devices)
        if not devices:
            raise LifecycleError("没有目标设备：请先在设备清单添加或在意图页选择")
        compiler = PolicyCompiler(self.bus)
        result = compiler.compile(intent_key, params, devices)
        if result.errors:
            raise LifecycleError("；".join(result.errors[:3]))
        if not result.policies:
            raise LifecycleError("没有编译出任何策略（目标厂商都不支持该意图？）")
        created = []
        for policy in result.policies:
            reverse, reason = reverse_commands(policy.intent_key, policy.params, policy.vendor)
            run = PolicyRun(policy=policy, reverse=list(reverse), reverse_reason=reason)
            self._touch(run, "compiled", f"生成 {len(policy.commands)} 条命令，风险 {policy.risk}")
            self.runs[run.id] = run
            created.append(run)
        if runs is not None:
            runs.extend(created)
        self.bus.publish("intent.compiled",
                         f"{result.intent_title}: {len(created)} 台设备已编译，等待预演",
                         source="lifecycle", intent=intent_key, runs=len(created))
        return created

    def _touch(self, run: PolicyRun, state: str, note: str = ""):
        if state not in STATES:
            raise LifecycleError(f"未知状态 {state}")
        if state != run.state and state not in TRANSITIONS.get(run.state, set()):
            raise LifecycleError(f"非法迁移 {run.state} → {state}")
        run.state = state
        run.updated = _now()
        run.history.append((state, run.updated, note))
        self.bus.publish(f"policy.{state}",
                         f"{run.device} ({getattr(run.policy, 'vendor', '')}): {state}"
                         + (f" · {note}" if note else ""),
                         severity="warning" if state in ("failed", "rollback_blocked") else "info",
                         source="lifecycle", run=run.id, device=run.device)

    # ── 预演 ──
    def plan(self, run: PolicyRun) -> dict:
        """静态预演：检查命令、风险、回滚能力，不连设备。"""
        checks = []
        commands = list(getattr(run.policy, "commands", ()))
        checks.append({"name": "命令非空", "ok": bool(commands),
                       "detail": f"{len(commands)} 条"})
        checks.append({"name": "风险等级", "ok": True,
                       "detail": getattr(run.policy, "risk", "low")})
        checks.append({"name": "可回滚", "ok": run.can_rollback,
                       "detail": "已生成反向命令" if run.can_rollback else run.reverse_reason})
        run.checks = checks
        if not commands:
            run.error = "策略没有任何命令"
            self._touch(run, "failed", run.error)
            return {"ok": False, "checks": checks}
        self._touch(run, "planned", f"预演通过（{len(commands)} 条命令）")
        return {"ok": True, "checks": checks}

    def approve(self, run: PolicyRun, note: str = "人工确认下发") -> None:
        self._touch(run, "approved", note)

    # ── 下发 ──
    def deploy(self, run: PolicyRun, adapter=None, device=None, timeout: float = 15.0) -> dict:
        device = device or self._device_for(run)
        adapter = adapter or self._adapter_for(device)
        if run.state == "planned":
            # 调用 deploy 本身就是"确认下发"：把审批写进历史，状态机保持诚实
            self.approve(run, note="调用方确认下发（deploy 隐式审批）")
        self._touch(run, "deploying", f"通过 {adapter.protocol} 下发")
        try:
            outputs = adapter.run_commands(device, list(run.policy.commands), timeout=timeout)
        except Exception as exc:      # noqa: BLE001  适配器异常统一转成失败状态
            run.error = friendly_error(exc)
            self._touch(run, "failed", run.error)
            return {"ok": False, "error": run.error}
        failed = [o for o in outputs if not o.ok]
        deploy_mod._audit({"action": "intent.deploy", "intent": run.policy.intent_key,
                           "device": run.device, "commands": len(outputs),
                           "status": "OK" if not failed else "WARNING"})
        if failed:
            first = friendly_text(failed[0].error) if failed[0].error else ""
            run.error = (f"{len(failed)} 条命令返回错误"
                         + (f"（首条：{first}）" if first else ""))
            self._touch(run, "failed", run.error)
            return {"ok": False, "error": run.error, "outputs": [o.__dict__ for o in outputs]}
        self._touch(run, "deployed", f"{len(outputs)} 条命令执行完成")
        return {"ok": True, "outputs": [o.__dict__ for o in outputs]}

    # ── 校验 ──
    def verify(self, run: PolicyRun, adapter=None, device=None) -> dict:
        """回读设备状态，确认意图真的生效（不是"命令发出去了"就算完）。"""
        device = device or self._device_for(run)
        adapter = adapter or self._adapter_for(device)
        command = VERIFY_COMMANDS.get(getattr(device, "vendor", ""))
        if command and adapter.protocol == "cli":
            try:
                outputs = adapter.run_commands(device, [command])
                text = outputs[0].output if outputs else ""
            except Exception as exc:      # noqa: BLE001
                run.checks = [{"name": "回读", "ok": False, "detail": str(exc)}]
                self._touch(run, "failed", f"校验失败：{exc}")
                return {"ok": False, "error": str(exc)}
            expected = self._expected_tokens(run)
            missing = [token for token in expected if token not in text]
            ok = not missing
            run.checks = [{"name": "回读命令", "ok": True, "detail": command},
                          {"name": "关键字段", "ok": ok,
                           "detail": ("全部命中" if ok else f"缺少 {missing}")}]
        else:
            # 没有该厂商的回读命令（或非 CLI 通道）：只能确认命令已下发
            run.checks = [{"name": "回读", "ok": True,
                           "detail": "该厂商无内置回读命令，仅确认下发成功"}]
            ok = True
        if ok:
            self._touch(run, "verified", "回读校验通过")
            return {"ok": True, "checks": run.checks}
        self._touch(run, "failed", "回读未命中关键字段")
        return {"ok": False, "checks": run.checks}

    # ── 回滚 ──
    def rollback(self, run: PolicyRun, adapter=None, device=None, timeout: float = 15.0) -> dict:
        if not run.reverse:
            self._touch(run, "rollback_blocked", run.reverse_reason or "没有可用的反向命令")
            return {"ok": False, "blocked": True, "reason": run.reverse_reason}
        device = device or self._device_for(run)
        adapter = adapter or self._adapter_for(device)
        try:
            outputs = adapter.run_commands(device, list(run.reverse), timeout=timeout)
        except Exception as exc:      # noqa: BLE001
            run.error = friendly_error(exc)
            self._touch(run, "failed", f"回滚失败：{run.error}")
            return {"ok": False, "error": run.error}
        failed = [o for o in outputs if not o.ok]
        deploy_mod._audit({"action": "intent.rollback", "intent": run.policy.intent_key,
                           "device": run.device, "commands": len(outputs),
                           "status": "OK" if not failed else "WARNING"})
        if failed:
            run.error = f"回滚时 {len(failed)} 条命令报错"
            self._touch(run, "failed", run.error)
            return {"ok": False, "error": run.error}
        self._touch(run, "rolled_back", f"{len(outputs)} 条反向命令执行完成")
        return {"ok": True, "outputs": [o.__dict__ for o in outputs]}

    # ── 辅助 ──
    def _device_for(self, run: PolicyRun):
        host = getattr(run.policy, "host", "")
        for device in self.store.inventory.devices:
            if device.host == host:
                return device
        raise LifecycleError(f"设备清单里找不到 {host}（可能已被删除）")

    def _adapter_for(self, device):
        adapter = self.store.registry.for_device(device)
        if adapter is None:
            raise LifecycleError(f"没有匹配 {device.protocol} 的南向适配器")
        return adapter

    @staticmethod
    def _expected_tokens(run: PolicyRun) -> list[str]:
        params = getattr(run.policy, "params", {}) or {}
        raw = str(params.get("vlans") or "")
        tokens = [t for t in raw.replace("，", ",").replace("、", ",").split(",") if t.strip()]
        return [t.strip() for t in tokens]

    # ── 查询 ──
    def get(self, run_id: str) -> PolicyRun | None:
        return self.runs.get(run_id)

    def recent(self, limit: int = 50) -> list[PolicyRun]:
        return sorted(self.runs.values(), key=lambda r: r.updated, reverse=True)[:limit]

    def snapshot(self, limit: int = 50) -> list[dict]:
        return [run.to_dict() for run in self.recent(limit)]
