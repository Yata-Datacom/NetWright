"""R3 配置回滚契约测试：恢复前自动备份 / 读失败不发命令 / 审计 / 失败不重试。"""

from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)


from netwright.lib.controller import deploy as deploy_mod
from netwright.lib.inventory import Device, Inventory
from netwright.sdn import ControllerStore
from netwright.sdn.backup import ConfigBackup
from netwright.sdn.southbound import CommandOutput

SNAPSHOT = "sysname SW-1\nvlan 10\nvlan 20\n!\n# 注释行\n"
CURRENT = "sysname SW-1\nvlan 99\n"


class FakeRestoreAdapter:
    """可编程假适配器：read_config / run_commands 均可注入结果。"""

    protocol = "cli"

    def __init__(self, config: str = CURRENT, fail: bool = False, read_error=None):
        self.config = config
        self.fail = fail
        self.read_error = read_error
        self.sent: list[list[str]] = []
        self.reads = 0

    def read_config(self, device, timeout=15.0):
        self.reads += 1
        if self.read_error is not None:
            raise self.read_error
        return self.config

    def run_commands(self, device, commands, timeout=15.0):
        self.sent.append(list(commands))
        if self.fail:
            return [CommandOutput(c, "", "mock failure") for c in commands]
        return [CommandOutput(c, "ok", "") for c in commands]


def _store(tmp_path, adapter) -> tuple[ControllerStore, ConfigBackup]:
    inv = Inventory(str(tmp_path / "dev.json"))
    inv.add(Device(host="192.0.2.1", vendor="huawei", hostname="核心A"))
    store = ControllerStore(inv)
    store.registry.for_device = lambda _device: adapter
    backup = ConfigBackup(str(tmp_path / "bk"), bus=store.bus)
    store.backups = backup
    backup.save("核心A", SNAPSHOT)
    return store, backup


def test_restore_pre_backups_current_config(tmp_path):
    """恢复前必须自动 backup_device()，且返回的 pre_backup 可在历史里找到。"""
    adapter = FakeRestoreAdapter(config=CURRENT)
    store, backup = _store(tmp_path, adapter)
    device = store.inventory.devices[0]

    result = store.restore_backup(device, backup.history("核心A")[0].filename)

    assert result["ok"] is True
    assert result["commands"] == 3, "快照里 3 条有效命令（空行/!/注释不计）"
    assert result["error"] == ""
    assert result["pre_backup"], "必须记录恢复前备份文件名"
    pre = [e for e in backup.history("核心A") if e.filename == result["pre_backup"]]
    assert pre, "恢复前备份必须真的落盘"
    assert adapter.sent == [["sysname SW-1", "vlan 10", "vlan 20"]], \
        "命令应去掉空行与注释后原样下发"


def test_restore_aborts_without_sending_when_read_fails(tmp_path):
    """get_config 失败 → 不发任何命令、不做备份，错误说明"未发送任何命令"。"""
    adapter = FakeRestoreAdapter(read_error=OSError("conn refused"))
    store, backup = _store(tmp_path, adapter)
    device = store.inventory.devices[0]

    result = store.restore_backup(device, backup.history("核心A")[0].filename)

    assert result["ok"] is False
    assert adapter.sent == [], "读不到现网配置时绝不能下发"
    assert result["pre_backup"] == ""
    assert "未发送任何命令" in result["error"]


def test_restore_failure_does_not_retry(tmp_path):
    """下发失败不重试第二次（半途状态更危险），只报告；审计记录 FAILED。"""
    adapter = FakeRestoreAdapter(fail=True)
    store, backup = _store(tmp_path, adapter)
    device = store.inventory.devices[0]

    result = store.restore_backup(device, backup.history("核心A")[0].filename)

    assert result["ok"] is False
    assert len(adapter.sent) == 1, "失败后不允许重试第二次"
    assert "不重试" in result["error"]
    actions = [e.get("action") for e in deploy_mod.audit_tail(50)]
    assert "config.restore" in actions


def test_restore_success_is_audited(tmp_path):
    adapter = FakeRestoreAdapter()
    store, backup = _store(tmp_path, adapter)
    device = store.inventory.devices[0]

    store.restore_backup(device, backup.history("核心A")[0].filename)

    entries = [e for e in deploy_mod.audit_tail(50)
               if e.get("action") == "config.restore"]
    assert entries, "审计里必须出现 config.restore"
    assert entries[-1]["status"] == "OK" and entries[-1]["commands"] == 3
    assert entries[-1]["pre_backup"]


def test_restore_unknown_snapshot_fails_cleanly(tmp_path):
    """快照文件名不存在：报错、不发命令，但恢复前备份已完成（顺序正确）。"""
    adapter = FakeRestoreAdapter()
    store, _backup = _store(tmp_path, adapter)
    device = store.inventory.devices[0]

    result = store.restore_backup(device, "no-such-snapshot.cfg")

    assert result["ok"] is False
    assert adapter.sent == []
    assert result["pre_backup"], "现网备份在解析快照之前已完成"
    assert "找不到快照" in result["error"]


def test_restore_empty_snapshot_rejected(tmp_path):
    """快照全是注释/空行：明确拒绝，不发命令。"""
    adapter = FakeRestoreAdapter()
    store, backup = _store(tmp_path, adapter)
    backup.save("核心A", "!\n# 只有注释\n")
    device = store.inventory.devices[0]

    result = store.restore_backup(device, backup.history("核心A")[0].filename)

    assert result["ok"] is False and adapter.sent == []
    assert "没有可执行" in result["error"]
