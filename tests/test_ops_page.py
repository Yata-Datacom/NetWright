"""运维中心页面（合规/路径/漂移）——冒烟与行为测试。"""
from __future__ import annotations

import json
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from netwright.app import NetWrightApp
from netwright.lib.inventory import Device
from netwright.sdn.backup import ConfigBackup

BAD = "sysname SW-1\ntelnet server enable\nline vty 0 4\n"


@pytest.fixture()
def app(tmp_path, monkeypatch):
    try:
        instance = NetWrightApp()
    except Exception as exc:      # noqa: BLE001
        pytest.skip(f"GUI 不可用：{exc}")
    instance.withdraw()
    # 隔离数据目录，避免污染真实配置
    instance.controller_store.backups = ConfigBackup(str(tmp_path / "backups"))
    instance.inventory.devices = []
    yield instance
    try:
        instance.controller_api.stop()
    except Exception:             # noqa: BLE001
        pass
    try:
        instance.destroy()
    except Exception:             # noqa: BLE001
        pass


def test_ops_page_registered_and_builds(app):
    app.show("ops")
    page = app.pages["ops"]
    assert page is not None
    assert page.table.tree.get_children() == ()


def test_compliance_lists_findings_from_latest_backup(app):
    app.inventory.add(Device(host="192.0.2.9", hostname="SW-9", note="测试"))
    app.controller_store.backups.save("192.0.2.9", BAD)
    page = app.pages["ops"]
    page.refresh()
    page.var_device.set("SW-9 (192.0.2.9)")
    page.run_compliance()
    rows = page.table.tree.get_children()
    assert rows, "应至少列出一条命中"
    values = [page.table.tree.item(r, "values") for r in rows]
    assert any("telnet" in str(v).lower() for v in values)


def test_compliance_without_backup_shows_hint(app):
    app.inventory.add(Device(host="192.0.2.8", hostname="SW-8", note="测试"))
    page = app.pages["ops"]
    page.refresh()
    page.var_device.set("SW-8 (192.0.2.8)")
    page.run_compliance()
    assert "先到" in page.var_score.get()


def test_path_trace_reports_reachable(app):
    graph = app.controller_store.graph
    graph.add_edge("A", "B", "Gi0/1", "Gi0/2")
    page = app.pages["ops"]
    page.refresh()
    page.var_src.set("A")
    page.var_dst.set("B")
    page.run_path()
    assert page.var_path.get().startswith("A → B")


def test_topology_path_highlight(app):
    graph = app.controller_store.graph
    graph.add_edge("A", "B", "Gi0/1", "Gi0/2")
    app.show("topology")
    page = app.pages["topology"]
    text = page.show_path("A", "B")
    assert text.startswith("A → B")
    assert page._path_nodes == {"A", "B"}


def test_catalog_tab_generates_commands(app):
    page = app.pages["controller"]
    page.cmb_catalog.current(0)
    page._catalog_params()
    page._param_vars["vlan_id"].set("123")
    page._catalog_preview()
    text = page.txt_catalog.get("1.0", "end")
    assert "vlan 123" in text
    assert "风险等级" in text


def test_catalog_tab_reports_validation_errors(app):
    page = app.pages["controller"]
    page.cmb_catalog.current(0)
    page._catalog_params()
    page._param_vars["vlan_id"].set("")
    page._catalog_preview()
    assert "vlan" not in page.txt_catalog.get("1.0", "end").lower()


def test_drift_daily_toggle_persists(app):
    page = app.pages["ops"]
    page.var_drift_hours.set("6")
    page.var_drift_daily.set(True)
    page._toggle_daily()
    assert app.settings["drift_daily"] is True
    assert app.settings["drift_hours"] == 6.0
    page.var_drift_daily.set(False)
    page._toggle_daily()
    assert app.settings["drift_daily"] is False


def test_path_trace_unreachable_is_explicit(app):
    page = app.pages["ops"]
    page.var_src.set("X")
    page.var_dst.set("Y")
    page.run_path()
    assert "不可达" in page.var_path.get()

def test_catalog_adopt_creates_lifecycle_runs(app):
    from netwright.lib.inventory import Device

    app.inventory.add(Device(host="192.0.2.77", hostname="SW-77", vendor="huawei",
                             note="测试"))
    page = app.pages["controller"]
    page.cmb_catalog.current(0)
    page._catalog_params()
    page._param_vars["vlan_id"].set("321")
    page._catalog_adopt()
    runs = list(app.controller_store.lifecycle.runs.values())
    assert runs, "应写入运行档案"
    assert runs[-1].state == "compiled"
    assert "vlan 321" in " ".join(runs[-1].policy.commands)
    assert runs[-1].policy.intent_key == "catalog:vlan_add"
def test_health_card_renders_metrics(app):
    """展示逻辑直接测：异步线程在 pytest 里没有 mainloop，无法走 after 回主线程。"""
    page = app.pages["ops"]
    assert hasattr(page, "btn_health")
    page._health_done({"ok": True, "values": {}, "errors": {"cpu_1min": "TimeoutError"},
                       "cpu_util": 21, "mem_util": 63.5, "uptime_hours": 12.0})
    text = page.var_health.get()
    assert "CPU 21%" in text and "63.5%" in text and "失败 1 项" in text


def test_health_card_reports_failure(app):
    page = app.pages["ops"]
    page._health_done({"ok": False, "error": "socket.timeout: timed out"})
    assert "采样失败" in page.var_health.get()


def test_health_example_rules_file_is_valid():
    from netwright.lib.compliance import load_rules

    path = os.path.join(ROOT, "templates", "compliance.example.json")
    data = json.load(open(path, encoding="utf-8"))
    assert len(data["rules"]) >= 8
    assert len(load_rules(path)) >= 8