"""snmp.py — SNMPv2c Trap 的最小 BER 解码与监听。

不引入 pysnmp：只需要"读懂 trap 里的 OID 与值"，一百多行 BER 解析就够了，
而且能把依赖面控制住（控制器只装 paramiko 就能跑）。

支持的值类型：INTEGER / OCTET STRING / OID / NULL / IpAddress / Counter32 /
Gauge32 / TimeTicks / Counter64 —— 覆盖 trap 里 99% 的 varbind。
"""
from __future__ import annotations

import socketserver
import threading
from dataclasses import dataclass, field

# 常用 trap OID
TRAP_LINK_DOWN = "1.3.6.1.6.3.1.1.5.3"
TRAP_LINK_UP = "1.3.6.1.6.3.1.1.5.4"
TRAP_COLD_START = "1.3.6.1.6.3.1.1.5.1"
TRAP_WARM_START = "1.3.6.1.6.3.1.1.5.2"
TRAP_AUTH_FAILURE = "1.3.6.1.6.3.1.1.5.5"

TAG_INTEGER = 0x02
TAG_OCTET = 0x04
TAG_NULL = 0x05
TAG_OID = 0x06
TAG_SEQUENCE = 0x30
TAG_IPADDRESS = 0x40
TAG_COUNTER32 = 0x41
TAG_GAUGE32 = 0x42
TAG_TIMETICKS = 0x43
TAG_COUNTER64 = 0x46
TAG_TRAP_V2 = 0xA7


class BerError(ValueError):
    """BER 结构不合法。"""


@dataclass
class SnmpTrap:
    version: int = 1
    community: str = ""
    varbinds: list = field(default_factory=list)     # [(oid, value)]
    source: str = ""

    def get(self, oid: str, default=None):
        for key, value in self.varbinds:
            if key == oid:
                return value
        return default

    @property
    def trap_oid(self) -> str:
        return str(self.get("1.3.6.1.6.3.1.1.4.1.0", "") or "")

    @property
    def uptime(self):
        return self.get("1.3.6.1.2.1.1.3.0")

    def to_dict(self) -> dict:
        return {"version": self.version, "community": self.community,
                "source": self.source, "trap_oid": self.trap_oid,
                "varbinds": [{"oid": o, "value": v} for o, v in self.varbinds]}


# ── BER ─────────────────────────────────────────────────────────────
def read_tlv(data: bytes, pos: int = 0) -> tuple[int, bytes, int]:
    if pos + 2 > len(data):
        raise BerError("TLV 截断")
    tag = data[pos]
    pos += 1
    length = data[pos]
    pos += 1
    if length & 0x80:
        count = length & 0x7F
        if count == 0 or pos + count > len(data):
            raise BerError("长度字段非法")
        length = int.from_bytes(data[pos:pos + count], "big")
        pos += count
    end = pos + length
    if end > len(data):
        raise BerError("内容截断")
    return tag, data[pos:end], end


def _decode_int(value: bytes) -> int:
    return int.from_bytes(value, "big", signed=True) if value else 0


