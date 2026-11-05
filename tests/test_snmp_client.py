"""SNMPv2c 主动采集（C）：报文编码、响应解析、超时行为。"""
from __future__ import annotations

import os
import socket
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from netwright.sdn.sources.snmp_client import (PDU_GET, PDU_GETNEXT, PDU_RESPONSE,
                                               _int, _oid, _tlv, build_request,
                                               parse_response)


def _response(oid: str, value: str, community: str = "public",
              request_id: int = 0x5A5A) -> bytes:
    """构造一个合法的 GetResponse（用同一套编码器，保证格式自洽）。"""
    varbind = _tlv(0x30, _oid(oid) + _tlv(0x04, value.encode()))
    pdu_body = _int(request_id) + _int(0) + _int(0) + _tlv(0x30, varbind)
    return _tlv(0x30, _int(1) + _tlv(0x04, community.encode()) + _tlv(PDU_RESPONSE, pdu_body))


def test_request_has_sequence_version_and_pdu():
    packet = build_request("public", "1.3.6.1.2.1.1.3.0")
    assert packet[0] == 0x30
    assert b"public" in packet
    assert bytes([PDU_GET]) in packet
    getnext = build_request("public", "1.3.6.1.2.1.1.3.0", pdu=PDU_GETNEXT)
    assert bytes([PDU_GETNEXT]) in getnext


def test_oid_encoding_roundtrip_through_parser():
    oid = "1.3.6.1.2.1.1.5.0"
    parsed = parse_response(_response(oid, "core-sw-01"))
    assert parsed is not None
    assert parsed["oid"] == oid
    assert parsed["value"] == "core-sw-01"


def test_parse_rejects_garbage_and_wrong_pdu():
    assert parse_response(b"not snmp") is None
    empty = _tlv(0x30, _int(1) + _tlv(0x04, b"public") + _tlv(0xA1, _int(1)))
    assert parse_response(empty) is None


def test_parse_reports_error_status():
    varbind = _tlv(0x30, _oid("1.3.6.1.2.1.1.1.0") + _tlv(0x05, b""))
    pdu_body = _int(1) + _int(2) + _int(1) + _tlv(0x30, varbind)
    packet = _tlv(0x30, _int(1) + _tlv(0x04, b"public") + _tlv(PDU_RESPONSE, pdu_body))
    parsed = parse_response(packet)
    assert parsed["error_status"] == 2
    assert parsed["error_index"] == 1


def test_snmp_get_times_out_cleanly(monkeypatch):
    from netwright.sdn.sources import snmp_client

    def fake_recvfrom(self, size):
        raise socket.timeout("timed out")

    monkeypatch.setattr(socket.socket, "recvfrom", fake_recvfrom)
    with pytest.raises(socket.timeout):
        snmp_client.snmp_get("127.0.0.1", "public", "1.3.6.1.2.1.1.3.0", timeout=0.1)
