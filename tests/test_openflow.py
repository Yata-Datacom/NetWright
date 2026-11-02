"""OpenFlow 1.3 流表校验与 flow_mod 编码测试（不连交换机）。"""

from __future__ import annotations

import os
import struct
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)


from netwright.lib.inventory import Device, Inventory
from netwright.sdn import ControllerStore, nbapi
from netwright.sdn.auth import TokenAuth
from netwright.sdn.southbound.openflow import (FlowEntry, FlowError, OFT_FLOW_MOD,
                                               OFP_VERSION_13, OpenFlowAdapter)


def test_flow_mod_header_and_length():
    entry = FlowEntry(priority=200, match={"in_port": 1, "eth_type": 0x0800},
                      actions=[{"type": "output", "port": 2}])
    payload = entry.encode(xid=42)
    version, msg_type, length, xid = struct.unpack("!BBHI", payload[:8])
    assert version == OFP_VERSION_13 and msg_type == OFT_FLOW_MOD
    assert length == len(payload) and xid == 42
    assert len(payload) % 8 == 0, "OpenFlow 报文必须 8 字节对齐"


def test_vlan_vid_sets_present_bit():
    entry = FlowEntry(match={"vlan_vid": 100}, actions=[{"type": "output", "port": 1}])
    hexdump = entry.hexdump()
    assert "10" in hexdump  # 0x1064 = present|100，至少能确认编码里带了标志位
    assert entry.to_dict()["match"]["vlan_vid"] == 100


def test_drop_flow_has_no_actions():
    entry = FlowEntry(match={"eth_type": 0x0806}, actions=[{"type": "drop"}])
    payload = entry.encode()
    assert len(payload) > 40


@pytest.mark.parametrize("kwargs, message", [
    ({"match": {"nope": 1}, "actions": [{"type": "output", "port": 1}]}, "不支持的 match 字段"),
    ({"match": {"eth_src": "zz:zz:zz:zz:zz:zz"},
      "actions": [{"type": "output", "port": 1}]}, "MAC 格式"),
    ({"priority": 70000, "match": {"in_port": 1},
      "actions": [{"type": "output", "port": 1}]}, "priority"),
    ({"match": {"in_port": 1}, "actions": [{"type": "drop"}, {"type": "output", "port": 1}]},
     "drop 不能和其他动作混用"),
    ({"match": {"in_port": 1}, "actions": []}, "动作不能为空"),
    ({"match": {"in_port": 1}, "actions": [{"type": "flood"}]}, "不支持的动作"),
])
def test_validation_errors(kwargs, message):
    with pytest.raises(FlowError) as exc:
        FlowEntry(**kwargs)
    assert message in str(exc.value)


def test_adapter_build_and_refuse_transport():
    adapter = OpenFlowAdapter()
    flows = [{"table": 0, "priority": 100, "match": {"in_port": 1},
              "actions": [{"type": "output", "port": 2}]},
             {"table": 0, "priority": 50, "match": {"eth_type": 0x0806},
              "actions": [{"type": "drop"}]}]
    compiled = adapter.build_flow_mods(flows)
    assert len(compiled) == 2
    assert all(item["hex"] and item["bytes"] % 8 == 0 for item in compiled)
    from netwright.sdn.southbound import UnsupportedOperation

    with pytest.raises(UnsupportedOperation) as exc:
        adapter.program_flows(Device(host="192.0.2.1"), flows)
    assert "已校验并编码 2 条" in str(exc.value)


def test_nbapi_openflow_validate(tmp_path):
    inv = Inventory(str(tmp_path / "dev.json"))
    store = ControllerStore(inv, auth=TokenAuth("t"))
    headers = {"Authorization": "Bearer t"}
    flow = {"match": {"in_port": 1}, "actions": [{"type": "output", "port": 2}]}
    status, body = nbapi.dispatch(store, "POST", "/api/v2/openflow/validate",
                                  {"flows": [flow]}, headers=headers)
    assert status == 200 and body["count"] == 1
    assert body["compiled"][0]["bytes"] % 8 == 0

    status, body = nbapi.dispatch(store, "POST", "/api/v2/openflow/validate",
                                  {"flows": [{"match": {"bad": 1}, "actions": []}]},
                                  headers=headers)
    assert status == 400 and body["ok"] is False

    status, _ = nbapi.dispatch(store, "POST", "/api/v2/openflow/validate",
                               {"flows": [flow]})
    assert status == 401
