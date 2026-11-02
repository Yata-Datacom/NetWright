"""易用性相关回归测试：演示数据 / 清单迁移 / CSV 脱敏 / 协议持久化 / 设置迁移。"""

from __future__ import annotations

import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)


from netwright import demo
from netwright.lib import settings as settings_mod
from netwright.lib.inventory import Device, Inventory


# ── 协议持久化（v3.9 的回归 bug）──────────────────────────────────
def test_device_protocol_survives_roundtrip():
    device = Device(host="192.0.2.1", protocol="telnet", username="u", password="p")
    restored = Device.from_storage(device.to_storage())
    assert restored.protocol == "telnet", "Telnet 设备重启后不能退回 ssh"


def test_inventory_persists_protocol(tmp_path):
    path = str(tmp_path / "dev.json")
    inv = Inventory(path)
    inv.add(Device(host="192.0.2.1", protocol="telnet", hostname="A"))
    again = Inventory(path)
    assert again.devices[0].protocol == "telnet"


# ── CSV 导出默认脱敏 ───────────────────────────────────────────────
def test_export_csv_hides_password_by_default(tmp_path):
    inv = Inventory(str(tmp_path / "dev.json"))
    inv.add(Device(host="192.0.2.1", username="admin", password="Secret!123"))
    plain = inv.export_csv()
    backup = inv.export_csv(include_secrets=True)
    assert "Secret!123" not in plain
    assert "Secret!123" in backup


# ── 同一设备多行 CSV（每行一条链路）────────────────────────────────
def test_import_csv_multi_row_same_host_keeps_links(tmp_path):
    inv = Inventory(str(tmp_path / "dev.json"))
    text = ("host,vendor,hostname,local_intf,peer_device,peer_intf\n"
            "192.0.2.1,huawei,核心A,GE0/0/1,核心B,GE0/0/1\n"
            "192.0.2.1,huawei,核心A,GE0/0/2,核心C,GE0/0/1\n")
    added, warns = inv.import_csv(text)
    assert added == 1, "同一设备只应添加一次"
    assert not warns, "带链路信息的重复行不该产生告警"
    assert len(inv.links) == 2, "两行链路都要收下"


def test_import_csv_pure_duplicate_still_warns(tmp_path):
    inv = Inventory(str(tmp_path / "dev.json"))
    text = "host,vendor\n192.0.2.1,huawei\n192.0.2.1,huawei\n"
    added, warns = inv.import_csv(text)
    assert added == 1 and len(warns) == 1


# ── 旧文件名迁移 ───────────────────────────────────────────────────
def test_inventory_migrates_netforge_file(tmp_path):
    legacy = tmp_path / "netforge_devices.json"
    legacy.write_text(json.dumps({
        "version": 1,
        "devices": [{"host": "192.0.2.9", "port": 22, "vendor": "huawei",
                     "hostname": "老核心", "password": "plain:OTI="}],
    }, ensure_ascii=False), encoding="utf-8")
    inv = Inventory(str(tmp_path / "netwright_devices.json"))
    assert [d.host for d in inv.devices] == ["192.0.2.9"]
    assert (tmp_path / "netwright_devices.json").is_file(), "应写出新格式文件"


def test_settings_migrates_legacy_theme_key(tmp_path):
    (tmp_path / "netwright_settings.json").write_text(
        json.dumps({"theme": "浅色 · 亮", "rest_port": 8899}, ensure_ascii=False),
        encoding="utf-8")
    data = settings_mod.load_settings(str(tmp_path))
    assert "theme" not in data
    assert data["theme_mode"] == "light"
    assert data["auto_refresh"] is True, "默认应开启自动刷新"


def test_settings_migrates_legacy_filename(tmp_path):
    (tmp_path / "netforge_settings.json").write_text(
        json.dumps({"theme_mode": "dark", "last_page": "topology"}), encoding="utf-8")
    data = settings_mod.load_settings(str(tmp_path))
    assert data["theme_mode"] == "dark" and data["last_page"] == "topology"


# ── 演示数据 ───────────────────────────────────────────────────────
def test_demo_seed_is_idempotent_and_clears(tmp_path):
    inv = Inventory(str(tmp_path / "dev.json"))
    first_devices, first_links = demo.seed(inv)
    assert first_devices == len(demo.DEMO_DEVICES) and first_links > 0
    again = demo.seed(inv)
    assert again == (0, 0), "重复载入不应重复添加"
    assert demo.is_demo_loaded(inv)
    removed = demo.clear(inv)
    assert removed == len(demo.DEMO_DEVICES)
    assert not inv.devices


def test_demo_uses_documentation_network_only():
    for device in demo.DEMO_DEVICES:
        assert device.host.startswith("192.0.2."), "演示数据只能用 RFC 5737 文档网段"
    assert any(d.protocol == "telnet" for d in demo.DEMO_DEVICES), \
        "演示数据应覆盖 Telnet，方便验证协议列"


def test_demo_seed_keeps_user_devices(tmp_path):
    inv = Inventory(str(tmp_path / "dev.json"))
    inv.add(Device(host="10.0.0.1", hostname="我的设备"))
    demo.seed(inv)
    hosts = [d.host for d in inv.devices]
    assert "10.0.0.1" in hosts and "192.0.2.11" in hosts


# ── 图模型 clear ───────────────────────────────────────────────────
def test_graph_clear():
    from netwright.sdn.model import NetworkGraph

    graph = NetworkGraph()
    graph.add_edge("A", "B", "Gi0/1", "Gi0/2")
    graph.clear()
    assert graph.nodes == {} and graph.edges == []
    graph.add_edge("A", "B", "Gi0/1", "Gi0/2")
    assert len(graph.edges) == 1, "clear 后应能重新加同一条边"
