"""R5 OpenFlow 传输层契约测试：未装 os-ken 不崩、编码可离线验证、live 默认跳过。"""

from __future__ import annotations

import os
import socket
import struct
import sys
import threading

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)


from netwright.lib.inventory import Device
from netwright.sdn.southbound import UnsupportedOperation
from netwright.sdn.southbound.openflow import OpenFlowAdapter
from netwright.sdn.southbound.openflow_transport import (
    OsKenTransport, TransportError, encode_barrier_request, encode_hello,
    of_port_for, parse_port_status,
)

FLOWS = [{"match": {"in_port": 1},
          "actions": [{"type": "push_vlan"}, {"type": "output", "port": 2}]},
         {"match": {"vlan_vid": 10},
          "actions": [{"type": "output", "port": 1}]}]


def test_no_osken_transport_unavailable():
    """未装 os-ken：传输与适配器都不可用（装了则跳过本断言）。"""
    if OsKenTransport.available():
        pytest.skip("本机已安装 os-ken，未装路径的断言不适用")
    assert OsKenTransport.available() is False
    t = OsKenTransport(host="192.0.2.9")
    with pytest.raises(TransportError) as exc:
        t.connect()
    assert "os-ken" in str(exc.value) and "pip install" in str(exc.value)


def test_no_osken_adapter_program_flows_keeps_contract():
    """未装 os-ken：program_flows 仍抛 UnsupportedOperation（现有契约不变）。"""
    if OsKenTransport.available():
        pytest.skip("本机已安装 os-ken，未装路径的断言不适用")
    adapter = OpenFlowAdapter()
    assert adapter.available() is False
    with pytest.raises(UnsupportedOperation) as exc:
        adapter.program_flows(Device(host="192.0.2.1"), FLOWS)
    assert "已校验并编码 2 条" in str(exc.value), "保留既有报错前缀"
    assert "os-ken" in str(exc.value), "报错要给安装提示"


def test_hello_and_barrier_encoding():
    """握手/屏障报文逐字节正确（8 字节头，OF1.3）。"""
    assert encode_hello(7) == struct.pack("!BBHI", 4, 0, 8, 7)
    assert encode_barrier_request(9) == struct.pack("!BBHI", 4, 20, 8, 9)


def test_parse_port_status():
    body = struct.pack("!B7xI", 0, 3) + b"\x00" * 56       # reason=0(ADD), port 3
    info = parse_port_status(body)
    assert info["reason"] == 0 and info["port_no"] == 3
    assert parse_port_status(b"")["reason"] is None


def test_of_port_for_device():
    assert of_port_for(Device(host="10.0.0.1", port=22)) == 6653, "管理口 22 不当 OF 端口"
    assert of_port_for(Device(host="10.0.0.1", port=6633)) == 6633
    assert of_port_for(Device(host="10.0.0.1")) == 6653


def test_send_requires_connect_first():
    t = OsKenTransport()
    with pytest.raises(TransportError) as exc:
        t.send_flow_mod(b"\x00" * 16)
    assert "connect" in str(exc.value)


class _FakeSwitch:
    """最小 OF1.3 对端：收 HELLO 回 HELLO，收 flow_mod+barrier 回 barrier。"""

    def __init__(self):
        self.flow_mods: list[bytes] = []
        self._xid = 0

    def serve(self, conn: socket.socket):
        def _send(msg_type: int, xid: int, payload: bytes = b""):
            conn.sendall(struct.pack("!BBHI", 4, msg_type, 8 + len(payload), xid) + payload)
        while True:
            header = conn.recv(8)
            if len(header) < 8:
                return
            _v, msg_type, length, xid = struct.unpack("!BBHI", header)
            body = b""
            while len(body) < length - 8:
                body += conn.recv(length - 8 - len(body))
            if msg_type == 0:                       # HELLO
                _send(0, xid)
            elif msg_type == 14:                    # FLOW_MOD
                self.flow_mods.append(body)
            elif msg_type == 20:                    # BARRIER_REQUEST
                _send(21, xid)                      # BARRIER_REPLY


def test_live_flow_mod_against_fake_switch():
    """有 os-ken 时：对本地假交换机跑通"连接 → 握手 → 下发 1 条 flow → barrier 确认"。

    不需要真实 OVS：对端行为用 socket 服务模拟（协议语义按 OF1.3 头部）。
    """
    if not OsKenTransport.available():
        pytest.skip("未安装 os-ken（可选依赖）：传输层被能力闸门关闭")
    server = socket.socket()
    server.bind(("127.0.0.1", 0))
    server.listen(1)
    port = server.getsockname()[1]
    switch = _FakeSwitch()
    accepted = []

    def runner():
        conn, _addr = server.accept()
        accepted.append(conn)
        switch.serve(conn)

    thread = threading.Thread(target=runner, daemon=True)
    thread.start()

    transport = OsKenTransport(host="127.0.0.1", port=port, timeout=3.0)
    transport.connect()
    compiled = OpenFlowAdapter().build_flow_mods(FLOWS)
    result = transport.send_flow_mod(bytes.fromhex(compiled[0]["hex"]))
    assert result["barrier"] is True
    transport.close()
    thread.join(timeout=2)
    assert len(switch.flow_mods) == 1, "对端应收到一条 flow_mod"


@pytest.mark.openflow_live
def test_openflow_live_real_switch():
    """真实下发：需要 OVS/mininet 在 127.0.0.1:6653（CI 与本机默认跳过）。"""
    probe = socket.socket()
    try:
        probe.settimeout(1.0)
        probe.connect(("127.0.0.1", 6653))
    except OSError:
        pytest.skip("127.0.0.1:6653 没有 OpenFlow 对端（装 OVS 后运行 pytest -m openflow_live）")
    finally:
        probe.close()
    transport = OsKenTransport(host="127.0.0.1", port=6653, timeout=3.0)
    transport.connect()
    try:
        flow = {"match": {"in_port": 1}, "actions": [{"type": "output", "port": 2}]}
        compiled = OpenFlowAdapter().build_flow_mods([flow])
        result = transport.send_flow_mod(bytes.fromhex(compiled[0]["hex"]))
        assert result["barrier"] is True
    finally:
        transport.close()
