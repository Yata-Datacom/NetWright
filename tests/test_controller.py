# -*- coding: utf-8 -*-
"""控制器测试：意图渲染 / LLDP 解析 / 拓扑 / 部署流水线 / REST 北向。"""

from __future__ import annotations

import json
import os
import sys
import urllib.request

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from netforge_lib.controller import deploy, intents, topology  # noqa: E402
from netforge_lib.controller.restapi import ControllerAPI, ControllerState  # noqa: E402
from netforge_lib.inventory import Device, Inventory  # noqa: E402


# ── 意图渲染 ────────────────────────────────────────────────────────
def test_intent_catalog():
    items = intents.list_intents()
    keys = {i["key"] for i in items}
    assert {"vlan_deploy", "port_role", "bgp_neighbor", "static_route", "mgmt_baseline"} <= keys
    for item in items:
        assert item["fields"], f"{item['key']} 缺表单字段"


def test_vlan_deploy_render_all_vendors():
    for vendor in ("huawei", "h3c", "cisco", "ruijie"):
        cmds = intents.render_intent("vlan_deploy", {"vlans": "10,20", "description": "Users"},
                                     vendor)
        blob = "\n".join(cmds)
        assert "vlan 10" in blob and "vlan 20" in blob, vendor
    assert "vlan batch 10 20" in intents.render_intent(
        "vlan_deploy", {"vlans": "10,20", "description": "Users"}, "huawei")


def test_port_role_access_and_trunk():
    hw_access = intents.render_intent(
        "port_role", {"interface": "GE0/0/1", "mode": "access", "vlan": "10"}, "huawei")
    assert hw_access[0] == "interface GigabitEthernet0/0/1"
    assert "port default vlan 10" in hw_access
    cs_trunk = intents.render_intent(
        "port_role", {"interface": "Gi0/1", "mode": "trunk", "vlan": "10 20"}, "cisco")
    assert cs_trunk[0] == "interface GigabitEthernet0/1"
    assert "switchport trunk allowed vlan 10,20" in cs_trunk


def test_bgp_neighbor_render():
    hw = intents.render_intent(
        "bgp_neighbor", {"local_as": 65001, "router_id": "192.0.2.1",
                         "neighbor_ip": "192.0.2.2", "remote_as": 65002}, "huawei")
    assert "bgp 65001" in hw and "peer 192.0.2.2 as-number 65002" in "\n".join(hw)
    cs = intents.render_intent(
        "bgp_neighbor", {"local_as": 65001, "router_id": "192.0.2.1",
                         "neighbor_ip": "192.0.2.2", "remote_as": 65002}, "cisco")
    assert "router bgp 65001" in cs and "neighbor 192.0.2.2 remote-as 65002" in "\n".join(cs)


def test_intent_validation_errors():
    with pytest.raises(ValueError):
        intents.render_intent("vlan_deploy", {"vlans": ""}, "huawei")          # 缺必填
    with pytest.raises(ValueError):
        intents.render_intent("vlan_deploy", {"vlans": "10,abc", "description": "x"}, "huawei")
    with pytest.raises(ValueError):
        intents.render_intent("no_such_intent", {}, "huawei")
    with pytest.raises(ValueError):
        intents.render_intent("bgp_neighbor", {"local_as": 1, "router_id": "1.1.1.1",
                                               "neighbor_ip": "999.1.1.1", "remote_as": 2},
                              "huawei")                                        # IP 非法
    with pytest.raises(ValueError):
        intents.render_intent("bgp_neighbor", {"local_as": 1, "router_id": "1.1.1.1",
                                               "neighbor_ip": "2.2.2.2", "remote_as": 2},
                              "linux")                                         # 不支持的厂商


def test_static_route_and_baseline():
    hw = intents.render_intent("static_route", {"destination": "10.1.0.0", "mask": "255.255.0.0",
                                                "nexthop": "192.0.2.254", "preference": 100}, "huawei")
    assert hw[0] == "ip route-static 10.1.0.0 255.255.0.0 192.0.2.254 preference 100"
    cs = intents.render_intent("mgmt_baseline", {"ntp_server": "192.0.2.53",
                                                 "syslog_server": "192.0.2.54"}, "cisco")
    assert "ntp server 192.0.2.53" in cs and "logging host 192.0.2.54" in cs


# ── LLDP/CDP 解析与拓扑 ────────────────────────────────────────────
HUAWEI_BRIEF = """
Local Intf    Neighbor Intf     Neighbor Device       Exptime(s)
GE0/0/1       GE0/0/24          SW-2                  105
GE0/0/2       GE0/0/24          SW-3                  105
"""

CISCO_CDP = """
Device ID        Local Intrfce     Holdtme  Capability  Platform   Port ID
SW-1             Gig 0/24          167      S I         WS-C2960   Gig 0/1
"""

H3C_BRIEF = """
Interface GE1/0/48 has 1 neighbor(s):
  Neighbor: GE1/0/24   System Name: SW-1
"""


