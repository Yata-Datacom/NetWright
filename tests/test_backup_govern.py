"""R8 备份治理契约测试：按设备保留份数 / 导出 zip（manifest）/ 目录迁移。"""

from __future__ import annotations

import json
import os
import sys
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)


from netwright.lib.inventory import Device, Inventory
from netwright.sdn import ControllerStore
from netwright.sdn.backup import ConfigBackup

CONFIGS = [f"sysname SW\nvlan {i}\n" for i in range(1, 6)]   # 5 份不同内容


def _backup(tmp_path, **kw) -> ConfigBackup:
    return ConfigBackup(str(tmp_path / "bk"), **kw)


def test_per_device_keep_overrides_global(tmp_path):
    """按设备设保留份数：A=2 立即生效，B 仍用全局 keep。"""
    backup = _backup(tmp_path, keep=4)
    for i, text in enumerate(CONFIGS):
        backup.save("A", text)
        backup.save("B", f"sysname B\nvlan {i}\n")
    assert len(backup.history("A")) == 4 and len(backup.history("B")) == 4

    backup.set_device_keep("A", 2)
    assert len(backup.history("A")) == 2, "A 的保留份数应立即生效"
    assert len(backup.history("B")) == 4, "B 不受 A 的设置影响"


def test_export_zip_contains_manifest_with_sha256(tmp_path):
    """导出 zip 含 manifest.json（设备/时间/sha256），sha256 与历史一致。"""
    backup = _backup(tmp_path)
    first = backup.save("CoreA", CONFIGS[0])
    backup.save("CoreA", CONFIGS[1])
    backup.save("CoreB", CONFIGS[2])

    out = str(tmp_path / "export.zip")
    result = backup.export_zip(out)
    assert result["snapshots"] == 3 and result["devices"] == 2
    with zipfile.ZipFile(out) as zf:
        assert "manifest.json" in zf.namelist()
        manifest = json.loads(zf.read("manifest.json").decode("utf-8"))
        arcs = [n for n in zf.namelist() if n.endswith(".cfg")]
        assert len(arcs) == 3
        for name in arcs:
            assert zf.read(name), "快照内容不应为空"
    # manifest 以 (设备, 文件名) 定位（归档目录名经过文件名净化）
    by_key = {(e["device"], os.path.basename(e["file"])): e
              for e in manifest["entries"]}
    assert by_key[("CoreA", first.filename)]["sha256"] == first.sha256
    assert all(e["time"] and e["device"] for e in manifest["entries"])


def test_export_zip_can_filter_devices(tmp_path):
    backup = _backup(tmp_path)
    backup.save("A", CONFIGS[0])
    backup.save("B", CONFIGS[1])
    out = str(tmp_path / "only-a.zip")
    result = backup.export_zip(out, devices=["A"])
    assert result["snapshots"] == 1 and result["devices"] == 1


def test_migrate_moves_root_when_target_free(tmp_path):
    """同盘且新位置空闲 → 整个 backups/ 原子搬移，历史完整、旧目录消失。"""
    backup = _backup(tmp_path)
    backup.save("核心A", CONFIGS[0])
    old_root = backup.root
    assert os.path.isdir(old_root)

    result = backup.migrate_root(str(tmp_path / "newbase"))
    assert result["moved"] is True
    assert not os.path.exists(old_root), "旧目录应被搬走（不再写入）"
    assert len(backup.history("核心A")) == 1, "历史完整保留"

    entry = backup.save("核心A", CONFIGS[1])       # 新快照必须落在新目录
    assert entry.path.startswith(result["new"])


def test_migrate_leaves_old_dir_when_target_exists(tmp_path):
    """目标 backups/ 已存在 → 旧目录保留只读，新目录从空开始。"""
    backup = _backup(tmp_path)
    backup.save("核心A", CONFIGS[0])
    old_root = backup.root
    (tmp_path / "newbase" / "backups").mkdir(parents=True)   # 目标根已占用

    result = backup.migrate_root(str(tmp_path / "newbase"))
    assert result["moved"] is False
    assert os.path.isdir(old_root), "旧目录保留（只读）"
    assert backup.history("核心A") == [], "新目录从空开始"
    entry = backup.save("核心A", CONFIGS[1])
    assert entry.path.startswith(result["new"]), "写入只进新目录"


def test_store_set_backup_dir_integration(tmp_path):
    """store.set_backup_dir：新快照进新目录，旧目录不再被写入。"""
    inv = Inventory(str(tmp_path / "dev.json"))
    inv.add(Device(host="192.0.2.1", vendor="huawei", hostname="核心A"))
    store = ControllerStore(inv)
    store.backups = ConfigBackup(str(tmp_path / "old"), bus=store.bus)
    store.backups.save("核心A", CONFIGS[0])
    old_root = store.backups.root
    (tmp_path / "newbase" / "backups").mkdir(parents=True)  # 目标根已占用 → 旧目录保留只读
    old_files = sorted(os.listdir(os.path.join(old_root,
                                               store.backups._safe("核心A"))))

    store.set_backup_dir(str(tmp_path / "newbase"))
    assert store.backups.root != old_root

    class FakeAdapter:
        protocol = "cli"

        def read_config(self, device, timeout=15.0):
            return CONFIGS[1]

    store.registry.for_device = lambda _d: FakeAdapter()
    entry = store.backup_device(inv.devices[0])
    assert entry["path"].startswith(str(tmp_path / "newbase")), "新快照只进新目录"
    assert sorted(os.listdir(os.path.join(old_root,
                                          store.backups._safe("核心A")))) == old_files, \
        "迁移后旧目录不再被写入"
