"""netwright.sdn — SDN 控制器内核（v2 骨架）。

分层：

  events.py    进程内事件总线（环形历史 + 订阅）
  model.py     控制器图模型（Node / Edge / NetworkGraph）
  policy.py    意图 → 策略编译（不产生副作用）
  store.py     控制器状态仓库（图 + 策略 + 统计，可持久化）
  southbound/  南向适配器（CLI 实装；NETCONF / OpenFlow / RESTCONF 骨架）
  nbapi.py     北向 REST v2 路由

与 ``netwright.lib.controller`` 的关系：后者是既有的"意图下发 + v1 REST"，
本包在其上补齐控制器应有的状态面（拓扑图、事件、策略、南向抽象）。
"""
from __future__ import annotations

from .events import Event, EventBus
from .model import Edge, NetworkGraph, Node, normalize_interface
from .policy import CompileResult, Policy, PolicyCompiler
from .store import ControllerStore
from .southbound import (AdapterRegistry, Capability, SouthboundAdapter,
                         UnsupportedOperation, default_registry)

__all__ = [
    "Event", "EventBus", "Edge", "NetworkGraph", "Node", "normalize_interface",
    "CompileResult", "Policy", "PolicyCompiler", "ControllerStore",
    "AdapterRegistry", "Capability", "SouthboundAdapter", "UnsupportedOperation",
    "default_registry",
]