def test_parse_huawei_brief():
    links = topology.parse_neighbors("huawei", HUAWEI_BRIEF, "SW-1")
    assert [(l.local_intf, l.peer_device, l.peer_intf) for l in links] == [
        ("GigabitEthernet0/0/1", "SW-2", "GigabitEthernet0/0/24"),
        ("GigabitEthernet0/0/2", "SW-3", "GigabitEthernet0/0/24")]


def test_parse_cisco_cdp():
    links = topology.parse_neighbors("cisco", CISCO_CDP, "SW-2")
    assert links and links[0].peer_device == "SW-1" and links[0].peer_intf == "Gig 0/1"


def test_parse_h3c_brief():
    links = topology.parse_neighbors("h3c", H3C_BRIEF, "SW-3")
    assert links and links[0].peer_device == "SW-1"


def test_build_topology_dedupes_undirected():
    topo = topology.build_topology([
        ("SW-1", "huawei", HUAWEI_BRIEF),
        ("SW-2", "cisco", CISCO_CDP),   # SW-2↔SW-1 与上面是同一条边
    ])
    edges = topo.undirected_edges()
    pairs = [tuple(sorted((e[0], e[2]))) for e in edges]
    assert pairs.count(("SW-1", "SW-2")) == 1
    assert "SW-3" in topo.nodes


def test_unsupported_vendor_rejected():
    with pytest.raises(ValueError):
        topology.parse_neighbors("linux", "anything", "L1")


# ── 部署流水线 ──────────────────────────────────────────────────────
def test_dry_run_plan(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)  # 审计日志写 tmp
    devices = [Device(host="192.0.2.1", vendor="huawei", hostname="A"),
               Device(host="192.0.2.2", vendor="linux", hostname="L1")]
    plan = deploy.dry_run("vlan_deploy", {"vlans": "10", "description": "Users"}, devices)
    assert plan["plan"][0]["device"] == "A"
    assert "vlan 10" in plan["plan"][0]["commands"]
    assert plan["skipped"] and "linux" in plan["skipped"][0]


def test_apply_records_audit(tmp_path, monkeypatch):
    monkeypatch.setattr(deploy, "_base_dir", lambda: str(tmp_path))
    devices = [Device(host="192.0.2.1", vendor="huawei", username="a", password="b")]

    def fake_run_commands(dev, cmds, timeout=15.0, port=None):
        return [(c, c, "ok", "") for c in cmds]

    from netforge_lib import ssh_client
    with patch.object(ssh_client, "run_commands", fake_run_commands):
        result = deploy.apply("vlan_deploy", {"vlans": "10", "description": "Users"}, devices)
    assert result["results"][0]["status"] == "OK"
    audit = deploy.audit_tail()
    assert any(e.get("action") == "intent.apply" and e["device"] == "192.0.2.1" for e in audit)
    # 密码永不入审计
    assert all("b" != e.get("params", {}).get("password") for e in audit)


from unittest.mock import patch  # noqa: E402


# ── REST 北向 ───────────────────────────────────────────────────────
@pytest.fixture(scope="module")
def api():
    inv = Inventory(str(ROOT + "/.tmp-inv.json") if False else None)
    inv.devices = [Device(host="192.0.2.1", vendor="huawei", username="admin",
                          password="TopSecret", hostname="A")]
    state = ControllerState(inv)
    svc = ControllerAPI(state, port=0)          # 端口 0 = 随机空闲
    svc.start()
    yield svc, state
    svc.stop()
    try:
        os.unlink(str(inv.path))
    except OSError:
        pass


def _get(url):
    with urllib.request.urlopen(url, timeout=5) as r:
        return json.loads(r.read().decode())


def _post(url, payload):
    req = urllib.request.Request(url, data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=5) as r:
        return json.loads(r.read().decode())


def test_rest_health_and_devices(api):
    svc, _ = api
    base = f"http://127.0.0.1:{svc._server.server_address[1]}"
    assert _get(base + "/api/health")["ok"] is True
    devs = _get(base + "/api/devices")["devices"]
    assert devs[0]["password"] == "••••••"        # 密码打码
    assert "TopSecret" not in json.dumps(_get(base + "/api/devices"))


def test_rest_intents_and_dryrun(api):
    svc, _ = api
    base = f"http://127.0.0.1:{svc._server.server_address[1]}"
    catalog = _get(base + "/api/intents")["intents"]
    assert any(i["key"] == "vlan_deploy" for i in catalog)
    plan = _post(base + "/api/dry-run", {
        "intent_key": "vlan_deploy", "intent": {"vlans": "10,20", "description": "Users"},
        "device_hosts": ["192.0.2.1"]})
    assert plan["ok"] and plan["plan"][0]["commands"]


def test_rest_apply_requires_confirm(api):
    svc, _ = api
    base = f"http://127.0.0.1:{svc._server.server_address[1]}"
    payload = {"intent_key": "vlan_deploy", "intent": {"vlans": "10"},
               "device_hosts": ["192.0.2.1"]}
    with pytest.raises(urllib.error.HTTPError) as ctx:
        _post(base + "/api/apply", payload)       # 无 confirm → 400 拒绝
    assert ctx.value.code == 400
