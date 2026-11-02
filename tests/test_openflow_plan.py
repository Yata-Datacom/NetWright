"""R4 意图 → 流表契约测试：flows_for 计划 + Policy.flows + REST plan 返回 flows。"""

from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)


from netwright.lib.inventory import Device, Inventory
from netwright.sdn import ControllerStore, nbapi
from netwright.sdn.auth import TokenAuth
from netwright.sdn.openflow_plan import flows_for
from netwright.sdn.southbound.openflow import FlowEntry


PARAMS = {"vlans": "10,20", "in_port": 1, "out_port": 2}


def test_vlan_deploy_generates_ingress_and_egress_flows():
    """vlan_deploy → 每个 VLAN 两条 flow（ingress 打 VLAN、egress 去 VLAN）。"""
    flows = flows_for("vlan_deploy", PARAMS, "huawei")
    assert len(flows) >= 2, "至少要生成 ingress/egress 两条 flow"
    roles = {f["role"] for f in flows}
    assert "ingress_tag" in roles and "egress_untag" in roles
    assert len(flows) == 4, "两个 VLAN × 两个方向"
    ingress = next(f for f in flows if f["role"] == "ingress_tag")
    assert ingress["match"] == {"in_port": 1}
    assert {"type": "push_vlan"} in ingress["actions"]
    egress = next(f for f in flows if f["role"] == "egress_untag")
    assert egress["match"]["vlan_vid"] in (10, 20)


def test_all_planned_flows_pass_flowentry_validation():
    """全部 flow 都能通过 FlowEntry 校验（表/值域/match/动作白名单）。"""
    flows = flows_for("vlan_deploy", PARAMS, "cisco")
    assert flows
    for raw in flows:
        entry = FlowEntry.from_dict(raw)      # 校验不过会抛 FlowError
        assert entry.priority == 200
        assert entry.actions, "动作不能为空"


def test_missing_port_facts_yield_empty_plan():
    """没填 in_port/out_port → 空计划（不猜端口），且不报错。"""
    assert flows_for("vlan_deploy", {"vlans": "10"}, "huawei") == []
    assert flows_for("vlan_deploy", {"vlans": "10", "in_port": 1}, "huawei") == []
    assert flows_for("vlan_deploy", {"vlans": "10", "in_port": 0, "out_port": 2},
                     "huawei") == []
    assert flows_for("vlan_deploy", {"vlans": "10,20", "in_port": 1, "out_port": 1},
                     "huawei") == [], "入出口相同没有语义"


def test_unknown_intent_yields_empty_plan():
    """不支持的意图 → flows=[] 且不报错。"""
    assert flows_for("port_role", {"interface": "GE0/0/1", "mode": "access",
                                   "vlan": "10"}, "huawei") == []
    assert flows_for("bgp_neighbor", {"neighbor_ip": "192.0.2.2", "asn": "65001",
                                      "router_id": "192.0.2.1"}, "huawei") == []
    assert flows_for("", {}, "huawei") == []


def test_compiler_attaches_flows_to_policy(tmp_path):
    """PolicyCompiler 编译 vlan_deploy → Policy.flows 非空（其他意图为空元组）。"""
    inv = Inventory(str(tmp_path / "dev.json"))
    inv.add(Device(host="192.0.2.1", vendor="huawei", hostname="OF-SW"))
    store = ControllerStore(inv)

    result = store.compile("vlan_deploy", PARAMS, inv.devices)
    assert result.ok and result.policies
    policy = result.policies[0]
    assert len(policy.flows) == 4
    assert policy.to_dict()["flows"] == [dict(f) for f in policy.flows]

    other = store.compile("port_role", {"interface": "GE0/0/1", "mode": "access",
                                        "vlan": "10"}, inv.devices)
    assert other.ok
    assert other.policies[0].flows == (), "无流表语义的意图 flows 必须为空元组"


def test_rest_plan_returns_flows(tmp_path):
    """POST /api/v2/intents/plan 返回带 flows；不支持的意图 flows=[] 且 200。"""
    inv = Inventory(str(tmp_path / "dev.json"))
    inv.add(Device(host="192.0.2.1", vendor="huawei", hostname="OF-SW"))
    token = TokenAuth("secret")
    store = ControllerStore(inv, auth=token)
    headers = {"Authorization": "Bearer secret"}

    status, body = nbapi.dispatch(store, "POST", "/api/v2/intents/plan",
                                  {"intent_key": "vlan_deploy", "params": PARAMS},
                                  headers)
    assert status == 200 and body["ok"] is True
    assert body["flows"], "plan 返回必须带 flows"
    assert len(body["flows"]) == 4

    status, body = nbapi.dispatch(store, "POST", "/api/v2/intents/plan",
                                  {"intent_key": "port_role",
                                   "params": {"interface": "GE0/0/1",
                                              "mode": "access", "vlan": "10"}},
                                  headers)
    assert status == 200
    assert body["flows"] == [], "不支持的意图返回空 flows 且不报错"


def test_rest_plan_flows_round_trip_through_validate(tmp_path):
    """闭环：plan 产出的 flows 直接喂 /openflow/validate 能全部编码通过。"""
    inv = Inventory(str(tmp_path / "dev.json"))
    inv.add(Device(host="192.0.2.1", vendor="huawei", hostname="OF-SW"))
    token = TokenAuth("secret")
    store = ControllerStore(inv, auth=token)
    headers = {"Authorization": "Bearer secret"}

    _status, plan = nbapi.dispatch(store, "POST", "/api/v2/intents/plan",
                                   {"intent_key": "vlan_deploy", "params": PARAMS},
                                   headers)
    status, validated = nbapi.dispatch(store, "POST", "/api/v2/openflow/validate",
                                       {"flows": plan["flows"]}, headers)
    assert status == 200 and validated["ok"] is True
    assert validated["count"] == len(plan["flows"])
    for compiled in validated["compiled"]:
        assert compiled["bytes"] >= 64 and len(compiled["hex"]) == compiled["bytes"] * 2
