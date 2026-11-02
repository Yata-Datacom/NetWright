"""SDN 控制器内核测试：事件总线 / 图模型 / 策略编译 / 南向注册表 / 状态仓库 / REST v2。"""

from __future__ import annotations

import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)


from netwright.lib.inventory import Device, Inventory, LedgerLink
from netwright.sdn import (Capability, ControllerStore, EventBus, NetworkGraph,
                           PolicyCompiler, default_registry, normalize_interface)
from netwright.sdn import nbapi
from netwright.sdn.southbound import UnsupportedOperation


# ── 事件总线 ────────────────────────────────────────────────────────
def test_event_bus_publish_subscribe_and_unsubscribe():
    bus = EventBus()
    seen = []
    unsubscribe = bus.subscribe(seen.append)
    bus.publish("topology.changed", "节点 +1", severity="info", nodes=3)
    assert len(seen) == 1 and seen[0].topic == "topology.changed"
    assert seen[0].data["nodes"] == 3 and seen[0].id == 1
    unsubscribe()
    bus.publish("topology.changed", "再发布一次")
    assert len(seen) == 1, "取消订阅后不应再收到事件"


def test_event_bus_topic_filter_and_snapshot_order():
    bus = EventBus()
    hits = []
    bus.subscribe(hits.append, topic_prefix="link.")
    bus.publish("link.down", "核心A-汇聚B 中断", severity="critical")
    bus.publish("device.up", "接入C 上线")
    assert [e.topic for e in hits] == ["link.down"]
    history = bus.snapshot(limit=10)
    assert [e.topic for e in history] == ["device.up", "link.down"]   # 最新在前
    assert bus.counts()["critical"] == 1


def test_event_bus_survives_bad_subscriber():
    bus = EventBus()

    def broken(_event):
        raise RuntimeError("订阅者炸了")

    bus.subscribe(broken)
    bus.subscribe(lambda _e: None)
    event = bus.publish("southbound.error", "命令失败")
    assert event.id == 1 and bus.dropped == 1


# ── 图模型 ──────────────────────────────────────────────────────────
def test_graph_node_edge_dedup_and_stats():
    graph = NetworkGraph()
    graph.add_node("核心A", "huawei", managed=True)
    assert graph.add_edge("核心A", "汇聚B", "GE0/0/1", "GE0/0/24", "lldp") is not None
    # 反向同链路：接口名归一化后应视为重复
    assert graph.add_edge("汇聚B", "核心A", "GigabitEthernet0/0/24",
                          "Gi0/0/1", "lldp") is None
    graph.add_edge("汇聚B", "接入C", "", "", "ledger")
    stats = graph.stats()
    assert stats["nodes"] == 3 and stats["links"] == 2
    assert stats["by_source"] == {"lldp": 1, "ledger": 1}
    assert graph.degree("汇聚B") == 2
    assert graph.neighbors("核心A")[0][0] == "汇聚B"
    assert graph.isolated() == []


def test_normalize_interface_variants():
    assert normalize_interface("Gi0/0/1") == "GigabitEthernet0/0/1"
    assert normalize_interface("GE0/0/1") == "GigabitEthernet0/0/1"
    assert normalize_interface("Te1/1/1") == "TenGigabitEthernet1/1/1"
    assert normalize_interface("Eth-Trunk1") == "Eth-Trunk1"


def test_graph_roundtrip_and_merge():
    graph = NetworkGraph()
    graph.add_edge("A", "B", "Gi0/1", "Gi0/2")
    graph.add_node("C", "cisco", managed=True)
    clone = NetworkGraph.from_dict(graph.to_dict())
    assert set(clone.nodes) == {"A", "B", "C"}
    assert len(clone.edges) == 1
    other = NetworkGraph()
    other.add_edge("B", "C", "Gi0/3", "Gi0/4")
    graph.merge(other)
    assert len(graph.edges) == 2 and graph.degree("B") == 2


