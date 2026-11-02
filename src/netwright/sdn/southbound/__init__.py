"""southbound — 南向适配器集合与默认注册表。

新增协议：继承 ``SouthboundAdapter`` → 在 ``default_registry()`` 里注册一行。
控制器其余部分（策略编译、北向 REST、UI 的「南向」面板）都只读注册表。
"""
from __future__ import annotations

from .base import (AdapterInfo, AdapterRegistry, Capability, CommandOutput,
                   SouthboundAdapter, UnsupportedOperation)
from .cli import CliAdapter
from .netconf import NetconfAdapter
from .openflow import OpenFlowAdapter
from .restconf import RestconfAdapter

__all__ = [
    "AdapterInfo", "AdapterRegistry", "Capability", "CommandOutput",
    "SouthboundAdapter", "UnsupportedOperation",
    "CliAdapter", "NetconfAdapter", "OpenFlowAdapter", "RestconfAdapter",
    "default_registry",
]


def default_registry(bus=None) -> AdapterRegistry:
    """四个内置适配器：CLI 实装，其余为可插拔骨架。"""
    registry = AdapterRegistry()
    for adapter in (CliAdapter(bus), NetconfAdapter(bus),
                    OpenFlowAdapter(bus), RestconfAdapter(bus)):
        registry.register(adapter)
    return registry
