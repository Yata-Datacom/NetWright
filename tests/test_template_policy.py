"""R13 模板 → 策略闭环契约测试。

模板 + 设备表 → Policy（带模板溯源）→ 生命周期（预演/下发/回滚 blocked）
——证明模板下发与意图下发走同一条受审计的路，没有旁路。
"""

from __future__ import annotations

import hashlib
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)


from netwright.lib import generator
from netwright.lib.controller import deploy as deploy_mod
from netwright.lib.inventory import Device, Inventory
from netwright.sdn import ControllerStore
from netwright.sdn.southbound import CommandOutput

TEMPLATE_TEXT = """#
# VLAN 基线模板（华为）
#
sysname {{hostname}}
vlan batch {{vlans}}
#
interface {{uplink}}
description uplink
#"""


class FakeTemplateAdapter:
    protocol = "cli"

    def __init__(self):
        self.sent: list[list[str]] = []

    def run_commands(self, device, commands, timeout=15.0):
        self.sent.append(list(commands))
        return [CommandOutput(c, "ok", "") for c in commands]


def _template(vendor: str = "huawei") -> dict:
    return {"file": "cli/vlan_baseline/huawei.cfg", "vendor": vendor,
            "name": "VLAN 基线", "text": TEMPLATE_TEXT,
            "vars": generator.template_variables(TEMPLATE_TEXT)}


def _inventory(tmp_path) -> Inventory:
    inv = Inventory(str(tmp_path / "dev.json"))
    inv.add(Device(host="192.0.2.10", vendor="huawei", hostname="SW-HZ-01"))
    return inv


def test_to_policies_renders_commands_per_device(tmp_path):
    """一台华为设备渲染出 N 条命令 → Policy.commands == N（空行/注释被滤掉）。"""
    inv = _inventory(tmp_path)
    rows = [{"hostname": "SW-HZ-01", "host": "192.0.2.10",
             "vlans": "10,20", "uplink": "GE0/0/24"}]
    policies = generator.to_policies(_template(), rows, inv)
    assert len(policies) == 1
    policy = policies[0]
    # 模板 8 行文本 → 命令应为 4 条：sysname / vlan batch / interface / description
    assert len(policy.commands) == 4
    assert list(policy.commands) == ["sysname SW-HZ-01", "vlan batch 10,20",
                                     "interface GE0/0/24", "description uplink"]
    assert policy.device == "SW-HZ-01" and policy.host == "192.0.2.10"
    assert policy.vendor == "huawei"
    assert policy.intent_key == "template_deploy"


def test_policy_params_record_template_file_and_sha256(tmp_path):
    """Policy.params["template"] 必须带模板文件名 + sha256（审计可追）。"""
    inv = _inventory(tmp_path)
    rows = [{"hostname": "SW-HZ-01", "host": "192.0.2.10",
             "vlans": "10", "uplink": "GE0/0/1"}]
    tpl = _template()
    policies = generator.to_policies(tpl, rows, inv)
    meta = policies[0].params["template"]
    assert meta["file"] == "cli/vlan_baseline/huawei.cfg"
    assert meta["sha256"] == hashlib.sha256(tpl["text"].encode("utf-8")).hexdigest()
    # 设备表变量也留在 params 里（详情页可读）
    assert policies[0].params["vlans"] == "10"


def test_to_policies_missing_variable_raises_with_index(tmp_path):
    """设备表缺变量 → 报错带设备序号，绝不渲染出字面占位符。"""
    inv = _inventory(tmp_path)
    rows = [{"hostname": "SW-HZ-01", "host": "192.0.2.10",
             "vlans": "10", "uplink": ""}]     # uplink 缺失
    try:
        generator.to_policies(_template(), rows, inv)
    except ValueError as exc:
        assert "第 1 台设备缺少变量" in str(exc) and "uplink" in str(exc)
    else:
        raise AssertionError("缺变量必须抛 ValueError")


def test_to_policies_unknown_device_gets_synthesized_identity(tmp_path):
    """行不在清单里 → 用行内信息合成设备身份（模板部署不强制先入清单）。"""
    inv = _inventory(tmp_path)
    rows = [{"hostname": "SW-NOT-IN-INV", "vlans": "30", "uplink": "GE0/0/1"}]
    policies = generator.to_policies(_template(), rows, inv)
    assert policies[0].device == "SW-NOT-IN-INV"
    assert policies[0].host == "SW-NOT-IN-INV"


def test_template_policy_runs_through_lifecycle(tmp_path):
    """模板策略 → adopt → plan → deploy 走完整生命周期（不绕过审计）。"""
    inv = _inventory(tmp_path)
    store = ControllerStore(inv)
    rows = [{"hostname": "SW-HZ-01", "host": "192.0.2.10",
             "vlans": "10,20", "uplink": "GE0/0/24"}]
    policies = generator.to_policies(_template(), rows, inv)

    adapter = FakeTemplateAdapter()
    store.registry.for_device = lambda _d: adapter
    runs = store.lifecycle.adopt(policies)
    run = runs[0]
    assert run.state == "compiled"

    assert store.lifecycle.plan(run)["ok"]
    assert store.lifecycle.approve(run) is None
    result = store.lifecycle.deploy(run, adapter=adapter)
    assert result["ok"] is True
    assert adapter.sent == [list(policies[0].commands)], \
        "下发的内容必须是模板渲染的命令（同一条生命周期路径）"
    # 运行档案能看到来源模板
    detail = run.to_dict()
    assert detail["params"]["template"]["file"] == "cli/vlan_baseline/huawei.cfg"
    actions = [e.get("action") for e in deploy_mod.audit_tail(50)]
    assert "intent.deploy" in actions, "模板下发的审计与意图下发一致"


def test_template_policy_rollback_is_blocked(tmp_path):
    """template_deploy 无登记反向命令 → rollback_blocked（与现有一致，不猜命令）。"""
    inv = _inventory(tmp_path)
    store = ControllerStore(inv)
    rows = [{"hostname": "SW-HZ-01", "host": "192.0.2.10",
             "vlans": "10", "uplink": "GE0/0/1"}]
    policies = generator.to_policies(_template(), rows, inv)
    run = store.lifecycle.adopt(policies)[0]
    assert not run.can_rollback and run.reverse_reason
    assert store.lifecycle.plan(run)["ok"]
    store.lifecycle.deploy(run, adapter=FakeTemplateAdapter())
    result = store.lifecycle.rollback(run, adapter=FakeTemplateAdapter())
    assert result.get("blocked") is True
    assert run.state == "rollback_blocked"


def test_builtin_templates_still_render_clean(tmp_path):
    """内置模板库仍能渲染（零残留校验不回归）——取华为 VLAN 模板真实跑一遍。"""
    tpls = generator.list_builtin_templates()
    assert tpls, "内置模板库不应为空"
    huawei = next((t for t in tpls if t["vendor"] == "huawei" and t["vars"]), None)
    assert huawei is not None, "应存在带变量的华为模板"
    row = {v: f"V_{i}" for i, v in enumerate(huawei["vars"])}
    text = generator.render_template(huawei["text"], row)
    assert "{{" not in text and "}}" not in text, "渲染后不允许残留占位符"
