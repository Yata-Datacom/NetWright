"""openflow.py — OpenFlow 南向适配器（骨架）。

控制器要成"超级 SDN 控制器"，流表编程是绕不开的一层：
  * 1.3 的 ``OFPT_FLOW_MOD`` 增删改流表；
  * ``OFPT_PACKET_IN`` / ``OFPT_PORT_STATUS`` 是拓扑与告警的事件源；
  * 与 CLI 通道并存：存量设备走 CLI，白盒/OVS 走 OpenFlow。

本文件目前只固定接口与数据结构，避免以后 UI 与策略层反复改签名。
"""
from __future__ import annotations

import importlib.util

from .base import Capability, CommandOutput, SouthboundAdapter, UnsupportedOperation

OFP_VERSION_13 = 0x04


class OpenFlowAdapter(SouthboundAdapter):
    protocol = "openflow"
    display_name = "OpenFlow 1.3（骨架）"
    description = "流表编程南向：flow-mod 下发、packet-in/port-status 事件订阅"
    capabilities = frozenset({
        Capability.FLOW_PROGRAM, Capability.STATE_READ, Capability.EVENT_STREAM,
    })
    transport = "TCP 6633 / 6653"
    requires = ("ryu 或 os-ken（控制器框架）",)

    def available(self) -> bool:
        return (importlib.util.find_spec("os_ken") is not None
                or importlib.util.find_spec("ryu") is not None)

    def note(self) -> str:
        return "骨架：能力已声明，flow-mod 编解码待实装（需 os-ken/ryu）"

    def run_commands(self, device, commands: list[str], timeout: float = 15.0) -> list[CommandOutput]:
        raise UnsupportedOperation(
            "OpenFlow 设备不接受 CLI 命令：请用 program_flows 下发流表")

    def program_flows(self, device, flows: list[dict], timeout: float = 10.0) -> dict:
        """flow 结构约定（与 REST /api/v2/flows 一致）：

        {"table": 0, "priority": 100, "match": {"in_port": 1, "eth_type": 0x0800},
         "actions": [{"type": "output", "port": 2}]}
        """
        if not self.available():
            raise UnsupportedOperation("缺少 os-ken/ryu，无法建立 OpenFlow 通道")
        raise UnsupportedOperation("OpenFlow program_flows 待实装（骨架）")
