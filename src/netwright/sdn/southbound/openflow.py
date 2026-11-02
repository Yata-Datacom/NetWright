"""openflow.py — OpenFlow 1.3 南向：流表模型 + flow_mod 编码（传输层暂未实装）。

分工说明（为什么不"假装能下发"）：
  * **本模块负责**：把"意图/流表项"翻译成合法的 OF1.3 ``flow_mod`` 字节，
    并做严格校验（字段名、值域、动作组合）——这部分可以离线单测，也能直接喂给
    任何 OpenFlow 控制器（os-ken/ryu）或交换机；
  * **暂不负责**：建立 TCP 6633/6653 通道、握手、barrier、错误回复。
    没有真实白盒设备时，假装"下发成功"比不做更危险。

支持的 match 字段（OXM）：in_port / eth_type / eth_src / eth_dst / vlan_vid /
ip_proto / ipv4_src / ipv4_dst；动作：output / drop / push_vlan。
"""
from __future__ import annotations

import importlib.util
import ipaddress
import struct

from .base import Capability, CommandOutput, SouthboundAdapter, UnsupportedOperation

OFP_VERSION_13 = 4
OFT_FLOW_MOD = 14
OFPFC_ADD = 0
OFPFC_DELETE = 3
OFPIT_APPLY_ACTIONS = 4
OFPAT_OUTPUT = 0
OFPAT_PUSH_VLAN = 17
OXM_CLASS_OPENFLOW_BASIC = 0x8000
OFP_MAX_PORT = 0xFFFFFF00        # OFPP_ANY / CONTROLLER 等保留端口

# 字段 → (OXM field 编号, 字节长度)
MATCH_FIELDS = {
    "in_port": (0, 4),
    "eth_dst": (3, 6),
    "eth_src": (2, 6),
    "eth_type": (5, 2),
    "vlan_vid": (6, 2),
    "ip_proto": (10, 1),
    "ipv4_src": (11, 4),
    "ipv4_dst": (12, 4),
}

ACTIONS = ("output", "drop", "push_vlan")


class FlowError(ValueError):
    """流表项不合法（字段/值域/动作）。"""


def _pad8(data: bytes) -> bytes:
    return data + b"\x00" * ((8 - len(data) % 8) % 8)


def _mac_bytes(value: str) -> bytes:
    parts = value.split(":")
    if len(parts) != 6:
        raise FlowError(f"MAC 格式不对：{value}")
    try:
        return bytes(int(p, 16) for p in parts)
    except ValueError as exc:
        raise FlowError(f"MAC 格式不对：{value}") from exc


def _field_bytes(name: str, value) -> bytes:
    field_id, length = MATCH_FIELDS[name]
    if name in ("eth_src", "eth_dst"):
        raw = _mac_bytes(str(value))
    elif name in ("ipv4_src", "ipv4_dst"):
        raw = ipaddress.IPv4Address(str(value)).packed
    elif name == "vlan_vid":
        # OpenFlow 里 VLAN id 带 OFPVID_PRESENT(0x1000) 标志位
        raw = struct.pack("!H", (int(value) & 0x0FFF) | 0x1000)
    else:
        raw = int(value).to_bytes(length, "big", signed=False)
    return struct.pack("!HBB", OXM_CLASS_OPENFLOW_BASIC | field_id, 0, length) + raw


def build_match(match: dict) -> bytes:
    """把 match dict 编成 OFPMT（type=1）+ 若干 OXM，并 8 字节对齐。"""
    body = b""
    for name, value in (match or {}).items():
        if name not in MATCH_FIELDS:
            raise FlowError(f"不支持的 match 字段：{name}（可用：{', '.join(MATCH_FIELDS)}）")
        body += _field_bytes(name, value)
    ompm = struct.pack("!HH", 1, 4 + len(body)) + body
    return _pad8(ompm)


def build_actions(actions: list) -> bytes:
    """动作列表 → 指令段（apply_actions）。"""
    encoded = b""
    for action in actions or []:
        kind = str(action.get("type", "")).lower()
        if kind == "output":
            port = int(action.get("port", 0))
            if not (0 < port <= 0xFFFFFF00):
                raise FlowError(f"output 端口非法：{port}")
            encoded += struct.pack("!HHIH6x", OFPAT_OUTPUT, 16, port, 0)
        elif kind == "push_vlan":
            encoded += struct.pack("!HHH2x", OFPAT_PUSH_VLAN, 8, 0x8100)
        elif kind == "drop":
            if len(actions) > 1:
                raise FlowError("drop 不能和其他动作混用")
            continue
        else:
            raise FlowError(f"不支持的动作：{kind}（可用：{', '.join(ACTIONS)}）")
    if not encoded:
        return b""      # 空指令 = 丢弃
    instruction = struct.pack("!HH", OFPIT_APPLY_ACTIONS, 8 + len(encoded)) + encoded
    return _pad8(instruction)


