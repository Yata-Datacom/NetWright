"""netcalc.py — IPv4 子网计算（纯函数，无副作用）。

所有输入输出都用字符串/基本类型，方便单测与 UI 复用。
"""
from __future__ import annotations

import ipaddress
from dataclasses import dataclass


@dataclass
class SubnetInfo:
    network: str          # 网络地址
    broadcast: str        # 广播地址
    netmask: str          # 掩码
    wildcard: str         # 反掩码
    prefix: int           # 前缀长度
    first_host: str       # 第一个可用主机
    last_host: str        # 最后一个可用主机
    total_ips: int        # 总地址数（含网络/广播）
    usable_hosts: int     # 可用主机数
    ip_class: str         # A/B/C/D/E
    scope: str            # 私网 / 公网 / 保留 / 环回 / 链路本地
    binary_mask: str      # 二进制掩码（点分）
    network_int: int      # 网络地址整数值（排序/进制换算用）


def _scope_of(ip: ipaddress.IPv4Address) -> str:
    if ip.is_loopback:
        return "环回"
    if ip.is_link_local:
        return "链路本地"
    if ip.is_private:
        return "私网"
    if ip.is_reserved or ip.is_multicast:
        return "保留/组播"
    return "公网"


def _class_of(ip: ipaddress.IPv4Address) -> str:
    first = int(ip) >> 24
    if first < 128:
        return "A"
    if first < 192:
        return "B"
    if first < 224:
        return "C"
    if first < 240:
        return "D（组播）"
    return "E（保留）"


def calc_subnet(cidr: str) -> SubnetInfo:
    """解析 CIDR 或「IP 掩码」，返回子网详情。

    支持：
      * 192.168.1.0/24
      * 192.168.1.130/24        （自动归到所属网络）
      * 192.168.1.130 255.255.255.0（空格/斜杠分隔均可）
    :raises ValueError: 输入无法解析时，message 面向用户。
    """
    text = (cidr or "").strip()
    if not text:
        raise ValueError("请输入 CIDR（如 192.168.1.0/24）")
    try:
        if "/" in text:
            net = ipaddress.ip_network(text, strict=False)
        else:
            parts = text.split()
            if len(parts) == 2 and "." in parts[1]:
                # IP + 点分掩码 → 转前缀（拒绝 255.0.255.0 这类非连续掩码）
                mask_int = int(ipaddress.IPv4Address(parts[1]))
                prefix = bin(mask_int).count("1")
                if ipaddress.IPv4Address(mask_int) != \
                        ipaddress.IPv4Address((0xFFFFFFFF << (32 - prefix)) & 0xFFFFFFFF):
                    raise ValueError(f"掩码不连续: {parts[1]}")
                net = ipaddress.ip_network(f"{parts[0]}/{prefix}", strict=False)
            else:
                net = ipaddress.ip_network(parts[0], strict=False)
    except ValueError as e:
        raise ValueError(f"无法解析地址: {e}") from e

    if not isinstance(net, ipaddress.IPv4Network):
        raise ValueError("当前仅支持 IPv4")

    # 可用主机范围：直接按整数计算，绝不物化地址列表（/8 有 1600 万个地址）
    if net.prefixlen < 31:
        first = ipaddress.IPv4Address(int(net.network_address) + 1)
        last = ipaddress.IPv4Address(int(net.broadcast_address) - 1)
        usable = net.num_addresses - 2
    else:
        first = last = net.network_address
        usable = net.num_addresses
    mask = net.netmask
    wildcard = ipaddress.IPv4Address(int(mask) ^ 0xFFFFFFFF)
    binary = ".".join(f"{int(mask):032b}"[i:i + 8] for i in range(0, 32, 8))

    return SubnetInfo(
        network=str(net.network_address),
        broadcast=str(net.broadcast_address),
        netmask=str(mask),
        wildcard=str(wildcard),
        prefix=net.prefixlen,
        first_host=str(first),
        last_host=str(last),
        total_ips=net.num_addresses,
        usable_hosts=usable,
        ip_class=_class_of(net.network_address),
        scope=_scope_of(net.network_address),
        binary_mask=binary,
        network_int=int(net.network_address),
    )


def split_vlsm(base_cidr: str, host_counts: list[int]) -> list[SubnetInfo]:
    """按主机数需求做 VLSM 划分（从大到小分配）。

    :param base_cidr: 母网，如 192.168.1.0/24
    :param host_counts: 各子网需要的主机数
    :raises ValueError: 空间不足或输入非法。
    :return: 依次分配的子网列表（与 host_counts 排序后一一对应，附原顺序无法保留）。
    """
    if not host_counts:
        raise ValueError("请至少提供一个子网主机数")
    base = ipaddress.ip_network((cidr_normalize(base_cidr)), strict=True)
    need = sorted(((int(c), i) for i, c in enumerate(host_counts)), reverse=True)
    result: list[SubnetInfo | None] = [None] * len(host_counts)
    current = int(base.network_address)
    end = int(base.broadcast_address)
    for hosts, _idx in need:
        if hosts < 1:
            raise ValueError("主机数必须 ≥ 1")
        # 每子网：主机数 + 网络地址 + 广播地址（/31 例外）
        total = hosts + 2 if hosts > 1 else 2
        prefix = 32 - max(2, (total - 1).bit_length())
        if prefix < base.prefixlen:
            raise ValueError(f"子网需求 {hosts} 台主机超出母网 /{base.prefixlen} 的空间")
        size = 2 ** (32 - prefix)
        if current + size - 1 > end:
            raise ValueError("母网空间不足，无法完成 VLSM 划分")
        sub = ipaddress.ip_network((current, prefix), strict=False)
        result[_idx] = calc_subnet(str(sub))
        current += size
    return [r for r in result if r is not None]


def cidr_normalize(text: str) -> str:
    """把「IP 掩码」/ CIDR 统一成 ip_network 可解析的 CIDR 字符串。"""
    info = calc_subnet(text)
    return f"{info.network}/{info.prefix}"
