"""资产盘点 / 台账链路 / Telnet 测试。"""

from __future__ import annotations

import os
import sys
from unittest.mock import patch


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from netwright.lib import discovery  # noqa: E402
from netwright.lib.controller import topology  # noqa: E402
from netwright.lib.inventory import Device, Inventory  # noqa: E402


# ── ARP 解析 ────────────────────────────────────────────────────────
HUAWEI_ARP = """
IP ADDRESS      MAC ADDRESS     EXPIRE(M) TYPE        VLAN   INTERFACE      VPN
192.0.2.10      5489-98ab-cd12            DF-Dynamic  10     Vlanif10
192.0.2.99      5489-9811-2233  15        Dynamic     10     GE0/0/1
"""

CISCO_ARP = """
Protocol  Address          Age (min)  Hardware Addr   Type   Interface
Internet  192.0.2.20             8   0000.1111.2222  ARPA   Vlan10
Internet  192.0.2.99            12   0000.2222.3333  ARPA   GigabitEthernet0/1
"""

LINUX_NEIGH = """
192.0.2.30 dev eth0 lladdr aa:bb:cc:dd:ee:ff REACHABLE
192.0.2.99 dev eth0  FAILED
"""


def test_parse_arp_huawei():
    pairs = discovery.parse_arp(HUAWEI_ARP)
    assert ("192.0.2.10", "5489-98ab-cd12") in pairs
    assert ("192.0.2.99", "5489-9811-2233") in pairs


def test_parse_arp_cisco_dot_mac():
    pairs = discovery.parse_arp(CISCO_ARP)
    assert ("192.0.2.20", "0000.1111.2222") in pairs


def test_parse_arp_linux_and_dedup():
    text = LINUX_NEIGH + "\n" + LINUX_NEIGH
    pairs = discovery.parse_arp(text)
    ips = [ip for ip, _ in pairs]
    assert ips.count("192.0.2.30") == 1       # 去重
    assert ("192.0.2.30", "aa:bb:cc:dd:ee:ff") in pairs


def test_parse_arp_ignores_public_ip():
    text = "8.8.8.9  0000.1111.2222  ARPA  GE0/0/0"
    assert discovery.parse_arp(text) == []


# ── 厂商推测 ────────────────────────────────────────────────────────
def test_guess_vendor():
    assert discovery.guess_vendor_from_text("Huawei S5735-L48") == "huawei"
    assert discovery.guess_vendor_from_text("cisco WS-C2960X") == "cisco"
    assert discovery.guess_vendor_from_text("MikroTik hAP ac2") == "mikrotik"
    assert discovery.guess_vendor_from_text("unknown-box") == ""


# ── 关联分析 ────────────────────────────────────────────────────────
def test_correlate_known_vs_new(tmp_path):
    inv = Inventory(str(tmp_path / "dev.json"))
    inv.add(Device(host="192.0.2.10", vendor="huawei", hostname="SW-2"))
    assets = {
        "192.0.2.10": discovery.Asset(key="192.0.2.10", ip="192.0.2.10",
                                      hostname="SW-2", source={"arp"}),
        "lldp:SW-9": discovery.Asset(key="lldp:SW-9", hostname="SW-9",
                                     source={"lldp"}, links=1),
    }
    summary = discovery.correlate(assets, inv, None)
    assert summary["known"] == 1 and summary["new"] == 1
    assert assets["192.0.2.10"].known and not assets["lldp:SW-9"].known


# ── 盘点流程（mock SSH）────────────────────────────────────────────
def test_discover_from_seeds(tmp_path, monkeypatch):
    inv = Inventory(str(tmp_path / "dev.json"))
    seed = Device(host="192.0.2.1", vendor="huawei", username="admin",
                  password="pw", hostname="SW-1")
    inv.add(seed)

    huawei_out = HUAWEI_BRIEF + "\n" + HUAWEI_ARP
    from netwright.lib import ssh_client

    def fake_run_commands(dev, cmds, timeout=15.0, port=None):
        return [(c, c, huawei_out, "") for c in cmds]

    with patch.object(ssh_client, "run_commands", fake_run_commands):
        result = discovery.discover_from_seeds([seed], inv, depth=1, probe=False)

    assert "SW-1" in result["visited"]
    assert result["topology"] is not None
    ips = {a.ip for a in result["assets"].values() if a.ip}
    assert "192.0.2.99" in ips          # ARP 发现的资产
    assert any(a.hostname == "SW-2" for a in result["assets"].values())
    assert result["summary"]["links"] >= 1


HUAWEI_BRIEF = """
Local Intf    Neighbor Intf     Neighbor Device       Exptime(s)
GE0/0/1       GE0/0/24          SW-2                  105
"""


