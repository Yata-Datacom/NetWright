"""南向实装 + 事件源测试：RESTCONF / NETCONF / syslog / SNMP trap。

原则：全部本地回环，不碰真实设备。
"""

from __future__ import annotations

import json
import os
import socket
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)


from netwright.lib.inventory import Device
from netwright.sdn.events import EventBus
from netwright.sdn.sources import (SnmpTrapListener, SyslogListener,
                                   classify_syslog, classify_trap,
                                   parse_snmp_trap, parse_syslog)
from netwright.sdn.southbound import UnsupportedOperation
from netwright.sdn.southbound.netconf import NetconfAdapter
from netwright.sdn.southbound.restconf import RestconfAdapter, RestconfError


# ══════════════════════════════════════════════════════════════════
# RESTCONF：本地 HTTP 服务（scheme=http 只为测试）
# ══════════════════════════════════════════════════════════════════
class _RestHandler(BaseHTTPRequestHandler):
    seen = []

    def log_message(self, *args):
        pass

    def _auth(self):
        return self.headers.get("Authorization", "")

    def do_GET(self):
        _RestHandler.seen.append(("GET", self.path, self._auth()))
        if self.path.endswith("/missing"):
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b'{"error":"not found"}')
            return
        body = json.dumps({"openconfig-interfaces:interfaces": {
            "interface": [{"name": "Ethernet0", "config": {"enabled": True}}]}}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/yang-data+json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_PATCH(self):
        length = int(self.headers.get("Content-Length") or 0)
        payload = self.rfile.read(length)
        _RestHandler.seen.append(("PATCH", self.path, payload.decode()))
        self.send_response(204)
        self.end_headers()

    def do_DELETE(self):
        _RestHandler.seen.append(("DELETE", self.path, ""))
        self.send_response(204)
        self.end_headers()


@pytest.fixture()
def restconf_server():
    server = ThreadingHTTPServer(("127.0.0.1", 0), _RestHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    _RestHandler.seen = []
    yield server.server_address[1]
    server.shutdown()
    server.server_close()


def _restconf(port):
    return RestconfAdapter(scheme="http", port=port, verify_tls=False)


def _device(host="127.0.0.1", vendor="sonic"):
    return Device(host=host, vendor=vendor, username="admin", password="pw")


def test_restconf_get_and_auth_header(restconf_server):
    adapter = _restconf(restconf_server)
    data = adapter.get_path(_device(), "openconfig-interfaces:interfaces")
    assert "openconfig-interfaces:interfaces" in data
    method, path, auth = _RestHandler.seen[-1]
    assert method == "GET" and auth.startswith("Basic ")


def test_restconf_patch_and_delete(restconf_server):
    adapter = _restconf(restconf_server)
    status = adapter.patch_path(_device(), "openconfig-interfaces:interfaces/interface=Ethernet0",
                                {"openconfig-interfaces:config": {"enabled": False}})
    assert status == 204
    assert any(item[0] == "PATCH" for item in _RestHandler.seen)
    assert adapter.delete_path(_device(), "openconfig-interfaces:interfaces/interface=Ethernet0") == 204


def test_restconf_http_error_is_wrapped(restconf_server):
    adapter = _restconf(restconf_server)
    with pytest.raises(RestconfError) as exc:
        adapter.get_path(_device(), "missing")
    assert exc.value.status == 404


def test_restconf_rejects_cli_commands():
    adapter = RestconfAdapter()
    with pytest.raises(UnsupportedOperation):
        adapter.run_commands(_device(), ["show version"])


def test_restconf_read_config_returns_json(restconf_server):
    adapter = _restconf(restconf_server)
    text = adapter.read_config(_device())
    assert json.loads(text)


# ══════════════════════════════════════════════════════════════════
# NETCONF：注入假会话
# ══════════════════════════════════════════════════════════════════
class _Reply:
    def __init__(self, data="", xml=""):
        self.data = data
        self.xml = xml


class FakeSession:
    def __init__(self):
        self.calls = []
        self.closed = False

    def get_config(self, **kwargs):
        self.calls.append(("get_config", kwargs))
        return _Reply(data="<interfaces/>")

    def edit_config(self, **kwargs):
        self.calls.append(("edit_config", kwargs))
        return _Reply(xml="<ok/>")

    def commit(self):
        self.calls.append(("commit", {}))
        return _Reply(xml="<ok/>")

    def discard_changes(self):
        self.calls.append(("discard", {}))
        return _Reply(xml="<ok/>")

    def close(self):
        self.closed = True


def test_netconf_get_config_with_injected_session():
    session = FakeSession()
    adapter = NetconfAdapter(session_factory=lambda _d: session)
    assert adapter.available()
    xml = adapter.get_config(_device(), filter_xml="<interfaces/>")
    assert xml == "<interfaces/>"
    kind, kwargs = session.calls[0]
    assert kind == "get_config" and kwargs["source"] == "running"
    assert kwargs["filter"] == ("subtree", "<interfaces/>")
    assert session.closed, "会话必须关闭"


def test_netconf_edit_config_and_commit():
    session = FakeSession()
    adapter = NetconfAdapter(session_factory=lambda _d: session)
    adapter.edit_config(_device(), "<config/>", target="candidate")
    adapter.commit(_device())
    kinds = [c[0] for c in session.calls]
    assert kinds[:2] == ["edit_config", "commit"]


def test_netconf_edit_config_rejects_empty():
    adapter = NetconfAdapter(session_factory=lambda _d: FakeSession())
    with pytest.raises(ValueError):
        adapter.edit_config(_device(), "   ")


def test_netconf_without_dependency_reports_unsupported():
    import importlib.util

    if importlib.util.find_spec("ncclient") is not None:
        pytest.skip("本机已安装 ncclient，跳过缺依赖分支")
    adapter = NetconfAdapter()
    assert adapter.available() is False
    with pytest.raises(UnsupportedOperation):
        adapter.get_config(_device())


def test_netconf_rejects_cli_commands():
    adapter = NetconfAdapter(session_factory=lambda _d: FakeSession())
    with pytest.raises(UnsupportedOperation):
        adapter.run_commands(_device(), ["display version"])


# ══════════════════════════════════════════════════════════════════
# Syslog
# ══════════════════════════════════════════════════════════════════
def test_parse_syslog_rfc3164():
    line = ("<189>Oct 11 22:14:15 SW-1 %%LINK-3-UPDOWN: Interface GigabitEthernet0/0/1, "
            "changed state to down")
    record = parse_syslog(line)
    assert record is not None
    assert record.host == "SW-1" and record.severity == 5
    topic, severity, _title = classify_syslog(record)
    assert topic == "link.down" and severity == "critical"


def test_parse_syslog_rfc5424():
    line = ('<165>1 2026-11-02T19:00:00Z core-1 vrp 1234 - - %%SYS-5-CONFIG_I: '
            'configured from console by admin')
    record = parse_syslog(line)
    assert record is not None and record.host == "core-1"
    topic, severity, _ = classify_syslog(record)
    assert topic == "device.config_change" and severity == "warning"


def test_classify_syslog_auth_and_noise():
    auth = parse_syslog("<30>Nov  2 10:00:00 sw sshd[1]: Failed password for admin")
    topic, severity, _ = classify_syslog(auth)
    assert topic == "auth.failure" and severity == "warning"
    noise = parse_syslog("<190>Nov  2 10:00:00 sw app: heartbeat ok")
    topic, severity, _ = classify_syslog(noise)
    assert topic == "syslog.message" and severity == "info"


def test_syslog_parse_never_raises_on_garbage():
    assert parse_syslog("") is None
    assert parse_syslog("\x00\x01binary") is not None      # 降级成裸消息，不抛异常


def test_syslog_listener_receives_udp():
    bus = EventBus()
    listener = SyslogListener(bus=bus, host="127.0.0.1", port=0)
    listener.start()
    try:
        port = listener.bound_port
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.sendto(b"<189>Nov  2 19:00:00 SW-9 %LINK-3-UPDOWN: interface down",
                        ("127.0.0.1", port))
        deadline = time.time() + 5
        while time.time() < deadline and listener.received == 0:
            time.sleep(0.02)
        assert listener.received == 1
        events = bus.snapshot(limit=5)
        assert events and events[0].topic == "link.down"
        assert events[0].data["device_host"] == "SW-9"
    finally:
        listener.stop()


# ══════════════════════════════════════════════════════════════════
# SNMP trap（手工构造 BER 报文）
# ══════════════════════════════════════════════════════════════════
def _tlv(tag: int, value: bytes) -> bytes:
    if len(value) < 0x80:
        return bytes([tag, len(value)]) + value
    length = len(value).to_bytes(2, "big")
    return bytes([tag, 0x82]) + length + value


def _int(value: int) -> bytes:
    return _tlv(0x02, value.to_bytes(max(1, (value.bit_length() + 7) // 8), "big"))


def _oid(dotted: str) -> bytes:
    parts = [int(p) for p in dotted.split(".")]
    out = bytearray([parts[0] * 40 + parts[1]])
    for number in parts[2:]:
        chunk = [number & 0x7F]
        number >>= 7
        while number:
            chunk.append((number & 0x7F) | 0x80)
            number >>= 7
        out.extend(reversed(chunk))
    return _tlv(0x06, bytes(out))


def _trap_bytes(trap_oid: str, if_index: int = 3) -> bytes:
    varbinds = b"".join([
        _tlv(0x30, _oid("1.3.6.1.2.1.1.3.0") + _tlv(0x43, (1000).to_bytes(2, "big"))),
        _tlv(0x30, _oid("1.3.6.1.6.3.1.1.4.1.0") + _oid(trap_oid)),
        _tlv(0x30, _oid("1.3.6.1.2.1.2.2.1.1") + _int(if_index)),
        _tlv(0x30, _oid("1.3.6.1.2.1.2.2.1.8") + _int(2)),
    ])
    pdu = _tlv(0xA7, _int(1) + _int(0) + _int(0) + _tlv(0x30, varbinds))
    return _tlv(0x30, _int(1) + _tlv(0x04, b"public") + pdu)


def test_parse_snmp_link_down_trap():
    trap = parse_snmp_trap(_trap_bytes("1.3.6.1.6.3.1.1.5.3"))
    assert trap is not None
    assert trap.community == "public"
    assert trap.trap_oid == "1.3.6.1.6.3.1.1.5.3"
    assert trap.get("1.3.6.1.2.1.2.2.1.1") == 3
    topic, severity, title = classify_trap(trap)
    assert topic == "link.down" and severity == "critical" and "Down" in title


def test_parse_snmp_garbage_returns_none():
    assert parse_snmp_trap(b"") is None
    assert parse_snmp_trap(b"\x30\x03\x02\x01") is None


def test_snmp_listener_publishes_event():
    bus = EventBus()
    listener = SnmpTrapListener(bus=bus, host="127.0.0.1", port=0)
    listener.start()
    try:
        port = listener.bound_port
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.sendto(_trap_bytes("1.3.6.1.6.3.1.1.5.4"), ("127.0.0.1", port))
        deadline = time.time() + 5
        while time.time() < deadline and listener.received == 0:
            time.sleep(0.02)
        assert listener.received == 1
        events = bus.snapshot(limit=5)
        assert events and events[0].topic == "link.up"
        assert events[0].data["if_index"] == 3
    finally:
        listener.stop()
