"""意图生命周期 + REST v2 鉴权测试（编译 → 预演 → 下发 → 校验 → 回滚）。"""

from __future__ import annotations

import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)


from netwright.lib.inventory import Device, Inventory
from netwright.sdn import ControllerStore, nbapi
from netwright.sdn.auth import TokenAuth
from netwright.sdn.lifecycle import LifecycleError
from netwright.sdn.southbound import CommandOutput
from netwright.sdn.reverse import reverse_commands


class FakeAdapter:
    """把 CLI 通道换成一个可编程的假适配器（不连任何设备）。"""

    protocol = "cli"

    def __init__(self, output: str = "", fail: bool = False):
        self.output = output
        self.fail = fail
        self.calls: list[list[str]] = []

    def run_commands(self, device, commands, timeout=15.0):
        self.calls.append(list(commands))
        if self.fail:
            return [CommandOutput(c, "", "mock failure") for c in commands]
        return [CommandOutput(c, self.output or f"ok {c}", "") for c in commands]


def _store(tmp_path, auth=None):
    inv = Inventory(str(tmp_path / "dev.json"))
    inv.add(Device(host="192.0.2.1", vendor="huawei", hostname="核心A"))
    store = ControllerStore(inv, auth=auth)
    return store


def _plan(store, params=None):
    runs = store.lifecycle.create("vlan_deploy", params or {"vlans": "10,20"},
                                  store.inventory.devices)
    for run in runs:
        assert store.lifecycle.plan(run)["ok"]
    return runs


# ── 反向命令 ────────────────────────────────────────────────────────
def test_reverse_vlan_per_vendor():
    cmds, reason = reverse_commands("vlan_deploy", {"vlans": "10,20"}, "huawei")
    assert cmds == ["undo vlan 10", "undo vlan 20"] and reason
    cmds, _ = reverse_commands("vlan_deploy", {"vlans": "10,20"}, "cisco")
    assert cmds == ["no vlan 10", "no vlan 20"]


def test_reverse_is_honest_when_unknown():
    cmds, reason = reverse_commands("port_role", {"interface": "GE0/0/1", "mode": "trunk", "vlan": "10"}, "huawei")
    assert cmds == [] and "原状态" in reason
    cmds, reason = reverse_commands("mgmt_baseline", {}, "huawei")
    assert cmds == [] and "人工" in reason


def test_reverse_port_shutdown():
    cmds, _ = reverse_commands("port_role", {"interface": "GE0/0/1", "mode": "shutdown"}, "huawei")
    assert cmds == ["interface GE0/0/1", "undo shutdown"]


# ── 状态机 ──────────────────────────────────────────────────────────
def test_lifecycle_full_path(tmp_path):
    store = _store(tmp_path)
    run = _plan(store)[0]
    assert run.state == "planned" and run.can_rollback
    store.lifecycle.approve(run)
    assert run.state == "approved"

    adapter = FakeAdapter(output="10 20 VLAN")
    result = store.lifecycle.deploy(run, adapter=adapter)
    assert result["ok"] and run.state == "deployed"
    assert adapter.calls, "下发必须真的调用适配器"

    result = store.lifecycle.verify(run, adapter=FakeAdapter(output="VLAN 10 ... VLAN 20"))
    assert result["ok"] and run.state == "verified"

    result = store.lifecycle.rollback(run, adapter=FakeAdapter())
    assert result["ok"] and run.state == "rolled_back"
    states = [s for s, _t, _n in run.history]
    assert states[:6] == ["compiled", "planned", "approved", "deploying", "deployed", "verified"]


def test_lifecycle_deploy_failure_marks_failed(tmp_path):
    store = _store(tmp_path)
    run = _plan(store)[0]
    store.lifecycle.approve(run)
    result = store.lifecycle.deploy(run, adapter=FakeAdapter(fail=True))
    assert result["ok"] is False and run.state == "failed"


def test_lifecycle_verify_detects_missing_vlan(tmp_path):
    store = _store(tmp_path)
    run = _plan(store)[0]
    store.lifecycle.approve(run)
    store.lifecycle.deploy(run, adapter=FakeAdapter())
    result = store.lifecycle.verify(run, adapter=FakeAdapter(output="VLAN 10 only"))
    assert result["ok"] is False and run.state == "failed"
    assert any(c["name"] == "关键字段" and not c["ok"] for c in run.checks)


def test_lifecycle_rollback_blocked_without_reverse(tmp_path):
    store = _store(tmp_path)
    runs = store.lifecycle.create("port_role",
                                  {"interface": "GE0/0/1", "mode": "trunk", "vlan": "10"},
                                  store.inventory.devices)
    run = runs[0]
    assert run.can_rollback is False
    assert store.lifecycle.plan(run)["ok"]
    store.lifecycle.approve(run)
    store.lifecycle.deploy(run, adapter=FakeAdapter())
    result = store.lifecycle.rollback(run, adapter=FakeAdapter())
    assert result["blocked"] is True and run.state == "rollback_blocked"
    assert "原状态" in run.reverse_reason