# ── 台账链路 → 拓扑 ────────────────────────────────────────────────
def test_ledger_links_build_topology(tmp_path):
    inv = Inventory(str(tmp_path / "dev.json"))
    csv_text = ("host,port,vendor,protocol,username,password,hostname,"
                "local_intf,peer_device,peer_intf\n"
                "192.0.2.1,22,huawei,ssh,admin,P1,核心A,GE0/0/24,核心B,GE0/0/24\n"
                "192.0.2.2,22,huawei,telnet,admin,P2,核心B,,,,\n")
    added, warns = inv.import_csv(csv_text)
    assert added == 2 and not warns
    assert inv.devices[0].protocol == "ssh"
    assert inv.devices[1].protocol == "telnet"
    assert len(inv.links) == 1
    lk = inv.links[0]
    assert (lk.device_host, lk.peer_host) == ("192.0.2.1", "核心B")

    # 台账 → 拓扑
    names = {d.host: (d.hostname or d.host) for d in inv.devices}
    topo = topology.Topology()
    for lk in inv.links:
        a = names.get(lk.device_host, lk.device_host)
        b = names.get(lk.peer_host, lk.peer_host)
        topo.nodes.update([a, b])
        topo.links.append(topology.Link(a, lk.local_intf, b, lk.peer_intf))
    edges = topo.undirected_edges()
    assert len(edges) == 1 and edges[0][0] == "核心A" and edges[0][2] == "核心B"


def test_ledger_link_persist(tmp_path):
    inv = Inventory(str(tmp_path / "dev.json"))
    inv.devices.append(Device(host="192.0.2.1", hostname="A"))
    inv.links.append(__import__(
        "netwright.lib.inventory", fromlist=["LedgerLink"]).LedgerLink(
        "192.0.2.1", "GE0/0/24", "B", "GE0/0/24"))
    inv.save()
    inv2 = Inventory(str(tmp_path / "dev.json"))
    assert len(inv2.links) == 1
    assert inv2.links[0].peer_host == "B"


# ── Telnet 客户端 ──────────────────────────────────────────────────
def test_strip_iac():
    from netwright.lib.telnet_client import _strip_iac
    raw = b"login:" + bytes([255, 251, 1]) + b" ok " + bytes([255, 250, 24, 0, 255, 240]) + b"end"
    text = _strip_iac(raw).decode()
    assert "login:" in text and "end" in text
    assert b"\xff\xfb" not in _strip_iac(raw)


class _FakeSock:
    """最小 socket 桩：按预置响应序列回放。"""

    def __init__(self, responses):
        self.responses = list(responses)
        self.sent = []

    def sendall(self, data):
        self.sent.append(data)

    def settimeout(self, t):
        pass

    def recv(self, n):
        if len(self.responses) > 1:
            return self.responses.pop(0)
        time.sleep(0.03)                 # 粘滞最后一个响应（模拟持续提示符）
        return self.responses[0] if self.responses else b""

    def close(self):
        pass


import time  # noqa: E402


def test_telnet_run_commands(monkeypatch):
    from netwright.lib import telnet_client as tc
    from netwright.lib.inventory import Device

    dev = Device(host="192.0.2.1", vendor="huawei", username="admin",
                 password="pw", protocol="telnet")
    # 登录序列：Username → Password → 提示符；命令回显+输出
    responses = [
        b"Username:",
        b"Password:",
        b"<SW-1>",
        b"display version\r\nHuawei Versatile Routing Platform\r\n<SW-1>",
    ]
    sock = _FakeSock(responses)
    monkeypatch.setattr(tc.socket, "create_connection", lambda *a, **k: sock)
    monkeypatch.setattr(tc.time, "sleep", lambda s: None)
    results = tc.telnet_run_commands(dev, ["display version"], timeout=2)
    assert results[0][0] == "display version"
    assert "Versatile Routing Platform" in results[0][2]
    assert results[0][3] == ""
    assert any(b"admin" in s for s in sock.sent)
    assert any(b"display version" in s for s in sock.sent)


def test_protocol_dispatch(monkeypatch):
    """protocol=telnet 的设备自动走 telnet 通道。"""
    from netwright.lib import ssh_client
    from netwright.lib.inventory import Device

    dev = Device(host="192.0.2.1", vendor="huawei", protocol="telnet")
    called = {"telnet": False}

    def fake_telnet(dev_, cmds, timeout=15.0, port=23):
        called["telnet"] = True
        return [(c, c, "ok", "") for c in cmds]

    monkeypatch.setattr(ssh_client, "telnet_run_commands", fake_telnet) \
        if hasattr(ssh_client, "telnet_run_commands") else None
    # run_commands 内部是延迟导入，需要 patch telnet_client 模块
    import netwright.lib.telnet_client as tmod
    monkeypatch.setattr(tmod, "telnet_run_commands", fake_telnet)
    out = ssh_client.run_commands(dev, ["show version"])
    assert called["telnet"] and out[0][2] == "ok"