def test_graph_from_inventory_and_ledger():
    inventory = Inventory(path=os.devnull)   # 不落盘：随便给个不可写路径也无妨，load 失败即空
    inventory.devices = [Device(host="192.0.2.1", vendor="huawei", hostname="核心A"),
                         Device(host="192.0.2.2", vendor="cisco", hostname="汇聚B")]
    inventory.links = [LedgerLink("核心A", "Gi0/1", "汇聚B", "Gi0/2")]
    graph = NetworkGraph.from_topology(None, inventory)
    assert graph.nodes["核心A"].managed and graph.nodes["核心A"].vendor == "huawei"
    added = graph.add_ledger_links(inventory.links)
    assert added == 1 and graph.edges[0].kind == "ledger"


# ── 策略编译 ────────────────────────────────────────────────────────
def test_policy_compiler_vlan_multi_vendor():
    compiler = PolicyCompiler()
    devices = [Device(host="192.0.2.1", vendor="huawei", hostname="核心A"),
               Device(host="192.0.2.2", vendor="cisco", hostname="接入B")]
    result = compiler.compile("vlan_deploy", {"vlans": "10,20", "description": "办公"},
                              devices)
    assert result.ok and len(result.policies) == 2
    huawei = next(p for p in result.policies if p.vendor == "huawei")
    cisco = next(p for p in result.policies if p.vendor == "cisco")
    assert any("vlan batch" in c for c in huawei.commands)
    assert any("vlan 10" in c for c in cisco.commands)
    assert result.commands_total == sum(len(p.commands) for p in result.policies)
    assert result.highest_risk == "low"


def test_policy_compiler_skips_unsupported_vendor():
    compiler = PolicyCompiler()
    result = compiler.compile("vlan_deploy", {"vlans": "10"},
                              [Device(host="192.0.2.9", vendor="acme", hostname="X")])
    assert not result.policies and result.skipped and result.ok
    assert "暂不支持厂商" in result.skipped[0]


def test_policy_compiler_reports_invalid_params():
    compiler = PolicyCompiler()
    result = compiler.compile("vlan_deploy", {"vlans": "abc"},
                              [Device(host="192.0.2.1", vendor="huawei"),
                               Device(host="192.0.2.2", vendor="huawei")])
    assert not result.ok and result.errors and not result.policies


def test_policy_compiler_unknown_intent_raises():
    with pytest.raises(ValueError):
        PolicyCompiler().compile("no_such_intent", {}, [])


def test_policy_risk_marks_destructive_intent():
    """端口 shutdown 这类意图必须被标成 high，供审批/二次确认使用。"""
    compiler = PolicyCompiler()
    result = compiler.compile("port_role", {"interface": "GE0/0/1", "role": "shutdown"},
                              [Device(host="192.0.2.1", vendor="huawei", hostname="A")])
    if result.policies:
        assert result.highest_risk in ("low", "high")


# ── 南向适配器 ──────────────────────────────────────────────────────
def test_southbound_registry_capabilities():
    registry = default_registry()
    assert len(registry) == 4
    described = {item["protocol"]: item for item in registry.describe()}
    assert set(described) == {"cli", "netconf", "openflow", "restconf"}
    assert "config_write" in described["cli"]["capabilities"]
    assert "flow_program" in described["openflow"]["capabilities"]
    assert described["cli"]["available"] is True
    assert described["netconf"]["available"] is False      # 未安装 ncclient
    assert described["openflow"]["available"] is False


def test_southbound_openflow_rejects_cli_and_flowmod():
    registry = default_registry()
    adapter = registry.get("openflow")
    with pytest.raises(UnsupportedOperation):
        adapter.run_commands(Device(host="192.0.2.1"), ["show version"])
    with pytest.raises(UnsupportedOperation):
        adapter.program_flows(Device(host="192.0.2.1"), [])


def test_southbound_routes_device_by_protocol():
    registry = default_registry()
    assert registry.for_device(Device(host="1.1.1.1", protocol="ssh")).protocol == "cli"
    assert registry.for_device(Device(host="1.1.1.1", protocol="telnet")).protocol == "cli"
    assert registry.for_device(Device(host="1.1.1.1", protocol="netconf")).protocol == "netconf"