def test_illegal_transition_rejected(tmp_path):
    store = _store(tmp_path)
    run = _plan(store)[0]
    with pytest.raises(LifecycleError):
        store.lifecycle._touch(run, "verified", "跳过下发")


def test_create_without_devices_raises(tmp_path):
    store = _store(tmp_path)
    with pytest.raises(LifecycleError):
        store.lifecycle.create("vlan_deploy", {"vlans": "10"}, [])


def test_snapshot_contains_intents(tmp_path):
    store = _store(tmp_path)
    _plan(store)
    snapshot = store.snapshot()
    assert snapshot["intents"] and snapshot["intents"][0]["state"] == "planned"


# ── REST v2 鉴权 + 意图路由 ─────────────────────────────────────────
def test_nbapi_requires_token(tmp_path):
    store = _store(tmp_path, auth=TokenAuth("secret-token"))
    status, body = nbapi.dispatch(store, "GET", "/api/v2/topology")
    assert status == 401 and body["ok"] is False
    status, body = nbapi.dispatch(store, "GET", "/api/v2/topology",
                                  headers={"Authorization": "Bearer secret-token"})
    assert status == 200 and body["ok"]
    status, _ = nbapi.dispatch(store, "GET", "/api/v2/topology",
                               headers={"X-API-Token": "secret-token"})
    assert status == 200


def test_nbapi_health_is_public(tmp_path):
    store = _store(tmp_path, auth=TokenAuth("secret"))
    status, body = nbapi.dispatch(store, "GET", "/api/v2/health")
    assert status == 200 and body["ok"]


def test_nbapi_token_rotation_invalidates_old(tmp_path):
    auth = TokenAuth("old-token")
    store = _store(tmp_path, auth=auth)
    assert nbapi.dispatch(store, "GET", "/api/v2/events",
                          headers={"X-API-Token": "old-token"})[0] == 200
    auth.rotate()
    assert nbapi.dispatch(store, "GET", "/api/v2/events",
                          headers={"X-API-Token": "old-token"})[0] == 401


def test_nbapi_intent_plan_and_deploy(tmp_path):
    store = _store(tmp_path, auth=TokenAuth("t"))
    headers = {"Authorization": "Bearer t"}
    status, body = nbapi.dispatch(
        store, "POST", "/api/v2/intents/plan",
        {"intent_key": "vlan_deploy", "params": {"vlans": "10,20"}}, headers=headers)
    assert status == 200 and body["count"] == 1
    run_id = body["runs"][0]["id"]

    adapter = FakeAdapter(output="VLAN 10 20")
    store.registry.for_device = lambda _device: adapter      # 注入假南向

    status, body = nbapi.dispatch(store, "POST", "/api/v2/intents/deploy",
                                  {"run_ids": [run_id]}, headers=headers)
    assert status == 200 and body["ok"]
    status, body = nbapi.dispatch(store, "POST", "/api/v2/intents/verify",
                                  {"run_ids": [run_id]}, headers=headers)
    assert status == 200 and body["ok"]
    status, body = nbapi.dispatch(store, "GET", "/api/v2/intents/runs", headers=headers)
    assert status == 200 and body["runs"][0]["state"] == "verified"


def test_nbapi_intent_rollback_blocked(tmp_path):
    store = _store(tmp_path, auth=TokenAuth("t"))
    headers = {"Authorization": "Bearer t"}
    _status, body = nbapi.dispatch(
        store, "POST", "/api/v2/intents/plan",
        {"intent_key": "port_role", "params": {"interface": "GE0/0/1", "mode": "trunk", "vlan": "10"}},
        headers=headers)
    run_id = body["runs"][0]["id"]
    adapter = FakeAdapter()
    store.registry.for_device = lambda _device: adapter
    nbapi.dispatch(store, "POST", "/api/v2/intents/deploy", {"run_ids": [run_id]},
                   headers=headers)
    status, body = nbapi.dispatch(store, "POST", "/api/v2/intents/rollback",
                                  {"run_ids": [run_id]}, headers=headers)
    assert status == 422 and body["results"][0]["blocked"] is True


def test_nbapi_intent_plan_validation(tmp_path):
    store = _store(tmp_path, auth=TokenAuth("t"))
    headers = {"Authorization": "Bearer t"}
    status, body = nbapi.dispatch(store, "POST", "/api/v2/intents/plan",
                                  {"params": {"vlans": "10"}}, headers=headers)
    assert status == 400 and body["ok"] is False
    status, body = nbapi.dispatch(store, "POST", "/api/v2/intents/deploy", {},
                                  headers=headers)
    assert status == 400
