"""netconf.py — NETCONF 南向适配器（骨架）。

当前状态：**能力已声明、连接层未实装**。设计意图是后续用 ncclient 走
``<get-config>`` / ``<edit-config>`` 替代 CLI 的脆弱回显解析。

实现时应遵循的约束（写在这里，避免以后重新设计）：
  * 凭据沿用 ``inventory.Device``，端口默认 830；
  * 一个设备一个 session，批量下发用 ``candidate`` 数据存储 + ``commit``；
  * 失败必须回滚（``discard-changes``），并把结果发布为 ``southbound.error`` 事件。
"""
from __future__ import annotations

import importlib.util

from .base import (Capability, CommandOutput, SouthboundAdapter,
                   UnsupportedOperation)


class NetconfAdapter(SouthboundAdapter):
    protocol = "netconf"
    display_name = "NETCONF（骨架）"
    description = "结构化配置南向：get-config / edit-config，替代 CLI 回显解析"
    capabilities = frozenset({
        Capability.CONFIG_READ, Capability.CONFIG_WRITE, Capability.STATE_READ,
        Capability.EVENT_STREAM,
    })
    transport = "TCP 830 / SSH 子系统"
    requires = ("ncclient>=0.6",)

    def available(self) -> bool:
        return importlib.util.find_spec("ncclient") is not None

    def note(self) -> str:
        return "骨架：已声明能力，连接与 RPC 待实装（需安装 ncclient）"

    def run_commands(self, device, commands: list[str], timeout: float = 15.0) -> list[CommandOutput]:
        # NETCONF 不接受 CLI 命令集；由 read_config 走结构化接口
        raise UnsupportedOperation(
            "NETCONF 适配器尚未实装：请使用 CLI 通道，或安装 ncclient 后实现 RPC 映射")

    def read_config(self, device, timeout: float = 15.0) -> str:
        if not self.available():
            raise UnsupportedOperation("缺少依赖 ncclient，无法建立 NETCONF 会话")
        raise UnsupportedOperation("NETCONF read_config 待实装（骨架）")
