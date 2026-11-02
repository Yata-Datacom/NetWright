"""openflow_plan.py — 意图 → OpenFlow flow 计划（R4）。

与 CLI 命令的关系：同一条意图，CLI 渲染走 ``intents.render_intent``，
flow 计划走本模块；两者都是"编译产物"，下发都必须经过生命周期/显式确认。

设计原则（与 reverse.py 的"不猜命令"同源）：
  * 流表计划的 match 离不开**端口事实参数**（in_port / out_port）。
    意图表单没填端口时返回 ``[]``——宁缺勿猜，猜一个端口的流表比没有更危险；
  * 不认识的意图一律 ``[]``，绝不抛错（调用方按"无流表计划"降级）；
  * 产物是 plan（草稿），供 ``FlowEntry`` 校验、``/api/v2/openflow/validate``
    编码 dry-run；真正的下发要等 OpenFlow 通道实装（R5）。

已知建模边界：动作模型只有 push_vlan（推 0x8100 头），没有 set_field，
因此 ingress 流的 vid 指派暂以 push_vlan 表示——这是 v0.1 计划粒度，
注释里写明，不假装完整。
"""
from __future__ import annotations

import re

_MAX_PORT = 0xFFFFFF00        # OFPP_MAX（保留端口之下）
_MAX_VLAN = 4094


def _vlan_ids(raw: str) -> list[int]:
    ids = []
    for token in re.split(r"[,\s，、]+", str(raw or "")):
        if token.strip() and re.fullmatch(r"\d{1,4}", token.strip()):
            n = int(token)
            if 1 <= n <= _MAX_VLAN:
                ids.append(n)
    return ids


def flows_for(intent_key: str, params: dict, vendor: str) -> list[dict]:
    """把一条意图编译成 OpenFlow flow 列表（计划，不下发）。

    vlan_deploy：每个 VLAN 两条 flow——
      * ``ingress_tag``：access 口（in_port）进来的流量打 VLAN 并转发到
        trunk（out_port）——对应 CLI 侧的 ``vlan batch`` + 端口放行；
      * ``egress_untag``：trunk 口收到的该 VLAN 流量送回 access 口
        （出口按 access 语义剥标签）。
    ``in_port`` / ``out_port`` 是流表计划的事实参数：缺失或非法 → 返回 ``[]``。

    其他意图（暂无 flow 语义）一律返回 ``[]``，不报错。
    """
    params = params or {}
    if intent_key != "vlan_deploy":
        return []
    ids = _vlan_ids(params.get("vlans"))
    if not ids:
        return []
    try:
        in_port = int(params.get("in_port") or 0)
        out_port = int(params.get("out_port") or 0)
    except (TypeError, ValueError):
        return []
    if not (0 < in_port <= _MAX_PORT) or not (0 < out_port <= _MAX_PORT):
        return []
    if in_port == out_port:
        return []

    flows: list[dict] = []
    for vid in ids:
        flows.append({
            "role": "ingress_tag", "vlan": vid,
            "table": 0, "priority": 200,
            "match": {"in_port": in_port},
            "actions": [{"type": "push_vlan"},
                        {"type": "output", "port": out_port}],
        })
        flows.append({
            "role": "egress_untag", "vlan": vid,
            "table": 0, "priority": 200,
            "match": {"in_port": out_port, "vlan_vid": vid},
            "actions": [{"type": "output", "port": in_port}],
        })
    return flows
