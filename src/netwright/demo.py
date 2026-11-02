"""demo.py — 一键演示数据（小白第一次打开就能看到"有东西"的界面）。

设计原则：
  * **不覆盖用户数据**：只追加清单里不存在的设备/链路；
  * 用文档网段 192.0.2.0/24（RFC 5737），绝不指向真实可路由地址；
  * 演示设备带主机名，拓扑立刻有形状；其中一台故意配成 telnet，用来验证协议列。
"""
from __future__ import annotations

from .lib.inventory import Device, LedgerLink

DEMO_NOTE = "演示数据（可随时删除）"

DEMO_DEVICES = [
    Device(host="192.0.2.11", vendor="huawei", hostname="Core-SW-01",
           username="demo", password="Demo@123", note=DEMO_NOTE),
    Device(host="192.0.2.12", vendor="huawei", hostname="Core-SW-02",
           username="demo", password="Demo@123", note=DEMO_NOTE),
    Device(host="192.0.2.21", vendor="h3c", hostname="Agg-SW-01",
           username="demo", password="Demo@123", note=DEMO_NOTE),
    Device(host="192.0.2.22", vendor="cisco", hostname="Agg-SW-02",
           username="demo", password="Demo@123", note=DEMO_NOTE),
    Device(host="192.0.2.31", vendor="ruijie", hostname="Acc-SW-01",
           username="demo", password="Demo@123", note=DEMO_NOTE),
    Device(host="192.0.2.32", vendor="huawei", hostname="Acc-SW-02",
           username="demo", password="Demo@123", protocol="telnet", note=DEMO_NOTE),
    Device(host="192.0.2.41", vendor="linux", hostname="Monitor-01",
           username="demo", password="Demo@123", note=DEMO_NOTE),
]

DEMO_LINKS = [
    LedgerLink("Core-SW-01", "GE0/0/1", "Core-SW-02", "GE0/0/1"),
    LedgerLink("Core-SW-01", "GE0/0/23", "Agg-SW-01", "GE1/0/48"),
    LedgerLink("Core-SW-02", "GE0/0/23", "Agg-SW-02", "Gi1/0/48"),
    LedgerLink("Agg-SW-01", "GE1/0/1", "Acc-SW-01", "Gi0/24"),
    LedgerLink("Agg-SW-02", "Gi1/0/1", "Acc-SW-02", "GE0/0/24"),
    LedgerLink("Agg-SW-01", "GE1/0/2", "Monitor-01", "eth0"),
]


def is_demo_loaded(inventory) -> bool:
    return any(getattr(d, "note", "") == DEMO_NOTE for d in inventory.devices)


def seed(inventory, with_links: bool = True) -> tuple[int, int]:
    """把演示设备/链路追加进清单并落盘；返回 (新增设备数, 新增链路数)。"""
    added_devices = 0
    for device in DEMO_DEVICES:
        if inventory.find(device.host, device.port):
            continue
        inventory.devices.append(Device(**vars(device)))
        added_devices += 1

    added_links = 0
    if with_links:
        existing = {(lk.device_host, lk.local_intf, lk.peer_host, lk.peer_intf)
                    for lk in inventory.links}
        for link in DEMO_LINKS:
            key = (link.device_host, link.local_intf, link.peer_host, link.peer_intf)
            if key in existing:
                continue
            inventory.links.append(LedgerLink(**vars(link)))
            added_links += 1

    if added_devices or added_links:
        inventory.save()
    return added_devices, added_links


def clear(inventory) -> int:
    """删除所有演示设备与演示链路（按备注/端点识别），返回删除的台数。"""
    names = {d.hostname or d.host for d in inventory.devices if d.note == DEMO_NOTE}
    names |= {d.host for d in inventory.devices if d.note == DEMO_NOTE}
    before = len(inventory.devices)
    inventory.devices = [d for d in inventory.devices if d.note != DEMO_NOTE]
    demo_peers = {lk.peer_host for lk in DEMO_LINKS} | {lk.device_host for lk in DEMO_LINKS}
    kept_links = [lk for lk in inventory.links
                  if not (lk.device_host in names or lk.peer_host in demo_peers)]
    links_changed = len(kept_links) != len(inventory.links)
    inventory.links = kept_links
    if before != len(inventory.devices) or links_changed:
        inventory.save()
    return before - len(inventory.devices)
