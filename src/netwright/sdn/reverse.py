"""reverse.py — 反向命令生成（回滚的原料）。

原则：**只生成确定安全的反向命令**。配置类意图大多无法从"结果"反推"原状态"
（例如把 access 口改成 trunk，原 VLAN 是多少只有设备知道），这种情况下必须
明确返回"不可回滚"，让上层提示人工处置，而不是猜一条命令把生产网改坏。

返回 ``(commands, reason)``：
  * commands 非空 → 可回滚，reason 说明语义；
  * commands 为空 → 不可回滚，reason 给出人工处置建议。
"""
from __future__ import annotations

import re

VENDOR_UNDO = {
    "huawei": "undo",
    "huawei_ac": "undo",
    "h3c": "undo",
    "h3c_ac": "undo",
    "cisco": "no",
    "cisco_wlc": "no",
    "ruijie": "no",
}


def _vlan_ids(params: dict) -> list[str]:
    raw = str(params.get("vlans") or "")
    return [v for v in re.split(r"[,\s，、]+", raw) if v.strip()]


def reverse_commands(intent_key: str, params: dict, vendor: str) -> tuple[list[str], str]:
    """为一条意图生成反向命令。未知意图一律返回不可回滚。"""
    undo = VENDOR_UNDO.get(vendor)

    if intent_key == "vlan_deploy":
        ids = _vlan_ids(params)
        if not ids:
            return [], "没有解析到 VLAN 列表，无法生成回滚命令"
        if not undo:
            return [], f"厂商 {vendor} 没有登记 undo 关键字，请人工删除 VLAN"
        return [f"{undo} vlan {v}" for v in ids], f"删除本次创建的 {len(ids)} 个 VLAN"

    if intent_key == "port_role":
        mode = str(params.get("mode") or params.get("role") or "")
        intf = str(params.get("interface") or "")
        if not intf:
            return [], "未指定接口，无法回滚"
        # 只有 shutdown 有确定的反向动作；access/trunk 的原状态未知
        if mode in ("shutdown", "关闭"):
            cmd = f"{undo} shutdown" if undo else ""
            if not cmd:
                return [], f"厂商 {vendor} 未登记 undo 关键字，请人工执行 no shutdown"
            return [f"interface {intf}", cmd], f"恢复接口 {intf} 的 up 状态"
        return [], ("端口模式变更的原状态未知（原模式 / 原 VLAN 只有设备知道），"
                    "回滚需人工确认；请先用配置备份恢复")

    if intent_key == "static_route":
        return [], ("静态路由回滚需要原下一跳/出接口信息，"
                    "请根据变更前配置人工删除（undo ip route-static / no ip route）")

    if intent_key == "bgp_neighbor":
        return [], ("删除 BGP 邻居会影响路由收敛，建议人工在维护窗口执行 "
                    "undo peer / no neighbor")

    if intent_key == "mgmt_baseline":
        return [], ("管理面基线（SSH/SNMP/NTP）回滚可能导致失联，"
                    "必须人工在带外通道确认")

    return [], f"意图 {intent_key} 未登记回滚策略"
