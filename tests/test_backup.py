"""配置备份与差异测试（Oxidized 式快照）。"""

from __future__ import annotations

import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)


from netwright.lib.inventory import Device, Inventory
from netwright.sdn import ControllerStore, nbapi
from netwright.sdn.auth import TokenAuth
from netwright.sdn.backup import ConfigBackup

CONFIG_V1 = "sysname SW-1\nvlan 10\n"
CONFIG_V2 = "sysname SW-1\nvlan 10\nvlan 20\n"


def test_save_and_history(tmp_path):
    backup = ConfigBackup(str(tmp_path))
    entry = backup.save("SW-1", CONFIG_V1)
    assert entry.changed and os.path.isfile(entry.path)
    assert entry.path.endswith(".cfg")
    history = backup.history("SW-1")
    assert len(history) == 1 and history[0].sha256 == entry.sha256
    assert backup.latest("SW-1").filename == entry.filename


def test_unchanged_content_is_not_stored_again(tmp_path):
    backup = ConfigBackup(str(tmp_path))
    first = backup.save("SW-1", CONFIG_V1)
    second = backup.save("SW-1", CONFIG_V1)
    assert second.changed is False
    assert len(backup.history("SW-1")) == 1
    assert first.sha256 == second.sha256


def test_changed_content_creates_new_snapshot_and_diff(tmp_path):
    backup = ConfigBackup(str(tmp_path))
    backup.save("SW-1", CONFIG_V1)
    entry = backup.save("SW-1", CONFIG_V2)
    assert entry.changed and len(backup.history("SW-1")) == 2
    diff = backup.diff("SW-1")
    assert "+vlan 20" in diff and "--- SW-1/" in diff


def test_diff_requires_two_snapshots(tmp_path):
    backup = ConfigBackup(str(tmp_path))
    backup.save("SW-1", CONFIG_V1)
    assert backup.diff("SW-1") == ""


def test_empty_config_is_rejected(tmp_path):
    backup = ConfigBackup(str(tmp_path))
    with pytest.raises(ValueError):
        backup.save("SW-1", "   \n")


def test_device_name_is_sanitized(tmp_path):
    backup = ConfigBackup(str(tmp_path))
    entry = backup.save("192.0.2.1:22/核心 A", CONFIG_V1)
    assert os.path.dirname(entry.path).startswith(backup.root)
    assert "/" not in os.path.basename(os.path.dirname(entry.path))
    assert backup.devices()


def test_prune_keeps_latest(tmp_path):
    backup = ConfigBackup(str(tmp_path), keep=2)
    for index in range(4):
        backup.save("SW-1", CONFIG_V1 + f"# rev {index}\n")
    assert len(backup.history("SW-1")) == 2
    newest = backup.history("SW-1")[0]
    assert "# rev 3" in backup.read(newest)


def test_diff_text_is_unified():
    diff = ConfigBackup.diff_text("a\nb\n", "a\nc\n", "old", "new")
    assert "--- old" in diff and "+++ new" in diff
    assert "-b" in diff and "+c" in diff


# ── 与控制器/REST 的集成 ──────────────────────────────────────────
class BackupAdapter:
    protocol = "cli"

    def __init__(self, text=CONFIG_V1):
        self.text = text

    def read_config(self, device, timeout=15.0):
        return self.text


def _store(tmp_path, text=CONFIG_V1):
    inv = Inventory(str(tmp_path / "dev.json"))
    inv.add(Device(host="192.0.2.1", vendor="huawei", hostname="核心A"))
    store = ControllerStore(inv, auth=TokenAuth("t"),
                            backups=ConfigBackup(str(tmp_path), keep=5))
    store.registry.for_device = lambda _d: BackupAdapter(text)
    return store


def test_store_backup_device(tmp_path):
    store = _store(tmp_path)
    entry = store.backup_device(store.inventory.devices[0])
    assert entry["changed"] and store.backup_summary()["count"] == 1
    # 第二次内容相同 → 不新增
    again = store.backup_device(store.inventory.devices[0])
    assert again["changed"] is False


def test_store_backup_without_directory(tmp_path):
    inv = Inventory(str(tmp_path / "dev.json"))
    inv.add(Device(host="192.0.2.1"))
    store = ControllerStore(inv)
    with pytest.raises(RuntimeError):
        store.backup_device(store.inventory.devices[0])


def test_nbapi_backup_routes(tmp_path):
    store = _store(tmp_path)
    headers = {"Authorization": "Bearer t"}
    status, body = nbapi.dispatch(store, "POST", "/api/v2/backups", {}, headers=headers)
    assert status == 200 and body["ok"]
    status, body = nbapi.dispatch(store, "GET", "/api/v2/backups", headers=headers)
    assert status == 200 and body["count"] == 1
    status, body = nbapi.dispatch(store, "GET", "/api/v2/backups?device=核心A",
                                  headers=headers)
    assert status == 200 and len(body["entries"]) == 1

    # 内容变化后再备份 → diff 可查
    store.registry.for_device = lambda _d: BackupAdapter(CONFIG_V2)
    nbapi.dispatch(store, "POST", "/api/v2/backups", {}, headers=headers)
    status, body = nbapi.dispatch(store, "GET", "/api/v2/backups/diff?device=核心A",
                                  headers=headers)
    assert status == 200 and "+vlan 20" in body["diff"]


def test_nbapi_backup_requires_device_match(tmp_path):
    store = _store(tmp_path)
    headers = {"Authorization": "Bearer t"}
    status, body = nbapi.dispatch(store, "POST", "/api/v2/backups",
                                  {"device_hosts": ["10.9.9.9"]}, headers=headers)
    assert status == 404 and body["ok"] is False


# ── 现网对比（漂移检测）─────────────────────────────────────────────
def test_diff_against_latest_snapshot(tmp_path):
    backup = ConfigBackup(str(tmp_path))
    backup.save("SW-1", CONFIG_V1)
    diff = backup.diff_against("SW-1", CONFIG_V2)
    assert "+vlan 20" in diff and "现网配置" in diff
    assert not backup.diff_against("SW-1", CONFIG_V1)


def test_diff_against_without_snapshot_raises(tmp_path):
    backup = ConfigBackup(str(tmp_path))
    with pytest.raises(ValueError):
        backup.diff_against("SW-1", CONFIG_V1)


def test_store_compare_live_detects_drift(tmp_path):
    store = _store(tmp_path)
    store.backup_device(store.inventory.devices[0])
    store.registry.for_device = lambda _d: BackupAdapter(CONFIG_V2)
    result = store.compare_live(store.inventory.devices[0])
    assert result["has_changes"] is True and "+vlan 20" in result["diff"]
    assert any(e.topic == "config.drift" for e in store.bus.snapshot(10))


def test_nbapi_live_diff_route(tmp_path):
    store = _store(tmp_path)
    headers = {"Authorization": "Bearer t"}
    nbapi.dispatch(store, "POST", "/api/v2/backups", {}, headers=headers)
    store.registry.for_device = lambda _d: BackupAdapter(CONFIG_V2)
    status, body = nbapi.dispatch(
        store, "GET", "/api/v2/backups/live-diff?device=核心A", headers=headers)
    assert status == 200 and body["has_changes"] is True
    status, body = nbapi.dispatch(
        store, "GET", "/api/v2/backups/live-diff?device=不存在", headers=headers)
    assert status == 404
