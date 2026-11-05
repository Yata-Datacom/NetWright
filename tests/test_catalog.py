"""意图目录（D）：参数校验、厂商差异、反向命令。"""
from __future__ import annotations

import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from netwright.sdn.catalog import build_commands, describe


def test_catalog_lists_all_entries_with_params():
    entries = describe()
    keys = {e["key"] for e in entries}
    assert {"vlan_add", "port_desc", "port_toggle", "lacp", "acl_allow"} <= keys
    assert all(e["params"] for e in entries)


def test_vlan_add_huawei_vs_cisco():
    huawei = build_commands("vlan_add", {"vlan_id": "200", "name": "办公"}, "huawei")
    assert huawei["commands"] == ["vlan 200", " name 办公", "quit"]
    assert huawei["reverse"] == ["undo vlan 200"]

    cisco = build_commands("vlan_add", {"vlan_id": "200"}, "cisco")
    assert cisco["commands"] == ["vlan 200", "exit"]
    assert cisco["reverse"] == ["no vlan 200"]


def test_port_toggle_generates_reverse():
    down = build_commands("port_toggle", {"interface": "Gi0/1", "state": "down"}, "cisco")
    assert " shutdown" in down["commands"]
    assert " no shutdown" in down["reverse"]


def test_port_desc_has_no_safe_reverse():
    result = build_commands("port_desc", {"interface": "Gi0/1", "description": "上联-核心"},
                            "cisco")
    assert any("description 上联-核心" in c for c in result["commands"])
    assert result["reverse"] == [], "旧描述未知，不能假装能还原"


def test_lacp_two_members():
    result = build_commands("lacp", {"interfaces": "Gi0/1, Gi0/2", "group": "10"}, "huawei")
    text = "\n".join(result["commands"])
    assert text.count("eth-trunk 10") == 2


def test_acl_allow_huawei_uses_acl_number():
    result = build_commands("acl_allow", {"acl_id": "3000", "src": "10.0.0.0 0.0.0.255",
                                          "dst": "192.168.1.0 0.0.0.255"}, "huawei")
    assert result["commands"][0] == "acl number 3000"
    assert "rule permit ip" in result["commands"][1]


@pytest.mark.parametrize("key, params, message", [
    ("vlan_add", {}, "缺少必填参数"),
    ("vlan_add", {"vlan_id": "5000"}, "VLAN ID 越界"),
    ("port_toggle", {"interface": "Gi0/1", "state": "half"}, "state 只能是"),
    ("nope", {}, "未知意图"),
])
def test_validation_errors(key, params, message):
    with pytest.raises(ValueError) as exc:
        build_commands(key, params, "huawei")
    assert message in str(exc.value)


def test_unknown_vendor_is_rejected():
    with pytest.raises(ValueError) as exc:
        build_commands("vlan_add", {"vlan_id": "10"}, "juniper")
    assert "不支持的厂商" in str(exc.value)
