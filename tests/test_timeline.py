"""时间线聚合测试（事件 + 配置快照 + 意图运行）。"""

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
from netwright.sdn.backup import ConfigBackup
from netwright.sdn.timeline import build_timeline


def _store(tmp_path):
    inv = Inventory(str(tmp_path / "dev.json"))
    inv.add(Device(host="192.0.2.1", vendor="huawei", hostname="核心A"))
    return ControllerStore(inv, auth=TokenAuth("t"),
                           backups=ConfigBackup(str(tmp_path)))


def test_timeline_merges_three_sources(tmp_path):
    store = _store(tmp_path)
    store.bus.publish("link.down", "链路中断", severity="critical", device="核心A")
    store.backups.save("核心A", "sysname A\nvlan 10\n")
    store.lifecycle.create("vlan_deploy", {"vlans": "10"}, store.inventory.devices)

    items = build_timeline(store)
    kinds = {item.kind for item in items}
    assert kinds >= {"event", "backup", "intent"}
    assert items[0].ts >= items[-1].ts, "必须按时间倒序"
    assert any(item.device == "核心A" for item in items)


def test_timeline_respects_limit(tmp_path):
    store = _store(tmp_path)
    for index in range(10):
        store.bus.publish("syslog.message", f"msg {index}")
    assert len(build_timeline(store, limit=3)) == 3


def test_timeline_empty_store_is_empty(tmp_path):
    store = _store(tmp_path)
    assert build_timeline(store) == []


def test_nbapi_timeline_route(tmp_path):
    store = _store(tmp_path)
    store.bus.publish("link.up", "链路恢复", device="核心A")
    status, body = nbapi.dispatch(store, "GET", "/api/v2/timeline?limit=5",
                                  headers={"Authorization": "Bearer t"})
    assert status == 200 and body["ok"]
    assert body["items"] and body["items"][0]["kind"] == "event"
    status, _ = nbapi.dispatch(store, "GET", "/api/v2/timeline")
    assert status == 401
