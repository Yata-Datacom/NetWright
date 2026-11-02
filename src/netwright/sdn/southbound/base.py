"""base.py — 南向适配器契约（所有协议插件实现这套接口）。

控制器内部只依赖本文件的抽象：新增一种南向协议 = 新增一个 ``SouthboundAdapter``
子类并注册进 ``registry``，北向与 UI 不需要改。

契约刻意保持最小：``probe``（能不能通）、``run_commands``（配置/状态读写）、
``read_config``（整机配置）。OpenFlow 这类流表协议用 ``program_flows``，
默认抛 ``UnsupportedOperation``，由具体插件覆盖。
"""
from __future__ import annotations

import enum
from abc import ABC, abstractmethod
from dataclasses import dataclass, field


class Capability(str, enum.Enum):
    """适配器能力位（UI 与策略编译按能力降级）。"""

    CONFIG_READ = "config_read"       # 读全量配置
    CONFIG_WRITE = "config_write"     # 下发配置命令
    STATE_READ = "state_read"         # 读运行状态（邻居/表项/计数器）
    EVENT_STREAM = "event_stream"     # 事件订阅（telemetry / syslog）
    FLOW_PROGRAM = "flow_program"     # 流表编程（OpenFlow/P4）


class UnsupportedOperation(RuntimeError):
    """适配器声明了能力但当前实现未覆盖（骨架期的主要异常）。"""


@dataclass(frozen=True)
class CommandOutput:
    command: str
    output: str = ""
    error: str = ""

    @property
    def ok(self) -> bool:
        return not self.error


@dataclass(frozen=True)
class AdapterInfo:
    name: str
    protocol: str
    description: str
    capabilities: frozenset
    transport: str = ""
    requires: tuple = ()
    note: str = ""

    def to_dict(self) -> dict:
        return {"name": self.name, "protocol": self.protocol,
                "description": self.description, "transport": self.transport,
                "capabilities": sorted(c.value for c in self.capabilities),
                "requires": list(self.requires), "note": self.note}


class SouthboundAdapter(ABC):
    """南向插件基类。"""

    protocol: str = ""
    display_name: str = ""
    description: str = ""
    capabilities: frozenset = frozenset()
    transport: str = ""
    requires: tuple = ()

    def __init__(self, bus=None):
        self.bus = bus

    # ── 元信息 ──
    def info(self) -> AdapterInfo:
        return AdapterInfo(name=self.display_name or self.protocol,
                           protocol=self.protocol,
                           description=self.description,
                           capabilities=self.capabilities,
                           transport=self.transport,
                           requires=self.requires,
                           note=self.note())

    def note(self) -> str:
        return ""

    def available(self) -> bool:
        """依赖是否就绪（缺库返回 False，UI 灰掉但不报错）。"""
        return True

    def supports(self, capability: Capability) -> bool:
        return capability in self.capabilities

    # ── 生命周期 ──
    def probe(self, device, timeout: float = 5.0) -> bool:
        """端口级连通性探测；默认按 device.port 走 TCP。"""
        import socket
        port = getattr(device, "port", None) or 22
        try:
            with socket.create_connection((device.host, port), timeout=timeout):
                return True
        except OSError:
            return False

    # ── 读写 ──
    @abstractmethod
    def run_commands(self, device, commands: list[str], timeout: float = 15.0) -> list[CommandOutput]:
        """执行命令并返回逐条输出。"""

    def read_config(self, device, timeout: float = 15.0) -> str:
        raise UnsupportedOperation(f"{self.protocol} 适配器未实现 read_config")

    def program_flows(self, device, flows: list[dict], timeout: float = 10.0) -> dict:
        raise UnsupportedOperation(f"{self.protocol} 适配器未实现流表编程")

    # ── 事件 ──
    def poll_events(self, device, timeout: float = 5.0) -> list[dict]:
        return []


@dataclass
class AdapterRegistry:
    """协议 → 适配器实例的注册表。"""

    adapters: dict = field(default_factory=dict)

    def register(self, adapter: SouthboundAdapter) -> SouthboundAdapter:
        self.adapters[adapter.protocol] = adapter
        return adapter

    def get(self, protocol: str) -> SouthboundAdapter | None:
        return self.adapters.get(protocol or "")

    def for_device(self, device) -> SouthboundAdapter | None:
        """按设备的接入协议选适配器（ssh/telnet 都归 CLI 通道）。"""
        proto = getattr(device, "protocol", "ssh") or "ssh"
        if proto in ("ssh", "telnet"):
            return self.get("cli")
        return self.get(proto)

    def describe(self) -> list[dict]:
        out = []
        for adapter in self.adapters.values():
            info = adapter.info().to_dict()
            info["available"] = adapter.available()
            out.append(info)
        return sorted(out, key=lambda i: i["protocol"])

    def __len__(self) -> int:
        return len(self.adapters)
