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


def _split_name(filename: str) -> tuple:
    """把 ``YYYYmmdd-HHMMSS-ffffff[-N].cfg`` 拆成可比较的键。

    为什么不用正则取序号：``-(\\d+)\\.cfg$`` 会先匹配到时刻/微秒段，
    把基础文件当成第 211941 份；按 '-' 分段并把每段转成整数最稳。
    尾部多出来的段（同微秒碰撞时的 -1/-2）也纳入键，保证顺序严格单调。
    """
    stem = filename[:-4] if filename.endswith(".cfg") else (filename or "")
    parts = stem.split("-")
    date = parts[0] if parts else ""
    clock = parts[1] if len(parts) > 1 else ""
    tail = tuple(int(p) if p.isdigit() else 0 for p in parts[2:])
    return (date, clock) + tail


def _sequence(filename: str) -> int:
    """同一时刻内的第 N 份快照（用于展示/兼容），取键的最后一段。"""
    key = _split_name(filename)
    return int(key[-1]) if key and isinstance(key[-1], int) else 0


def _sort_key(filename: str) -> tuple:
    """文件名排序键（严格单调）：(日期, 时刻, 微秒, 同刻序号…)。"""
    return _split_name(filename)


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

    def __init__(self, base_dir: str, bus=None, keep: int = DEFAULT_KEEP,
                 device_keep: dict | None = None):
        self.base_dir = base_dir
        self.bus = bus
        self.keep = max(2, int(keep))
        # R8：按设备覆盖保留份数（settings["backup_keep_device"]）；
        # 没登记的设备用全局 keep。
        self.device_keep: dict[str, int] = {
            str(d): max(2, int(n)) for d, n in (device_keep or {}).items()}
        # 摘要缓存：键是 (路径, mtime_ns, size)。备份目录只在 save/prune 时变化，
        # 缓存能把 "每次 save 都重算全部快照 sha256" 的 O(n) IO 降到 O(1)。
        self._digests: dict[tuple, str] = {}

    def _keep_for(self, device: str) -> int:
        return self.device_keep.get(device, self.keep)

    def set_device_keep(self, device: str, keep: int) -> int:
        """按设备设置保留份数（R8），立即对现有历史生效（触发一次 prune）。"""
        value = max(2, int(keep))
        self.device_keep[device] = value
        self._prune(device)
        return value

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

    def _digest(self, path: str, stat=None) -> str:
        """文件 sha256（带缓存）；缓存键含 mtime/size，文件被外部改动会自动失效。"""
        try:
            stat = stat or os.stat(path)
        except OSError:
            return ""
        key = (path, stat.st_mtime_ns, stat.st_size)
        digest = self._digests.get(key)
        if digest is not None:
            return digest
        try:
            with open(path, "rb") as handle:
                digest = hashlib.sha256(handle.read()).hexdigest()
        except OSError:
            return ""
        self._digests[key] = digest
        return digest

    def _latest_path(self, device: str) -> str | None:
        """最快的"最新一份"：只按文件名排序，不读任何文件内容。"""
        folder = os.path.join(self.root, self._safe(device))
        if not os.path.isdir(folder):
            return None
        names = [n for n in os.listdir(folder) if n.endswith(".cfg")]
        if not names:
            return None
        return os.path.join(folder, max(names, key=_sort_key))

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
        # 文件名 = 秒级时间戳 + 同秒自增序号。
        # 不用"时钟微秒"做序号：Windows 的 time_ns 在快速连续写入时会抖动甚至回退，
        # 曾导致新快照被排到最旧、随后被 prune 删掉（真丢数据）。
        second = time.strftime("%Y%m%d-%H%M%S")
        counter = 0
        for name in os.listdir(folder):
            if not (name.startswith(second) and name.endswith(".cfg")):
                continue
            tail = name[len(second):-4].lstrip("-")
            if tail.isdigit():
                counter = max(counter, int(tail) + 1)
        path = os.path.join(folder, f"{second}-{counter:06d}.cfg")
        while os.path.exists(path):        # 极端并发下的兜底
            counter += 1
            path = os.path.join(folder, f"{second}-{counter:06d}.cfg")
        with open(path, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text if text.endswith("\n") else text + "\n")
        entry = BackupEntry(device=device, path=path, ts=time.time(),
                            size=len(data), sha256=digest, changed=True)
        self._prune(device, protect=path)
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
            except OSError:
                continue
            digest = self._digest(path, stat)
            entries.append(BackupEntry(device=device, path=path,
                                       ts=stat.st_mtime_ns / 1e9,
                                       size=stat.st_size, sha256=digest))
        # 同一秒内可能有多份（文件名带 -1/-2 后缀）：按 (时间, 序号) 排序，
        # 避免只按 mtime 排序时同秒快照顺序不稳定（prune 会删错）。
        return sorted(entries, key=lambda e: _sort_key(e.filename), reverse=True)

    def latest(self, device: str) -> BackupEntry | None:
        """最新一份快照。

        性能：只 stat 最新文件（按文件名排序），不再遍历/哈希整个历史目录；
        内容摘要走 ``_digest`` 缓存，重复调用几乎零 IO。
        """
        path = self._latest_path(device)
        if path is None:
            return None
        try:
            stat = os.stat(path)
        except OSError:
            return None
        return BackupEntry(device=device, path=path, ts=stat.st_mtime_ns / 1e9,
                           size=stat.st_size, sha256=self._digest(path, stat))

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
    def _prune(self, device: str, protect: str | None = None) -> None:
        """只保留最近 ``keep`` 份（R8：按设备覆盖）；``protect`` 永不删除。"""
        items = self.history(device)
        limit = self._keep_for(device)
        for entry in items[limit:]:
            if protect and os.path.abspath(entry.path) == os.path.abspath(protect):
                continue
            try:
                os.remove(entry.path)
            except OSError:
                pass

    # ── 导出 / 迁移（R8 备份治理）──
    def export_zip(self, zip_path: str, devices: list[str] | None = None) -> dict:
        """把快照打包成 zip，内含 manifest.json（设备 / 时间 / sha256）。

        :param devices: 要导出的设备列表（默认全部）。
        :return: {"path", "devices", "snapshots"}
        """
        import json as _json
        import zipfile

        names = devices if devices is not None else self.devices()
        manifest = {
            "created": time.time(),
            "created_text": time.strftime("%Y-%m-%d %H:%M:%S"),
            "tool": "NetWright",
            "entries": [],
        }
        count = 0
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for device in names:
                for entry in self.history(device):
                    arc = f"{self._safe(device)}/{entry.filename}"
                    zf.write(entry.path, arc)
                    manifest["entries"].append({
                        "device": device, "file": arc, "ts": entry.ts,
                        "time": entry.time_text, "size": entry.size,
                        "sha256": entry.sha256})
                    count += 1
            zf.writestr("manifest.json",
                        _json.dumps(manifest, ensure_ascii=False, indent=2))
        return {"path": zip_path, "devices": len(names), "snapshots": count}

    def migrate_root(self, new_base_dir: str) -> dict:
        """迁移备份目录到新 base（R8 设置项），迁移后旧目录不再写入。

        同盘且新位置空闲 → 整个 ``backups/`` 原子重命名（历史完整保留）；
        否则新目录从空开始（旧目录保持原样，只读不再写入）。
        """
        old_root = self.root
        old_base = self.base_dir
        self.base_dir = new_base_dir
        new_root = self.root
        moved = False
        os.makedirs(new_base_dir, exist_ok=True)   # rename 需要目标父目录存在
        if os.path.isdir(old_root) and not os.path.exists(new_root):
            try:
                os.rename(old_root, new_root)      # 同盘原子；跨盘抛 OSError
                moved = True
            except OSError:
                self.base_dir = old_base           # 回退，绝不留在半路
                raise
        self._digests.clear()
        return {"old": old_root, "new": new_root, "moved": moved}
