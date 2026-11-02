"""cli.py — CLI 南向适配器（SSH / Telnet），当前唯一完整实装的通道。

复用既有 ``lib/ssh_client``（已处理分页关闭、提示符裁剪、Telnet IAC 剥离），
控制器只是把它的结果包装成 ``CommandOutput`` 并补上能力声明与事件。
"""
from __future__ import annotations

import importlib.util

from .base import Capability, CommandOutput, SouthboundAdapter


class CliAdapter(SouthboundAdapter):
    protocol = "cli"
    display_name = "CLI（SSH / Telnet）"
    description = "命令行南向：逐条下发命令并回收回显，适配华为/思科/H3C/锐捷等存量网络"
    capabilities = frozenset({
        Capability.CONFIG_READ, Capability.CONFIG_WRITE, Capability.STATE_READ,
    })
    transport = "TCP 22 / 23"

    def available(self) -> bool:
        # Telnet 走标准库，SSH 需要 paramiko
        return importlib.util.find_spec("paramiko") is not None

    def note(self) -> str:
        return "SSH 依赖 paramiko；Telnet 仅用标准库"

    def run_commands(self, device, commands: list[str], timeout: float = 15.0) -> list[CommandOutput]:
        from ...lib.ssh_client import run_commands as _run

        raw = _run(device, list(commands), timeout=timeout)
        out = [CommandOutput(command=cmd, output=text, error=err)
               for _title, cmd, text, err in raw]
        if self.bus is not None:
            failed = [c.command for c in out if not c.ok]
            self.bus.publish(
                "southbound.commands", 
                f"{getattr(device, 'host', '?')}: 执行 {len(out)} 条命令"
                + (f"，{len(failed)} 条失败" if failed else ""),
                severity="warning" if failed else "info",
                source="cli", device=getattr(device, "host", ""),
                failed=failed[:5])
        return out

    def read_config(self, device, timeout: float = 15.0) -> str:
        """读取整机配置（各厂商的 show running-config 等价命令）。"""
        command = {
            "huawei": "display current-configuration",
            "huawei_ac": "display current-configuration",
            "h3c": "display current-configuration",
            "h3c_ac": "display current-configuration",
            "cisco": "show running-config",
            "cisco_wlc": "show running-config",
            "ruijie": "show running-config",
            "vyos": "show configuration commands",
            "sonic": "show runningconfiguration all",
            "mikrotik": "/export",
            "linux": "cat /etc/os-release",
        }.get(getattr(device, "vendor", ""), "show running-config")
        results = self.run_commands(device, [command], timeout=timeout)
        return results[0].output if results else ""
