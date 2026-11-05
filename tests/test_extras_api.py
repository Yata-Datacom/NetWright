"""新 REST 路由：合规扫描 / 意图目录 / 路径追踪 / 异步任务。"""
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

HEADERS = {"Authorization": "Bearer t"}


def _store(tmp_path):
    inventory = Inventory(str(tmp_path / "dev.json"))
    inventory.add(Device(host="192.0.2.1", vendor="huawei", hostname="核心A"))
    return ControllerStore(inventory, auth=TokenAuth("t"))


def test_catalog_route_requires_token(tmp_path):
    store = _store(tmp_path)
    status, _ = nbapi.dispatch(store, "GET", "/api/v2/catalog")
    assert status == 401
    status, body = nbapi.dispatch(store, "GET", "/api/v2/catalog", headers=HEADERS)
    assert status == 200 and body["entries"]


def test_catalog_plan_route(tmp_path):
    store = _store(tmp_path)
    status, body = nbapi.dispatch(store, "POST", "/api/v2/catalog/plan",
                                  {"key": "vlan_add", "vendor": "huawei",
                                   "params": {"vlan_id": "300"}}, headers=HEADERS)
    assert status == 200
    assert body["plan"]["commands"] == ["vlan 300", "quit"]
    status, body = nbapi.dispatch(store, "POST", "/api/v2/catalog/plan",
                                  {"key": "vlan_add", "params": {}}, headers=HEADERS)
    assert status == 400 and "缺少必填参数" in body["message"]


def test_compliance_scan_with_inline_config(tmp_path):
    store = _store(tmp_path)
    config = "sysname A\ntelnet server enable\n"
    status, body = nbapi.dispatch(store, "POST", "/api/v2/compliance/scan",
                                  {"configs": [{"device": "A", "text": config}]},
                                  headers=HEADERS)
    assert status == 200
    result = body["results"][0]
    assert result["device"] == "A"
    assert any(f["rule_id"] == "telnet.enabled" for f in result["findings"])
    assert result["score"] < 100
    status, _ = nbapi.dispatch(store, "POST", "/api/v2/compliance/scan", {},
                               headers=HEADERS)
    assert status == 400


def test_topology_path_route(tmp_path):
    store = _store(tmp_path)
    store.graph.add_edge("核心A", "接入B", "Gi0/1", "Gi0/2")
    status, body = nbapi.dispatch(store, "POST", "/api/v2/topology/path",
                                  {"src": "核心A", "dst": "接入B"}, headers=HEADERS)
    assert status == 200 and body["path"]["reachable"]
    assert body["path"]["description"].startswith("核心A → 接入B")
    status, _ = nbapi.dispatch(store, "POST", "/api/v2/topology/path",
                               {"src": "核心A"}, headers=HEADERS)
    assert status == 400


def test_tasks_route_lists_and_404s(tmp_path):
    store = _store(tmp_path)
    task_id = store.tasks.submit("demo", lambda: 1)
    store.tasks.wait(task_id, timeout=5)
    status, body = nbapi.dispatch(store, "GET", "/api/v2/tasks", headers=HEADERS)
    assert status == 200 and any(t["id"] == task_id for t in body["tasks"])
    status, body = nbapi.dispatch(store, "GET", f"/api/v2/tasks/{task_id}",
                                  headers=HEADERS)
    assert status == 200 and body["task"]["state"] == "done"
    status, _ = nbapi.dispatch(store, "GET", "/api/v2/tasks/nope", headers=HEADERS)
    assert status == 404
