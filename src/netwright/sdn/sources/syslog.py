"""syslog.py — Syslog 监听与归类（RFC3164 / RFC5424 兼容）。

为什么要它：控制器的"事件"如果只来自自己的操作，就只是操作日志；
把设备 syslog 接进来，才有"网络正在发生什么"的实时感（链路 flap、登录失败、配置变更）。

归类是**保守**的：只把明确命中的关键字升级成 warning/critical，其余保持 info，
避免把噪音刷成告警（告警疲劳比没有告警更糟）。
"""
from __future__ import annotations

import re
import socketserver
import threading
from dataclasses import dataclass, field

PRI_RE = re.compile(r"^<(\d{1,3})>")
RFC5424_RE = re.compile(
    r"^<(?P<pri>\d{1,3})>(?P<ver>\d)\s+(?P<ts>\S+)\s+(?P<host>\S+)\s+(?P<app>\S+)\s+"
    r"(?P<proc>\S+)\s+(?P<msgid>\S+)\s+(?P<sd>-|\[[^\]]*\])\s*(?P<msg>.*)$")
RFC3164_RE = re.compile(
    r"^<(?P<pri>\d{1,3})>(?P<ts>[A-Z][a-z]{2}\s+\d{1,2}\s+\d{2}:\d{2}:\d{2})\s+"
    r"(?P<host>\S+)\s+(?P<tag>[^:\[]+)(?:\[(?P<pid>\d+)\])?:\s*(?P<msg>.*)$")

_SEVERITY_NAMES = ["emerg", "alert", "crit", "err", "warning", "notice", "info", "debug"]

# (正则, topic, 严重度, 标题) —— 顺序即优先级
RULES = [
    (re.compile(r"link\s*down|interface .*? down|端口.*down|%LINK-\d-UPDOWN.*down", re.I),
     "link.down", "critical", "链路中断"),
    (re.compile(r"link\s*up|%LINK-\d-UPDOWN.*up|端口.*up", re.I),
     "link.up", "info", "链路恢复"),
    (re.compile(r"%BGP-\d-ADJCHANGE|bgp.*(down|up)|邻居.*(down|up)", re.I),
     "routing.bgp", "warning", "BGP 邻居变化"),
    (re.compile(r"%OSPF-\d-ADJCHANGE|ospf.*neighbor", re.I),
     "routing.ospf", "warning", "OSPF 邻居变化"),
    (re.compile(r"%SYS-\d-CONFIG_I|configured from|config.*changed|配置.*变更", re.I),
     "device.config_change", "warning", "配置变更"),
    (re.compile(r"authentication fail|login fail|login failed|ssh.*fail|认证失败", re.I),
     "auth.failure", "warning", "登录失败"),
    (re.compile(r"power.*(fail|absent)|fan.*(fail|absent)|temperature.*high", re.I),
     "device.hardware", "critical", "硬件告警"),
]


@dataclass
class SyslogRecord:
    priority: int
    facility: int
    severity: int
    host: str = ""
    tag: str = ""
    message: str = ""
    raw: str = ""
    fields: dict = field(default_factory=dict)

    @property
    def severity_name(self) -> str:
        return _SEVERITY_NAMES[self.severity] if 0 <= self.severity < 8 else "info"

    def to_dict(self) -> dict:
        return {"priority": self.priority, "facility": self.facility,
                "severity": self.severity_name, "host": self.host, "tag": self.tag,
                "message": self.message, "raw": self.raw}


def parse_syslog(line: str) -> SyslogRecord | None:
    """解析一行 syslog；无法识别返回 None（绝不抛异常，监听器不能被一条坏包打死）。"""
    text = (line or "").strip()
    if not text:
        return None
    match = RFC5424_RE.match(text)
    if match:
        pri = int(match.group("pri"))
        return SyslogRecord(
            priority=pri, facility=pri // 8, severity=pri % 8,
            host=match.group("host"), tag=match.group("app"),
            message=match.group("msg").strip(), raw=text,
            fields={"version": match.group("ver"), "msgid": match.group("msgid")})
    match = RFC3164_RE.match(text)
    if match:
        pri = int(match.group("pri"))
        return SyslogRecord(
            priority=pri, facility=pri // 8, severity=pri % 8,
            host=match.group("host"), tag=match.group("tag").strip(),
            message=match.group("msg").strip(), raw=text,
            fields={"timestamp": match.group("ts")})
    # 没有 <PRI> 的裸消息（部分设备/中继会去掉）
    pri_match = PRI_RE.match(text)
    pri = int(pri_match.group(1)) if pri_match else 13
    body = text[pri_match.end():] if pri_match else text
    return SyslogRecord(priority=pri, facility=pri // 8, severity=pri % 8,
                        message=body.strip(), raw=text)


def classify_syslog(record: SyslogRecord) -> tuple[str, str, str]:
    """返回 (topic, severity, title)。"""
    message = f"{record.tag} {record.message}"
    for pattern, topic, severity, title in RULES:
        if pattern.search(message):
            return topic, severity, title
    return "syslog.message", "info", "设备日志"


class _UDPHandler(socketserver.BaseRequestHandler):
    def handle(self):      # noqa: D102
        data, _sock = self.request
        listener: SyslogListener = self.server.listener      # type: ignore[attr-defined]
        listener.handle_packet(data)


class SyslogListener:
    """UDP syslog 监听器（默认 5140，避免与系统 rsyslog 抢 514）。"""

    def __init__(self, bus=None, on_event=None, host: str = "0.0.0.0", port: int = 5140):
        self.bus = bus
        self.on_event = on_event
        self.host = host
        self.port = port
        self._server: socketserver.ThreadingUDPServer | None = None
        self._thread: threading.Thread | None = None
        self.received = 0

    # ── 生命周期 ──
    def start(self) -> bool:
        if self._server is not None:
            return True
        server = socketserver.ThreadingUDPServer((self.host, self.port), _UDPHandler)
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

    # ── 处理 ──
    def handle_packet(self, data: bytes) -> dict | None:
        text = data.decode("utf-8", "replace").strip()
        record = parse_syslog(text)
        if record is None:
            return None
        self.received += 1
        topic, severity, title = classify_syslog(record)
        payload = {"title": title, "device_host": record.host, "syslog_tag": record.tag,
                   "syslog_message": record.message, "raw": record.raw,
                   "severity_name": record.severity_name}
        if self.bus is not None:
            self.bus.publish(topic, f"{title} · {record.host or '?'} {record.message}"[:400],
                             severity=severity, source="syslog", **payload)
        if self.on_event is not None:
            try:
                self.on_event(topic, payload)
            except Exception:      # noqa: BLE001
                pass
        return payload
