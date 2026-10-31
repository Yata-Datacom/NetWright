"""NetForge 纯逻辑模块测试：子网计算 / 端口与目标解析 / 模块发现。"""

from __future__ import annotations

import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from netforge_lib import netcalc, portscan


# ── 子网计算 ────────────────────────────────────────────────────
def test_calc_cidr():
    i = netcalc.calc_subnet("192.168.10.0/24")
    assert (i.network, i.broadcast, i.netmask) == ("192.168.10.0", "192.168.10.255", "255.255.255.0")
    assert i.usable_hosts == 254 and i.prefix == 24
    assert i.first_host == "192.168.10.1" and i.last_host == "192.168.10.254"


def test_calc_ip_with_dotted_mask():
    i = netcalc.calc_subnet("192.168.10.130 255.255.255.0")
    assert i.network == "192.168.10.0"     # 自动归到所属网络
    assert i.wildcard == "0.0.0.255"


def test_calc_slash31_and_32():
    i31 = netcalc.calc_subnet("192.0.2.0/31")
    assert i31.usable_hosts == 2           # /31 点对点
    i32 = netcalc.calc_subnet("192.0.2.5/32")
    assert i32.usable_hosts == 1


def test_calc_scope_and_class():
    assert netcalc.calc_subnet("10.0.0.0/8").scope == "私网"
    assert netcalc.calc_subnet("8.8.8.0/24").scope == "公网"
    assert netcalc.calc_subnet("127.0.0.0/8").scope == "环回"
    assert netcalc.calc_subnet("192.168.1.0/24").ip_class == "C"


def test_calc_rejects_bad_input():
    for bad in ("", "abc", "192.168.1.0/33", "300.1.1.0/24", "2001:db8::/64"):
        with pytest.raises(ValueError):
            netcalc.calc_subnet(bad)


def test_calc_rejects_noncontiguous_mask():
    with pytest.raises(ValueError):
        netcalc.calc_subnet("192.168.1.0 255.0.255.0")


def test_vlsm_split_ordered():
    subs = netcalc.split_vlsm("192.168.1.0/24", [100, 50, 20, 5])
    sizes = [s.prefix for s in subs]
    assert sizes == [25, 26, 27, 29]           # 从大到小
    assert subs[0].network == "192.168.1.0"
    assert subs[1].network == "192.168.1.128"
    assert subs[-1].usable_hosts >= 5


def test_vlsm_insufficient_space():
    with pytest.raises(ValueError):
        netcalc.split_vlsm("192.168.1.0/30", [100])


# ── 端口 / 目标解析 ─────────────────────────────────────────────
def test_parse_ports_mixed():
    assert portscan.parse_ports("22, 80 8000-8003；443") == [22, 80, 443, 8000, 8001, 8002, 8003]


def test_parse_ports_rejects_bad():
    for bad in ("", "0", "70000", "100-50", "abc"):
        with pytest.raises(ValueError):
            portscan.parse_ports(bad)


def test_parse_ports_limit():
    with pytest.raises(ValueError):
        portscan.parse_ports("1-65535")


def test_parse_ip_targets():
    assert portscan.parse_ip_targets("192.0.2.1") == ["192.0.2.1"]
    assert portscan.parse_ip_targets("192.0.2.10-12") == ["192.0.2.10", "192.0.2.11", "192.0.2.12"]
    assert portscan.parse_ip_targets("192.0.2.16-192.0.2.17") == ["192.0.2.16", "192.0.2.17"]
    assert len(portscan.parse_ip_targets("192.0.2.0/30")) == 2   # hosts() 不含网络/广播


def test_parse_ip_targets_rejects():
    for bad in ("999.1.1.1", "192.0.2.5-1", "example.com", "192.0.2.0/33"):
        with pytest.raises(ValueError):
            portscan.parse_ip_targets(bad)


def test_tcp_port_localhost():
    import socket
    import threading
    srv = socket.socket()
    srv.bind(("127.0.0.1", 0))
    srv.listen(1)
    port = srv.getsockname()[1]
    threading.Thread(target=srv.accept, daemon=True).start()
    r = portscan.tcp_port("127.0.0.1", port, timeout=2)
    assert r.state == "open"
    r2 = portscan.tcp_port("127.0.0.1", 1, timeout=0.5)
    assert r2.state in ("closed", "filtered")
    srv.close()
