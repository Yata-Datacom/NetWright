"""snmp_client.py — SNMPv2c 主动采集（C）：get / get_next。

已有 ``snmp.py`` 只做 trap 接收（被动）。这里补主动 GET，用于设备健康采集
（CPU/内存/温度/端口状态），不引入 pysnmp：v2c 的报文结构足够简单，
用标准库 BER 编解码既能避免重依赖，也能离线单测。

安全约定：community 只在内存里用，不写日志、不进事件消息。
"""
from __future__ import annotations

import socket

from .snmp import _decode_oid, _decode_value, read_tlv

ASN_INTEGER = 0x02
ASN_OCTET = 0x04
ASN_NULL = 0x05
ASN_OID = 0x06
ASN_SEQUENCE = 0x30
PDU_GET = 0xA0
PDU_GETNEXT = 0xA1
PDU_RESPONSE = 0xA2


def _tlv(tag: int, value: bytes) -> bytes:
    length = len(value)
    if length < 0x80:
        header = bytes([tag, length])
    else:
        length_bytes = length.to_bytes((length.bit_length() + 7) // 8, "big")
        header = bytes([tag, 0x80 | len(length_bytes)]) + length_bytes
    return header + value


def _int(value: int) -> bytes:
    if value == 0:
        raw = b"\x00"
    else:
        raw = value.to_bytes((value.bit_length() + 8) // 8, "big", signed=True)
        while len(raw) > 1 and raw[0] == 0xFF and raw[1] & 0x80:
            raw = raw[1:]
        while len(raw) > 1 and raw[0] == 0x00 and not raw[1] & 0x80:
            raw = raw[1:]
    return _tlv(ASN_INTEGER, raw)


def _oid(oid: str) -> bytes:
    parts = [int(p) for p in oid.strip(".").split(".") if p]
    if len(parts) < 2:
        raise ValueError(f"OID 至少两段：{oid}")
    body = bytes([parts[0] * 40 + parts[1]])
    for value in parts[2:]:
        chunk = [value & 0x7F]
        value >>= 7
        while value:
            chunk.append((value & 0x7F) | 0x80)
            value >>= 7
        body += bytes(reversed(chunk))
    return _tlv(ASN_OID, body)


def build_request(community: str, oid: str, request_id: int = 1,
                  pdu: int = PDU_GET) -> bytes:
    """构造 SNMPv2c 请求报文（version=1）。"""
    vb = _tlv(ASN_SEQUENCE, _oid(oid) + _tlv(ASN_NULL, b""))
    pdu_body = (_int(request_id) + _int(0) + _int(0) + _tlv(ASN_SEQUENCE, vb))
    return _tlv(ASN_SEQUENCE,
                _int(1) + _tlv(ASN_OCTET, community.encode("ascii", "replace"))
                + _tlv(pdu, pdu_body))


def parse_response(data: bytes) -> dict | None:
    """解析 GetResponse；结构不对返回 None（不抛异常给采集循环）。"""
    try:
        tag, body, _ = read_tlv(data, 0)
    except Exception:          # noqa: BLE001
        return None
    if tag != ASN_SEQUENCE:
        return None
    try:
        pos = 0
        _, _, pos = read_tlv(body, pos)                  # version
        _, community, pos = read_tlv(body, pos)           # community
        pdu_tag, pdu_body, _ = read_tlv(body, pos)
        if pdu_tag != PDU_RESPONSE:
            return None
        pos = 0
        _, err_status_raw, pos = read_tlv(pdu_body, pos)  # request-id
        _, err_status, pos = read_tlv(pdu_body, pos)
        _, err_index, pos = read_tlv(pdu_body, pos)
        _, vblist, _ = read_tlv(pdu_body, pos)
        pos = 0
        _, varbind, _ = read_tlv(vblist, pos)
        pos = 0
        _, oid_raw, pos = read_tlv(varbind, pos)
        value_tag, value_raw, _ = read_tlv(varbind, pos)
        return {"community": community.decode("ascii", "replace"),
                "error_status": int.from_bytes(err_status, "big") if err_status else 0,
                "error_index": int.from_bytes(err_index, "big") if err_index else 0,
                "oid": _decode_oid(oid_raw),
                "value": _decode_value(value_tag, value_raw)}
    except Exception:          # noqa: BLE001
        return None


def snmp_get(host: str, community: str, oid: str, timeout: float = 2.0,
             port: int = 161) -> tuple[str, object]:
    """同步 GET 一个 OID；超时抛 socket.timeout（由调用方转成人话）。"""
    request_id = 0x5A5A
    packet = build_request(community, oid, request_id)
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.settimeout(timeout)
        sock.sendto(packet, (host, port))
        data, _ = sock.recvfrom(4096)
    result = parse_response(data)
    if result is None:
        raise ValueError("不是合法的 SNMP GetResponse（可能是 v1 或加密响应）")
    if result["error_status"]:
        raise ValueError(f"设备返回 SNMP 错误 status={result['error_status']} "
                         f"index={result['error_index']}")
    return result["oid"], result["value"]
