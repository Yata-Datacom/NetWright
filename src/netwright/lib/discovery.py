"""discovery.py — 内网资产盘点：LLDP/CDP/ARP 采集 → 关联分析（纯逻辑 + 线程池）。

流程（BFS，按跳数）：
  种子设备 SSH/Telnet 采集 LLDP/CDP 邻居 + ARP 表
    → 邻居设备入图；ARP 中的内网 IP 入资产池
    → （depth≥2）新发现的邻居用同厂商凭据递归登录
    → 并发探测管理协议端口（22/23/830）
    → 与设备清单关联：已知 / 新增 / 厂商分布
"""
from __future__ import annotations

import concurrent.futures as futures
import ipaddress
import re
import socket
from dataclasses import dataclass, field

from .controller.topology import DISCOVERY_COMMANDS, Topology, build_topology, parse_neighbors

ARP_COMMANDS = {
    "huawei": "display arp all",
    "h3c": "display arp all",
    "cisco": "show ip arp",
    "ruijie": "show ip arp",
    "mikrotik": "/ip arp print",
    "sonic": "show arp",
    "linux": "ip neigh",
    "vyos": "show arp",
}

PROBE_PORTS = {22: "SSH", 23: "Telnet", 830: "NETCONF"}

_IP_RE = re.compile(r"\b(\d{1,3}(?:\.\d{1,3}){3})\b")
_MAC_PATTERNS = (
    re.compile(r"\b([0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4})\b", re.I),
    re.compile(r"\b([0-9a-f]{2}(?::[0-9a-f]{2}){5})\b", re.I),
    re.compile(r"\b([0-9a-f]{4}\.[0-9a-f]{4}\.[0-9a-f]{4})\b", re.I),
)


@dataclass
class Asset:
    key: str                       # IP（有则用 IP，否则 lldp:主机名）
    ip: str = ""
    hostname: str = ""
    vendor_guess: str = ""
    protocols: list = field(default_factory=list)
    source: set = field(default_factory=set)   # lldp / arp / probe / inventory
    known: bool = False
    links: int = 0

    def merge(self, other: "Asset") -> None:
        self.ip = self.ip or other.ip
        self.hostname = self.hostname or other.hostname
        self.vendor_guess = self.vendor_guess or other.vendor_guess
        self.protocols = sorted(set(self.protocols) | set(other.protocols))
        self.source |= other.source
        self.known = self.known or other.known
        self.links += other.links


def _is_private(ip: str) -> bool:
    try:
        return ipaddress.IPv4Address(ip).is_private
    except ValueError:
        return False


def parse_arp(text: str) -> list[tuple[str, str]]:
    """从任意厂商 ARP 输出提取 (IP, MAC)，容忍表格布局。

    解析策略（容错优先）：
      * 每行找第一个 IPv4 地址（私网才收录，公网直接忽略）；
      * MAC 依次尝试 华为横线 / 冒号 / 思科点分 三种格式；
      * 同 IP 去重（保留首次出现的 MAC）。

    :param text: ARP 命令的原始输出（可为多厂商混合）
    :return: [(ip, mac)] 去重列表
    """
    out: list[tuple[str, str]] = []
    seen: set[str] = set()
    for line in text.splitlines():
        ip_m = _IP_RE.search(line)
        if not ip_m:
            continue
        ip = ip_m.group(1)
        if not _is_private(ip):
            continue
        mac = next((p.search(line).group(1) for p in _MAC_PATTERNS if p.search(line)), "")
        if ip not in seen:
            seen.add(ip)
            out.append((ip, mac))
    return out


def guess_vendor_from_text(text: str) -> str:
    """从系统名/平台描述推测厂商。

    关键字规则按"具体在前"排序（如 MikroTik 的 hAP/RB 前缀比通用词更可信）。
    :param text: LLDP System Name / 平台描述 / 主机名等任意文本
    :return: 厂商 key（huawei/h3c/cisco/...），无法识别返回 ""
    """
    low = (text or "").lower()
    rules = (
        ("huawei", ("huawei", "ce58", "s5735", "s5720", "s6730", "vrp")),
        ("h3c", ("h3c", "comware", "wx25", "wx30", "wx4", "s5130", "s5560")),
        ("cisco", ("cisco", "catalyst", "nexus", "ios-xe", "air-")),
        ("ruijie", ("ruijie", "rg-s", "nbs")),
        ("mikrotik", ("mikrotik", "routeros", "rb4011", "hap ", "hap/")),
        ("vyos", ("vyos",)),
        ("sonic", ("sonic",)),
        ("linux", ("linux", "ubuntu", "centos", "debian")),
    )
    for vendor, kws in rules:
        if any(kw in low for kw in kws):
            return vendor
    return ""


def probe_protocols(ip: str, timeout: float = 1.0) -> list[str]:
    """探测管理协议端口（22=SSH / 23=Telnet / 830=NETCONF）。

    :param ip: 目标 IPv4
    :param timeout: 单端口 connect 超时秒数
    :return: 开放的协议名列表，如 ["SSH", "NETCONF"]
    """
    open_names = []
    for port, name in PROBE_PORTS.items():
        try:
            with socket.create_connection((ip, port), timeout=timeout):
                open_names.append(name)
        except OSError:
            continue
    return open_names