class FlowEntry:
    """一条流表项的校验与编码。"""

    def __init__(self, table: int = 0, priority: int = 100, match: dict | None = None,
                 actions: list | None = None, idle_timeout: int = 0,
                 hard_timeout: int = 0, cookie: int = 0, command: int = OFPFC_ADD):
        self.table = int(table)
        self.priority = int(priority)
        self.match = dict(match or {})
        self.actions = list(actions or [])
        self.idle_timeout = int(idle_timeout)
        self.hard_timeout = int(hard_timeout)
        self.cookie = int(cookie)
        self.command = int(command)
        self.validate()

    @classmethod
    def from_dict(cls, data: dict) -> FlowEntry:
        return cls(table=data.get("table", 0), priority=data.get("priority", 100),
                   match=data.get("match") or {}, actions=data.get("actions") or [],
                   idle_timeout=data.get("idle_timeout", 0),
                   hard_timeout=data.get("hard_timeout", 0),
                   cookie=data.get("cookie", 0))

    def validate(self) -> FlowEntry:
        if not (0 <= self.table <= 254):
            raise FlowError(f"table 必须是 0-254（收到 {self.table}）")
        if not (0 <= self.priority <= 65535):
            raise FlowError(f"priority 必须是 0-65535（收到 {self.priority}）")
        for name in ("idle_timeout", "hard_timeout"):
            value = getattr(self, name)
            if not (0 <= value <= 65535):
                raise FlowError(f"{name} 必须是 0-65535（收到 {value}）")
        if not self.match and not self.actions:
            raise FlowError("空流表项（既没有 match 也没有 actions）无意义")
        if not any(a.get("type") == "drop" for a in self.actions) and not self.actions:
            raise FlowError("动作不能为空：要么 output/push_vlan，要么显式 drop")
        build_match(self.match)          # 触发字段校验
        build_actions(self.actions)
        return self

    def to_dict(self) -> dict:
        return {"table": self.table, "priority": self.priority, "match": self.match,
                "actions": self.actions, "idle_timeout": self.idle_timeout,
                "hard_timeout": self.hard_timeout, "cookie": self.cookie}

    def encode(self, xid: int = 1) -> bytes:
        """编码成完整的 OF1.3 flow_mod 报文（含 8 字节头）。"""
        match = build_match(self.match)
        instructions = build_actions(self.actions)
        body = struct.pack(
            "!QQBBHHHIIIH2x", self.cookie, 0, self.table, self.command,
            self.idle_timeout, self.hard_timeout, self.priority,
            0xFFFFFFFF, 0xFFFFFFFF, 0xFFFFFFFF, 0) + match + instructions
        header = struct.pack("!BBHI", OFP_VERSION_13, OFT_FLOW_MOD, 8 + len(body), xid)
        return header + body

    def hexdump(self, xid: int = 1) -> str:
        return self.encode(xid).hex()


class OpenFlowAdapter(SouthboundAdapter):
    protocol = "openflow"
    display_name = "OpenFlow 1.3"
    description = "流表模型校验与 flow_mod 编码（传输层未实装，避免假下发）"
    capabilities = frozenset({
        Capability.FLOW_PROGRAM, Capability.STATE_READ, Capability.EVENT_STREAM,
    })
    transport = "TCP 6633 / 6653"
    requires = ("os-ken 或 ryu（仅传输层需要）",)

    def available(self) -> bool:
        """编码能力永远可用；这里表示"能不能真的连交换机"。"""
        return (importlib.util.find_spec("os_ken") is not None
                or importlib.util.find_spec("ryu") is not None)

    def note(self) -> str:
        return "已实装校验 + flow_mod 编码；TCP 通道与握手待实装"

    def run_commands(self, device, commands: list[str], timeout: float = 15.0) -> list[CommandOutput]:
        raise UnsupportedOperation("OpenFlow 设备不接受 CLI 命令：请用 program_flows")

    # ── 离线可用：校验 + 编码 ──
    def build_flow_mods(self, flows: list[dict], xid: int = 1) -> list[dict]:
        """把 flow 列表编译成报文；返回 [{flow, hex, bytes}]，不发送。"""
        out = []
        for index, raw in enumerate(flows or []):
            entry = FlowEntry.from_dict(raw)
            payload = entry.encode(xid + index)
            out.append({"flow": entry.to_dict(), "bytes": len(payload),
                        "hex": payload.hex()})
        return out

    def program_flows(self, device, flows: list[dict], timeout: float = 10.0) -> dict:
        """传输层未实装：先校验+编码，再明确拒绝发送。"""
        compiled = self.build_flow_mods(flows)
        raise UnsupportedOperation(
            f"已校验并编码 {len(compiled)} 条 flow_mod，但 OpenFlow 通道尚未实装："
            "请用 /api/v2/openflow/validate 做 dry-run，或接入 os-ken/ryu 后实现 program_flows")
