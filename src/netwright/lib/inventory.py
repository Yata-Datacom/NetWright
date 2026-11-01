"""inventory.py — 设备清单中心：所有模块共用的一份设备数据（JSON 持久化）。

字段：hostname(可选，默认 host) / host / port / vendor / username / password(受保护) / note
存储文件：程序目录下 netwright_devices.json（exe 同目录 / 仓库根目录）。
"""
from __future__ import annotations

import json
import os
import re
import sys
from dataclasses import asdict, dataclass

from . import secrets

FILENAME = "netwright_devices.json"

VENDORS = {
    "huawei": "华为 VRP",
    "h3c": "新华三 Comware",
    "cisco": "思科 IOS",
    "ruijie": "锐捷 RGOS",
    "linux": "Linux 服务器",
    "mikrotik": "MikroTik RouterOS",
    "vyos": "VyOS",
    "sonic": "SONiC",
    "huawei_ac": "华为 WLAN AC",
    "h3c_ac": "新华三 WLAN AC",
    "cisco_wlc": "思科 WLC（9800）",
    "generic": "通用",
}

BAD_FILENAME_CHARS = re.compile(r'[\\/:*?"<>|]')


@dataclass
class Device:
    host: str
    port: int = 22
    vendor: str = "huawei"
    username: str = ""
    password: str = ""          # 内存中始终是明文；落盘时经 secrets.protect
    hostname: str = ""          # 显示名，可空
    protocol: str = "ssh"       # 接入协议：ssh / telnet
    note: str = ""

    @property
    def display_name(self) -> str:
        return self.hostname or self.host

    def to_storage(self) -> dict:
        d = asdict(self)
        d["password"] = secrets.protect(self.password)
        return d

    @classmethod
    def from_storage(cls, data: dict) -> Device:
        return cls(
            host=str(data.get("host", "")),
            port=int(data.get("port") or 22),
            vendor=str(data.get("vendor") or "huawei"),
            username=str(data.get("username", "")),
            password=secrets.unprotect(str(data.get("password", ""))),
            hostname=str(data.get("hostname", "")),
            note=str(data.get("note", "")),
        )


@dataclass
class LedgerLink:
    device_host: str        # 本端设备（host）
    local_intf: str         # 本端接口
    peer_host: str          # 对端设备名/host
    peer_intf: str          # 对端接口


