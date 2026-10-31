"""topology.py — LLDP/CDP 邻居输出解析 + 拓扑图构建（纯函数）。

支持的输出（v1）：
  * 华为  display lldp neighbor brief（表格行式）
  * 华为  display lldp neighbor（分段式）
  * 思科  show cdp neighbors（表格行式）
  * H3C   display lldp neighbor-information brief（表格行式）
解析契约见本文件底部的样例字符串（tests/test_controller.py 用它们做回归）。
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field


@dataclass
class Link:
    device: str          # 本端设备名（由调用方传入，采集时的设备）
    local_intf: str
    peer_device: str
    peer_intf: str

    def normalized(self) -> "Link":
        """接口名归一化，减少同链路两种写法（Gi/GE vs GigabitEthernet）导致的重复边。"""
        def norm(name: str) -> str:
            m = re.match(r"^(Gig|Gi|GE)(\d.*)$", name, re.I)
            if m:
                return "GigabitEthernet" + m.group(2)
            return name
        return Link(self.device, norm(self.local_intf),
                    self.peer_device, norm(self.peer_intf))


@dataclass
class Topology:
    nodes: set = field(default_factory=set)
    links: list[Link] = field(default_factory=list)

    def add_links(self, device: str, links: list[Link]):
        self.nodes.add(device)
        for l in links:
            self.nodes.add(l.peer_device)
            self.links.append(l)

    def undirected_edges(self) -> list[tuple[str, str, str, str]]:
        """去重后的无向边：A-B 与 B-A 视为同一条，保留一条（含两端接口名）。"""
        seen: set = set()
        out = []
        for l in self.links:
            key = tuple(sorted([l.device, l.peer_device])) + tuple(
                sorted([l.local_intf, l.peer_intf]))[:0]  # 仅按设备对去重
            dev_key = tuple(sorted([l.device, l.peer_device]))
            if dev_key in seen:
                continue
            seen.add(dev_key)
            out.append((l.device, l.local_intf, l.peer_device, l.peer_intf))
        return out


# ── 华为 display lldp neighbor brief（表格行式）────────────────────
# 样例：
# Local Intf    Neighbor Intf     Neighbor Device       Exptime(s)
# GE0/0/1       GE0/0/24          SW-2                  105
def parse_huawei_brief(text: str, device: str) -> list[Link]:
    links = []
    for line in text.splitlines():
        m = re.match(
            r"^\s*(\S+)\s+(\S+)\s+(\S+)\s+\d+\s*$", line)
        if not m:
            continue
        local, peer_intf, peer_dev = m.group(1), m.group(2), m.group(3)
        if peer_dev.lower() in ("neighbor", "device", "intf"):
            continue
        links.append(Link(device, local, peer_dev, peer_intf).normalized())
    return links


# ── 华为 display lldp neighbor（分段式）────────────────────────────
# Local Interface : GigabitEthernet0/0/1
#  Neighbour Interface : GigabitEthernet0/0/24
#  Neighbour Device : SW-2
def parse_huawei_block(text: str, device: str) -> list[Link]:
    links = []
    local = peer_intf = peer_dev = None
    for line in text.splitlines():
        m = re.search(r"Local\s+Interface\s*:\s*(\S+)", line, re.I)
        if m:
            local = m.group(1)
            continue
        m = re.search(r"Neighbour\s+Interface\s*:\s*(\S+)", line, re.I)
        if m:
            peer_intf = m.group(1)
            continue
        m = re.search(r"Neighbour\s+Device\s*:\s*(\S+)", line, re.I)
        if m:
            peer_dev = m.group(1)
        if local and peer_intf and peer_dev:
            links.append(Link(device, local, peer_dev, peer_intf).normalized())
            local = peer_intf = peer_dev = None
    return links


# ── 思科 show cdp neighbors（表格行式，列按 ≥2 空格切分）────────────
# Device ID        Local Intrfce     Holdtme  Capability  Platform   Port ID
# SW-2             Gig 0/24          167      S I         WS-C2960   Gig 0/1
def parse_cisco_cdp(text: str, device: str) -> list[Link]:
    links = []
    for line in text.splitlines():
        if "Local Intrfce" in line or not line.strip():
            continue
        fields = re.split(r"\s{2,}", line.strip())
        if len(fields) < 6:
            continue
        peer_dev, local, peer_intf = fields[0], fields[1], fields[-1]
        if peer_dev.lower() in ("device", "id"):
            continue
        links.append(Link(device, local, peer_dev, peer_intf).normalized())
    return links


# ── H3C display lldp neighbor-information brief（表格行式）─────────
# Interface GE1/0/48 has 1 neighbor(s):
#   Neighbor: GE1/0/24   System Name: SW-2
def parse_h3c_brief(text: str, device: str) -> list[Link]:
    links = []
    local = None
    for line in text.splitlines():
        m = re.match(r"^\s*(?:Interface\s+)?(\S+)\s+has\s+\d+\s+neighbor", line, re.I)
        if m:
            local = m.group(1)
            continue
        m = re.search(r"Neighbor\s*:\s*(\S+)\s+.*?System\s*Name\s*:\s*(\S+)", line, re.I)
        if m and local:
            links.append(Link(device, local, m.group(2), m.group(1)).normalized())
            local = None
    return links


def parse_neighbors(vendor: str, text: str, device: str) -> list[Link]:
    """按厂商选择解析器；未知厂商抛 ValueError。"""
    parsers = {
        "huawei": [parse_huawei_brief, parse_huawei_block],
        "h3c": [parse_h3c_brief, parse_huawei_block],
        "cisco": [parse_cisco_cdp],
        "ruijie": [parse_cisco_cdp],   # 锐捷 CDP/LDP 风格与思科一致
    }
    if vendor not in parsers:
        raise ValueError(f"拓扑发现暂不支持厂商 {vendor}")
    for fn in parsers[vendor]:
        links = fn(text, device)
        if links:
            return links
    return []


# 每厂商采集命令
DISCOVERY_COMMANDS = {
    "huawei": ["display lldp neighbor brief", "display lldp neighbor"],
    "h3c": ["display lldp neighbor-information brief"],
    "cisco": ["show cdp neighbors", "show lldp neighbors"],
    "ruijie": ["show cdp neighbors"],
}


def build_topology(device_outputs: list[tuple[str, str, str]]) -> Topology:
    """把多台设备的采集输出拼成拓扑。

    :param device_outputs: [(device_name, vendor, 命令输出拼接文本)]
    """
    topo = Topology()
    for device, vendor, text in device_outputs:
        links = parse_neighbors(vendor, text, device)
        topo.add_links(device, links)
    return topo