def _decode_oid(value: bytes) -> str:
    if not value:
        return ""
    first = value[0]
    parts = [first // 40, first % 40]
    number = 0
    for byte in value[1:]:
        number = (number << 7) | (byte & 0x7F)
        if not byte & 0x80:
            parts.append(number)
            number = 0
    return ".".join(str(p) for p in parts)


def _decode_value(tag: int, value: bytes):
    if tag == TAG_INTEGER:
        return _decode_int(value)
    if tag in (TAG_COUNTER32, TAG_GAUGE32, TAG_TIMETICKS):
        return int.from_bytes(value, "big")
    if tag == TAG_COUNTER64:
        return int.from_bytes(value, "big")
    if tag == TAG_OID:
        return _decode_oid(value)
    if tag == TAG_IPADDRESS and len(value) == 4:
        return ".".join(str(b) for b in value)
    if tag == TAG_NULL:
        return None
    if tag == TAG_OCTET:
        try:
            return value.decode("utf-8")
        except UnicodeDecodeError:
            return value.hex()
    return value.hex()


def parse_snmp_trap(data: bytes, source: str = "") -> SnmpTrap | None:
    """解析 SNMPv2c trap；结构不对返回 None（监听器不能因为坏包崩溃）。"""
    try:
        tag, body, _ = read_tlv(data, 0)
        if tag != TAG_SEQUENCE:
            return None
        pos = 0
        tag, value, pos = read_tlv(body, pos)          # version
        version = _decode_int(value)
        tag, value, pos = read_tlv(body, pos)          # community
        community = value.decode("utf-8", "replace")
        tag, pdu, pos = read_tlv(body, pos)            # trap PDU
        if tag != TAG_TRAP_V2:
            return None
        cursor = 0
        for _ in ("request-id", "error-status", "error-index"):
            _t, _v, cursor = read_tlv(pdu, cursor)
        tag, varbind_list, cursor = read_tlv(pdu, cursor)
        if tag != TAG_SEQUENCE:
            return None
        bindings = []
        cursor = 0
        while cursor < len(varbind_list):
            tag, varbind, cursor = read_tlv(varbind_list, cursor)
            if tag != TAG_SEQUENCE:
                continue
            inner = 0
            _t, oid_bytes, inner = read_tlv(varbind, inner)
            vtag, vvalue, inner = read_tlv(varbind, inner)
            bindings.append((_decode_oid(oid_bytes), _decode_value(vtag, vvalue)))
        return SnmpTrap(version=version, community=community,
                        varbinds=bindings, source=source)
    except (BerError, IndexError, ValueError):
        return None


# ── 归类 ────────────────────────────────────────────────────────────
def classify_trap(trap: SnmpTrap) -> tuple[str, str, str]:
    oid = trap.trap_oid
    if oid == TRAP_LINK_DOWN:
        return "link.down", "critical", "SNMP: 链路 Down"
    if oid == TRAP_LINK_UP:
        return "link.up", "info", "SNMP: 链路 Up"
    if oid in (TRAP_COLD_START, TRAP_WARM_START):
        return "device.restart", "warning", "SNMP: 设备重启"
    if oid == TRAP_AUTH_FAILURE:
        return "auth.failure", "warning", "SNMP: 认证失败"
    return "snmp.trap", "info", f"SNMP Trap {oid or '(unknown)'}"


class _TrapHandler(socketserver.BaseRequestHandler):
    def handle(self):      # noqa: D102
        data, _sock = self.request
        listener: SnmpTrapListener = self.server.listener      # type: ignore[attr-defined]
        listener.handle_packet(data, self.client_address[0])


class SnmpTrapListener:
    """UDP 162 的 trap 接收器（默认 1162，避免与系统 snmpd 抢端口）。"""

    def __init__(self, bus=None, on_event=None, host: str = "0.0.0.0", port: int = 1162):
        self.bus = bus
        self.on_event = on_event
        self.host = host
        self.port = port
        self._server: socketserver.ThreadingUDPServer | None = None
        self._thread: threading.Thread | None = None
        self.received = 0

    def start(self) -> bool:
        if self._server is not None:
            return True
        server = socketserver.ThreadingUDPServer((self.host, self.port), _TrapHandler)
        server.daemon_threads = True
        server.listener = self      # type: ignore[attr-defined]
        self._server = server
        self._thread = threading.Thread(target=server.serve_forever, daemon=True)
        self._thread.start()
        return True

    def stop(self):
        if self._server is not None:
            self._server.shutdown()
            self._server.server_close()
            self._server = None
        self._thread = None

    @property
    def running(self) -> bool:
        return self._server is not None

    @property
    def bound_port(self) -> int:
        if self._server is None:
            return self.port
        return self._server.server_address[1]

    def handle_packet(self, data: bytes, source: str = "") -> dict | None:
        trap = parse_snmp_trap(data, source=source)
        if trap is None:
            return None
        self.received += 1
        topic, severity, title = classify_trap(trap)
        if_index = trap.get("1.3.6.1.2.1.2.2.1.1")
        admin = trap.get("1.3.6.1.2.1.2.2.1.7")
        oper = trap.get("1.3.6.1.2.1.2.2.1.8")
        payload = {"trap_oid": trap.trap_oid, "trap_source": source,
                   "if_index": if_index, "if_admin": admin, "if_oper": oper,
                   "varbinds": [{"oid": o, "value": v} for o, v in trap.varbinds]}
        if self.bus is not None:
            self.bus.publish(topic, f"{title} · {source or '?'}"
                             + (f" ifIndex={if_index}" if if_index is not None else ""),
                             severity=severity, source="snmp-trap", **payload)
        if self.on_event is not None:
            try:
                self.on_event(topic, payload)
            except Exception:      # noqa: BLE001
                pass
        return payload
