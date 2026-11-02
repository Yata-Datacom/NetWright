"""backup.py — 配置备份与差异（Oxidized 式的最小实现）。

为什么控制器需要它：下发/巡检都是"当下的动作"，而排障最常问的是
"**它什么时候变成这样的**"。按设备存配置快照 + 出 unified diff，
就能回答这个问题，而且不引入 git（单机工具不要求用户会 git）。

设计取舍：
  * 内容去重：与上一次快照 sha256 相同则不落盘（只记一次"未变化"），
    避免每天 24 份一模一样的配置把磁盘塞满；
  * 目录极简：``backups/<设备名>/<YYYYmmdd-HHMMSS>.cfg``，用户可以直接用资源管理器看；
  * 只保留最近 N 份（默认 30），可在构造时改；
  * 差异用标准库 difflib，输出 unified diff，和 ``git diff`` 观感一致。
"""
from __future__ import annotations

import difflib
import hashlib
import os
import re
import time
from dataclasses import dataclass

BACKUP_DIR = "backups"
DEFAULT_KEEP = 30
_UNSAFE = re.compile(r"[^A-Za-z0-9._-]+")
_SEQ_RE = re.compile(r"-(\d+)\.cfg$")


def _sequence(filename: str) -> int:
    """同一秒内的第 N 份快照（文件名后缀 -1/-2…），用于稳定排序。"""
    match = _SEQ_RE.search(filename or "")
    return int(match.group(1)) if match else 0


@dataclass
class BackupEntry:
    """一份配置快照。"""

    device: str
    path: str
    ts: float
    size: int
    sha256: str
    changed: bool = True

    @property
    def filename(self) -> str:
        return os.path.basename(self.path)

    @property
    def time_text(self) -> str:
        return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(self.ts))

    def to_dict(self) -> dict:
        return {"device": self.device, "file": self.filename, "path": self.path,
                "ts": self.ts, "time": self.time_text, "size": self.size,
                "sha256": self.sha256, "changed": self.changed}


class ConfigBackup:
    """按设备保存配置快照，并提供历史与差异查询。"""

    def __init__(self, base_dir: str, bus=None, keep: int = DEFAULT_KEEP):
        self.base_dir = base_dir
        self.bus = bus
        self.keep = max(2, int(keep))

    # ── 路径 ──
    @property
    def root(self) -> str:
        return os.path.join(self.base_dir, BACKUP_DIR)

    def _safe(self, device: str) -> str:
        name = _UNSAFE.sub("_", (device or "").strip()) or "unknown"
        return name[:80]

    def _device_dir(self, device: str) -> str:
        path = os.path.join(self.root, self._safe(device))
        os.makedirs(path, exist_ok=True)
        return path

    # ── 写入 ──
    def save(self, device: str, text: str, note: str = "") -> BackupEntry:
        """保存一份快照；内容与上次相同则不落盘（changed=False）。"""
        if not (text or "").strip():
            raise ValueError("配置内容为空，拒绝写入（避免用空文件覆盖历史）")
        data = text.encode("utf-8")
        digest = hashlib.sha256(data).hexdigest()
        previous = self.latest(device)
        if previous is not None and previous.sha256 == digest:
            return BackupEntry(device=device, path=previous.path, ts=previous.ts,
                               size=previous.size, sha256=digest, changed=False)
        folder = self._device_dir(device)
        stamp = time.strftime("%Y%m%d-%H%M%S", time.localtime())
        path = os.path.join(folder, f"{stamp}.cfg")
        suffix = 1
        while os.path.exists(path):        # 同一秒内多次备份
            path = os.path.join(folder, f"{stamp}-{suffix}.cfg")
            suffix += 1
        with open(path, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text if text.endswith("\n") else text + "\n")
        entry = BackupEntry(device=device, path=path, ts=time.time(),
                            size=len(data), sha256=digest, changed=True)
        self._prune(device)
        if self.bus is not None:
            self.bus.publish(
                "config.backup",
                f"{device}: 已保存配置快照（{entry.size // 1024} KB）" + (f" · {note}" if note else ""),
                source="backup", device=device, file=entry.filename, size=entry.size)
        return entry

    # ── 查询 ──
    def history(self, device: str) -> list[BackupEntry]:
        """按时间倒序返回快照列表。"""
        folder = os.path.join(self.root, self._safe(device))
        if not os.path.isdir(folder):
            return []
        entries = []
        for name in os.listdir(folder):
            if not name.endswith(".cfg"):
                continue
            path = os.path.join(folder, name)
            try:
                stat = os.stat(path)
                with open(path, "rb") as handle:
                    digest = hashlib.sha256(handle.read()).hexdigest()
            except OSError:
                continue
            entries.append(BackupEntry(device=device, path=path,
                                       ts=stat.st_mtime_ns / 1e9,
                                       size=stat.st_size, sha256=digest))
        # 同一秒内可能有多份（文件名带 -1/-2 后缀）：按 (时间, 序号) 排序，
        # 避免只按 mtime 排序时同秒快照顺序不稳定（prune 会删错）。
        return sorted(entries, key=lambda e: (e.ts, _sequence(e.filename)),
                      reverse=True)

    def latest(self, device: str) -> BackupEntry | None:
        items = self.history(device)
        return items[0] if items else None

    def devices(self) -> list[str]:
        if not os.path.isdir(self.root):
            return []
        return sorted(name for name in os.listdir(self.root)
                      if os.path.isdir(os.path.join(self.root, name)))

    # ── 差异 ──
    def read(self, entry: BackupEntry) -> str:
        with open(entry.path, encoding="utf-8", errors="replace") as handle:
            return handle.read()

    def diff(self, device: str, old: str | None = None, new: str | None = None) -> str:
        """返回 unified diff。

        :param old: 旧快照文件名（默认倒数第二份）
        :param new: 新快照文件名（默认最新一份）
        """
        items = self.history(device)
        if len(items) < 2 and not (old and new):
            return ""
        by_name = {e.filename: e for e in items}
        old_entry = by_name.get(old) if old else items[1]
        new_entry = by_name.get(new) if new else items[0]
        if old_entry is None or new_entry is None:
            raise ValueError("找不到指定的快照文件")
        return self.diff_text(self.read(old_entry), self.read(new_entry),
                              f"{device}/{old_entry.filename}",
                              f"{device}/{new_entry.filename}")

    @staticmethod
    def diff_text(old_text: str, new_text: str,
                  old_label: str = "before", new_label: str = "after") -> str:
        diff = difflib.unified_diff(
            (old_text or "").splitlines(), (new_text or "").splitlines(),
            fromfile=old_label, tofile=new_label, lineterm="", n=3)
        return "\n".join(diff)

    def diff_against(self, device: str, text: str, label: str = "现网配置") -> str:
        """拿"最新快照"和一段现读到的配置对比（不落盘）。

        典型用法：怀疑有人手改了设备 → 读一次现网配置，直接和上次快照比。
        """
        latest = self.latest(device)
        if latest is None:
            raise ValueError(f"{device} 还没有快照：先「🗄 备份配置」一次再对比")
        return self.diff_text(self.read(latest), text, latest.filename, label)

    # ── 清理 ──
    def _prune(self, device: str) -> None:
        items = self.history(device)
        for entry in items[self.keep:]:
            try:
                os.remove(entry.path)
            except OSError:
                pass