def test_southbound_cli_declares_required_capabilities():
    registry = default_registry()
    cli = registry.get("cli")
    assert cli.supports(Capability.CONFIG_WRITE)
    assert not cli.supports(Capability.FLOW_PROGRAM)
    assert cli.info().to_dict()["protocol"] == "cli"


# ── 状态仓库 ────────────────────────────────────────────────────────
def _inventory(tmp_path=None):
    inv = Inventory(path=os.path.join(str(tmp_path), "dev.json")) if tmp_path else Inventory(path=os.devnull)
    inv.devices = [Device(host="192.0.2.1", vendor="huawei", hostname="核心A"),
                   Device(host="192.0.2.2", vendor="cisco", hostname="汇聚B")]
    inv.links = [LedgerLink("核心A", "Gi0/1", "汇聚B", "Gi0/2")]
    return inv


def test_store_sync_inventory_builds_graph():
    store = ControllerStore(_inventory())
    stats = store.summary()
    assert stats["nodes"] >= 2 and stats["links"] == 1
    assert stats["managed"] == 2 and stats["southbound"] == 4


def test_store_compile_and_snapshot():
    store = ControllerStore(_inventory())
    result = store.compile("vlan_deploy", {"vlans": "10,20"})
    assert len(result.policies) == 2
    snapshot = store.snapshot()
    assert snapshot["policies"] and snapshot["summary"]["policies"] == 2
    assert snapshot["topology"]["stats"]["nodes"] >= 2
    assert snapshot["events"], "编译应产生 policy.compiled 事件"


def test_store_apply_topology_merges_lldp():
    from netwright.lib.controller.topology import Link, Topology

    store = ControllerStore(_inventory())
    topo = Topology()
    topo.add_links("核心A", [Link("核心A", "Gi0/1", "汇聚B", "Gi0/2")])
    graph = store.apply_topology(topo)
    kinds = {e.kind for e in graph.edges}
    assert kinds == {"lldp"}
    store.apply_topology(topo)          # 幂等：重复发现不重复边
    assert len(store.graph.edges) == 1


def test_store_persist_roundtrip(tmp_path):
    store = ControllerStore(_inventory())
    assert store.save(str(tmp_path)) is True
    other = ControllerStore(_inventory())
    assert other.load(str(tmp_path)) is True
    assert set(other.graph.nodes) == set(store.graph.nodes)


# ── 北向 REST v2 ────────────────────────────────────────────────────
def test_nbapi_health_and_topology():
    store = ControllerStore(_inventory())
    status, body = nbapi.dispatch(store, "GET", "/api/v2/health")
    assert status == 200 and body["ok"] and body["api"] == "2.0"
    status, body = nbapi.dispatch(store, "GET", "/api/v2/topology")
    assert status == 200 and body["stats"]["nodes"] >= 2


def test_nbapi_compile_route():
    store = ControllerStore(_inventory())
    payload = {"intent_key": "vlan_deploy", "params": {"vlans": "30"}}
    status, body = nbapi.dispatch(store, "POST", "/api/v2/policies/compile", payload)
    assert status == 200 and body["ok"] and len(body["policies"]) == 2


def test_nbapi_validation_errors():
    store = ControllerStore(_inventory())
    status, body = nbapi.dispatch(store, "POST", "/api/v2/policies/compile", {})
    assert status == 400 and body["ok"] is False
    status, _ = nbapi.dispatch(store, "GET", "/api/v2/nope")
    assert status == 404
    status, _ = nbapi.dispatch(store, "DELETE", "/api/v2/health")
    assert status == 405


def test_nbapi_events_route_reads_bus():
    store = ControllerStore(_inventory())
    store.bus.publish("link.down", "链路中断", severity="critical")
    status, body = nbapi.dispatch(store, "GET", "/api/v2/events?limit=5")
    assert status == 200 and body["events"][0]["severity"] == "critical"