class Inventory:
    """设备清单（内存 + 磁盘）：设备 + 台账链路。"""

    def __init__(self, path: str | None = None):
        self.path = path or os.path.join(_base_dir(), FILENAME)
        self.devices: list[Device] = []
        self.links: list[LedgerLink] = []
        self.load()

    # ── CRUD ──
    def add(self, dev: Device) -> Device:
        if not dev.host:
            raise ValueError("主机地址不能为空")
        if self.find(dev.host, dev.port):
            raise ValueError(f"已存在同地址设备: {dev.host}:{dev.port}")
        self.devices.append(dev)
        self.save()
        return dev

    def update(self, index: int, dev: Device):
        if not (0 <= index < len(self.devices)):
            raise IndexError("索引越界")
        if not dev.host:
            raise ValueError("主机地址不能为空")
        for i, other in enumerate(self.devices):
            if i != index and other.host == dev.host and other.port == dev.port:
                raise ValueError(f"已存在同地址设备: {dev.host}:{dev.port}")
        self.devices[index] = dev
        self.save()

    def remove(self, index: int):
        if not (0 <= index < len(self.devices)):
            raise IndexError("索引越界")
        self.devices.pop(index)
        self.save()

    def find(self, host: str, port: int) -> Device | None:
        for d in self.devices:
            if d.host == host and d.port == port:
                return d
        return None

    def by_vendor(self, vendor: str) -> list[Device]:
        return [d for d in self.devices if d.vendor == vendor]

    # ── 批量导入（CSV 文本：host,port,vendor,username,password,hostname,note）──
    def import_csv(self, text: str, replace: bool = False,
                   build_links: bool = True) -> tuple[int, list[str]]:
        """返回 (导入数, 警告列表)。表头行自动识别（host 或 地址 开头）。"""
        import csv
        import io
        warnings: list[str] = []
        rows = list(csv.reader(io.StringIO(text or "")))
        rows = [r for r in rows if any(str(c).strip() for c in r)]
        if not rows:
            return 0, ["内容为空"]
        header = [c.strip().lower() for c in rows[0]]
        colmap = {name: i for i, name in enumerate(header)}
        data_rows = rows[1:] if ("host" in colmap or "地址" in colmap or "ip" in colmap) else rows
        if data_rows is rows:
            colmap = {"host": 0, "port": 1, "vendor": 2, "username": 3, "password": 4}
        added = 0
        if replace:
            self.devices.clear()
        for n, row in enumerate(data_rows, start=2):
            def get(key, default="", _row=row, _map=colmap):
                i = _map.get(key)
                return str(_row[i]).strip() if i is not None and i < len(_row) and _row[i] else default
            host = get("host") or get("地址") or get("ip")
            if not host:
                warnings.append(f"第 {n} 行缺主机地址，已跳过")
                continue
            vendor = (get("vendor") or get("厂商") or "huawei").strip().lower()
            if vendor not in VENDORS:
                warnings.append(f"第 {n} 行厂商 {vendor} 未识别，按 generic 处理")
                vendor = "generic"
            try:
                port = int(get("port") or 22)
            except ValueError:
                port = 22
            protocol = (get("protocol") or get("协议") or "ssh").strip().lower()
            if protocol not in ("ssh", "telnet"):
                protocol = "ssh"
            dev = Device(host=host, port=port, vendor=vendor,
                         username=get("username") or get("用户名"),
                         password=get("password") or get("密码"),
                         hostname=get("hostname") or get("名称"),
                         protocol=protocol,
                         note=get("note") or get("备注"))
            if self.find(dev.host, dev.port):
                warnings.append(f"第 {n} 行 {dev.host}:{dev.port} 已存在，跳过")
                continue
            self.devices.append(dev)
            added += 1
            # 台账拓扑：本端接口 + 对端设备/接口（可选列）
            local_intf = get("local_intf") or get("本端接口")
            peer_dev = get("peer_device") or get("对端设备")
            peer_intf = get("peer_intf") or get("对端接口")
            if local_intf and peer_dev and build_links:
                self.links.append(LedgerLink(
                    device_host=host, local_intf=local_intf,
                    peer_host=peer_dev, peer_intf=peer_intf))
        if added:
            self.save()
        return added, warnings

    def export_csv(self) -> str:
        import csv
        import io
        buf = io.StringIO()
        w = csv.writer(buf, lineterminator="\n")
        w.writerow(["host", "port", "vendor", "protocol", "username", "password",
                    "hostname", "note"])
        for d in self.devices:
            w.writerow([d.host, d.port, d.vendor, d.protocol, d.username,
                        d.password, d.hostname, d.note])
        return buf.getvalue()

    # ── 持久化 ──
    def load(self):
        self.devices = []
        self.links = []
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                data = json.load(f)
            for d in data.get("devices", []):
                try:
                    self.devices.append(Device.from_storage(d))
                except Exception:
                    continue
            for lk in data.get("links", []):
                try:
                    self.links.append(LedgerLink(
                        device_host=str(lk.get("device_host", "")),
                        local_intf=str(lk.get("local_intf", "")),
                        peer_host=str(lk.get("peer_host", "")),
                        peer_intf=str(lk.get("peer_intf", ""))))
                except Exception:
                    continue
        except (OSError, ValueError):
            pass

    def save(self):
        payload = {"version": 2,
                   "devices": [d.to_storage() for d in self.devices],
                   "links": [asdict(lk) for lk in self.links]}
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        os.replace(tmp, self.path)


def safe_filename(name: str) -> str:
    return BAD_FILENAME_CHARS.sub("_", (name or "").strip()) or "unnamed"


def _base_dir() -> str:
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
