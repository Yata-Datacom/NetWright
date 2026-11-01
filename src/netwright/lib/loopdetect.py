"""loopdetect.py — MAC 表解析 + 环路告警 + MAC 漂移检测（纯逻辑）。

判定规则（误报优先压低）：
  * 高危：同一台设备 ≥2 个端口学到同一 MAC → 典型二层环路；
  * 中危：同一 MAC 出现在 ≥2 台设备 → 环路或漂移（TRILL/堆叠等合法场景需人工判断）；
  * 漂移：与上一轮快照相比，同一 MAC 在同设备换了端口，或跨设备迁移。
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

_MAC_PATTERNS = (
    re.compile(r"\b([0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4})\b", re.I),
    re.compile(r"\b([0-9a-f]{4}\.[0-9a-f]{4}\.[0-9a-f]{4})\b", re.I),
    re.compile(r"\b([0-9a-f]{2}(?::[0-9a-f]{2}){5})\b", re.I),
)

# 接口名：字母开头含数字/斜杠（GE0/0/1、Gi0/1、Eth1/49、Vlanif10、eth0、Port-channel1…）
_INTF_RE = re.compile(r"^[A-Za-z][\w.-]*\d")

BROADCAST_MACS = {"ffff.ffff.ffff", "ff:ff:ff:ff:ff:ff", "ffff-ffff-ffff"}


@dataclass
class MacRecord:
    mac: str
    device: str
    intf: str
    vlan: str = ""


@dataclass
class LoopAlert:
    severity: str        # critical / warning
    kind: str            # same-device / cross-device / flap
    mac: str
    message: str
    where: list = field(default_factory=list)   # [(device, intf), ...]


def _find_mac(line: str) -> str | None:
    for pat in _MAC_PATTERNS:
        m = pat.search(line)
        if m and m.group(1).lower() not in BROADCAST_MACS:
            return m.group(1).lower()
    return None


def _find_intf(line: str, mac: str) -> str:
    """行内取接口名：跳过 MAC/VLAN 纯数字，取最后一个字母开头含数字的 token。"""
    best = ""
    for tok in line.split():
        if tok.lower() == mac.lower() or re.fullmatch(r"\d{1,4}", tok):
            continue
        if _INTF_RE.match(tok):
            best = tok
    return best


def parse_mac_table(text: str, device: str) -> list[MacRecord]:
    """多厂商 MAC 表容错解析：每行取 MAC + 接口（VLAN 可选）。

    解析策略：
      * MAC 依次尝试 华为横线 / 思科点分 / 冒号 三种格式（广播 MAC 排除）；
      * 接口 = 行内最后一个"字母开头且含数字"的 token（跳过 MAC 与纯数字 VLAN）；
      * 同 (mac, device, intf) 去重。

    :param text: MAC 表命令原始输出
    :param device: 采集来源设备名（写入记录用于跨设备判定）
    :return: MacRecord 列表
    """
    out: list[MacRecord] = []
    seen: set[tuple[str, str, str]] = set()
    for line in text.splitlines():
        mac = _find_mac(line)
        if not mac:
            continue
        intf = _find_intf(line, mac)
        if not intf:
            continue
        vlan_m = re.search(r"\b(?:vlan|vsi|bd)[\s:]*([0-9]{1,4})\b", line, re.I)
        vlan = vlan_m.group(1) if vlan_m else ""
        key = (mac, device, intf)
        if key in seen:
            continue
        seen.add(key)
        out.append(MacRecord(mac=mac, device=device, intf=intf, vlan=vlan))
    return out


def collect_records(device_outputs: list[tuple[str, str]]) -> list[MacRecord]:
    """[(device_name, mac表输出)] → 记录列表。"""
    records: list[MacRecord] = []
    for device, text in device_outputs:
        records.extend(parse_mac_table(text, device))
    return records


def find_loops(records: list[MacRecord]) -> list[LoopAlert]:
    """环路判定：同机多口同一 MAC = critical；跨设备同 MAC = warning。

    :param records: parse_mac_table 的输出（可来自多台设备）
    :return: LoopAlert 列表（message 含设备/端口与处置建议）
    """
    alerts: list[LoopAlert] = []

    # ① 同设备多端口同一 MAC（高危：典型环路）
    by_dev: dict[tuple[str, str], set] = {}
    for r in records:
        by_dev.setdefault((r.mac, r.device), set()).add(r.intf)
    for (mac, dev), intfs in sorted(by_dev.items()):
        if len(intfs) > 1:
            ints = "、".join(sorted(intfs))
            alerts.append(LoopAlert(
                severity="critical", kind="same-device", mac=mac,
                message=f"设备 {dev} 的端口 {ints} 同时学到同一 MAC → 疑似二层环路，"
                        f"建议逐口拔线观察广播速率",
                where=[(dev, i) for i in sorted(intfs)]))

    # ② 跨设备同一 MAC（中危：环路或漂移）
    by_mac: dict[str, set] = {}
    for r in records:
        by_mac.setdefault(r.mac, set()).add(r.device)
    alerted_cross = {a.mac for a in alerts}
    for mac, devs in sorted(by_mac.items()):
        if len(devs) > 1 and mac not in alerted_cross:
            devs_s = "、".join(sorted(devs))
            alerts.append(LoopAlert(
                severity="warning", kind="cross-device", mac=mac,
                message=f"同一 MAC 出现在多台设备（{devs_s}）→ 疑似环路或 MAC 漂移",
                where=[(d, "") for d in sorted(devs)]))
    return alerts


def diff_flapping(prev: list[MacRecord], curr: list[MacRecord]) -> list[LoopAlert]:
    """两轮 MAC 快照对比：发现漂移。

    两种形态分别告警：
      * 同设备换口：prev[mac,dev]=intfA → curr[mac,dev]=intfB；
      * 跨设备迁移：prev 在设备 A，curr 出现在设备 B。

    :param prev: 上一轮记录列表
    :param curr: 本轮记录列表
    :return: LoopAlert 列表（kind=flap）
    """
    prev_map = {(r.mac, r.device): r.intf for r in prev}
    curr_map = {(r.mac, r.device): r.intf for r in curr}
    alerts: list[LoopAlert] = []
    for key, intf in curr_map.items():
        mac, dev = key
        old = prev_map.get(key)
        if old and old != intf:
            alerts.append(LoopAlert(
                severity="warning", kind="flap", mac=mac,
                message=f"MAC 在 {dev} 上从 {old} 漂移到 {intf}",
                where=[(dev, old), (dev, intf)]))
    # 跨设备迁移：上一轮在 A，本轮在 B
    prev_dev = {}
    for r in prev:
        prev_dev.setdefault(r.mac, set()).add(r.device)
    for key, intf in curr_map.items():
        mac, dev = key
        olds = prev_dev.get(mac, set())
        if olds and dev not in olds:
            alerts.append(LoopAlert(
                severity="warning", kind="flap", mac=mac,
                message=f"MAC 从 {('、'.join(sorted(olds)))} 迁移到 {dev}",
                where=[(d, "") for d in sorted(olds)] + [(dev, intf)]))
    return alerts


def loop_devices(alerts: list[LoopAlert]) -> set[str]:
    """涉及告警的设备集合（拓扑高亮用）。"""
    out: set[str] = set()
    for a in alerts:
        for dev, _i in a.where:
            out.add(dev)
    return out


MAC_COMMANDS = {
    "huawei": "display mac-address",
    "h3c": "display mac-address",
    "cisco": "show mac address-table",
    "ruijie": "show mac address-table",
    "sonic": "show mac",
    "mikrotik": "/interface bridge host print",
    "linux": None,      # 网桥表不适合通用解析，跳过
    "vyos": None,
}