def correlate(assets: dict[str, Asset], inventory, topo: Topology | None) -> dict:
    """关联分析：资产与设备清单比对，判定 已知/新增。

    匹配规则：资产 IP 在清单 host 中，或资产主机名在清单 hostname 中 → 已知。
    :return: {"known", "new", "links", "by_vendor", "link_list"}
    """
    inv_hosts = {d.host for d in inventory.devices}
    inv_names = {d.hostname for d in inventory.devices if d.hostname}
    known = new = 0
    for a in assets.values():
        a.known = (a.ip and a.ip in inv_hosts) or (a.hostname and a.hostname in inv_names)
        if a.known:
            known += 1
        else:
            new += 1
    by_vendor: dict[str, int] = {}
    for a in assets.values():
        key = a.vendor_guess or "unknown"
        by_vendor[key] = by_vendor.get(key, 0) + 1
    links = topo.undirected_edges() if topo else []
    return {"known": known, "new": new, "links": len(links),
            "by_vendor": by_vendor, "link_list": links}


def discover_from_seeds(devices: list, inventory, depth: int = 1,
                        timeout: float = 15.0, probe: bool = True,
                        workers: int = 20, progress=None) -> dict:
    """一键内网资产盘点（阻塞；调用方放线程）。

    :param devices: 种子设备（inventory.Device）
    :param inventory: 清单（用于已知/新增判定；凭据沿用种子设备）
    :param depth: 递归跳数（1 = 只查种子的一跳邻居）
    :return: {"assets": {key: Asset}, "topology": Topology, "summary": {...},
              "visited": [...], "errors": [...]}
    """
    from . import ssh_client
    from .inventory import Device

    assets: dict[str, Asset] = {}
    topo: Topology | None = None
    visited: list[str] = []
    errors: list[str] = []
    seen_hosts: set[str] = {d.host for d in devices}

    queue: list[Device] = list(devices)
    for level in range(max(1, depth + 1)):
        if not queue:
            break
        next_queue: list[Device] = []
        level_outputs: list[tuple[str, str, str]] = []

        def collect(dev: Device) -> tuple[str, str, str] | None:
            cmds = list(DISCOVERY_COMMANDS.get(dev.vendor, []))
            arp_cmd = ARP_COMMANDS.get(dev.vendor)
            if arp_cmd:
                cmds = cmds + [arp_cmd]
            if not cmds:
                return None
            try:
                outs = ssh_client.run_commands(dev, cmds, timeout=timeout)
                return (dev.display_name, dev.vendor,
                        "\n".join(o for _t, _c, o, _e in outs))
            except Exception as e:
                errors.append(f"{dev.display_name}: {e}")
                return None

        with futures.ThreadPoolExecutor(max_workers=max(1, min(workers, 50))) as ex:
            for result in ex.map(collect, queue):
                if result:
                    level_outputs.append(result)
                    visited.append(result[0])
                done = len(visited)
                if progress:
                    progress(done, done + len(queue) - 1)

        topo = build_topology(level_outputs) if topo is None else _merge_topo(
            topo, build_topology(level_outputs))

        for device_name, vendor, text in level_outputs:
            for ip, _mac in parse_arp(text):
                if not _is_private(ip):
                    continue
                a = assets.setdefault(ip, Asset(key=ip, ip=ip))
                a.merge(Asset(key=ip, ip=ip, source={"arp"}))
            for lk in parse_neighbors(vendor, text, device=device_name):
                peer = lk.peer_device
                a = assets.setdefault(f"lldp:{peer}",
                                      Asset(key=f"lldp:{peer}", hostname=peer))
                a.merge(Asset(key=f"lldp:{peer}", hostname=peer, source={"lldp"}, links=1))
                a.vendor_guess = a.vendor_guess or guess_vendor_from_text(peer)
                # 递归：新邻居 + 种子同款凭据（常见于统一管理的内网）
                if level < depth and peer and peer not in seen_hosts:
                    seed = next((d for d in devices if d.display_name == device_name), None)
                    if seed:
                        next_queue.append(Device(
                            host=peer, vendor=a.vendor_guess or seed.vendor,
                            username=seed.username, password=seed.password,
                            protocol=seed.protocol))
                        seen_hosts.add(peer)

        queue = next_queue

    if probe:
        ips = [a.ip for a in assets.values() if a.ip and _is_private(a.ip)]
        with futures.ThreadPoolExecutor(max_workers=60) as ex:
            fut_map = {ex.submit(probe_protocols, ip): ip for ip in ips}
            for fut in futures.as_completed(fut_map):
                ip = fut_map[fut]
                protocols = fut.result()
                if protocols:
                    assets[ip].protocols = protocols
                    assets[ip].source.add("probe")

    summary = correlate(assets, inventory, topo)
    return {"assets": assets, "topology": topo, "summary": summary,
            "visited": visited, "errors": errors}


def _merge_topo(a: Topology, b: Topology) -> Topology:
    from .controller.topology import Topology as T
    return T(nodes=a.nodes | b.nodes, links=a.links + b.links)
