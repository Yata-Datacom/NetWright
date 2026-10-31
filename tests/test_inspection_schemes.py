# -*- coding: utf-8 -*-
"""高级巡检方案测试：VXLAN+EVPN / MPLS·SR / 堆叠M-LAG / RoCEv2 + 过滤逻辑。"""

from __future__ import annotations

import os
import sys
from unittest.mock import patch

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, 'src')
if SRC not in sys.path:
    sys.path.insert(0, SRC)


from netforge.lib import inspector  # noqa: E402
from netforge.lib.inventory import Device  # noqa: E402

ADVANCED = ("VXLAN+EVPN", "MPLS/SR 骨干", "堆叠与M-LAG", "RoCEv2 无损", "IPv6 与过渡")
KEYWORDS = {
    "VXLAN+EVPN": ("vxlan", "evpn"),
    "MPLS/SR 骨干": ("mpls",),
    "堆叠与M-LAG": ("vpc", "irf", "drni", "vsu", "stack", "css", "dfs-group"),
    "RoCEv2 无损": ("pfc", "wred", "queuing", "priority-flow-control", "dcb"),
    "IPv6 与过渡": ("ipv6", "ospfv3", "dhcpv6", "-6"),
}


@pytest.mark.parametrize("name", ADVANCED)
def test_advanced_scheme_structure(name):
    scheme = inspector.BUILTIN_SCHEMES[name]
    assert scheme["desc"].strip()
    cmds_map = scheme["commands"]
    assert {"huawei", "cisco"} <= set(cmds_map), f"{name} 至少要覆盖华为和思科"
    for vendor, cmds in cmds_map.items():
        assert cmds, f"{name}/{vendor} 命令集为空"
        assert len(cmds) == len(set(cmds)), f"{name}/{vendor} 存在重复命令"
        for c in cmds:
            assert c.strip() and c == c.strip()
            low = c.lower()
            if vendor == "linux":
                continue  # Linux 用 ip/ss/journalctl 等系统命令，风格豁免
            if vendor in ("huawei", "h3c"):
                assert low.startswith("display"), f"{name}/{vendor}: {c}"
            else:
                assert low.startswith("show"), f"{name}/{vendor}: {c}"


@pytest.mark.parametrize("name", ADVANCED)
def test_advanced_scheme_keywords(name):
    """每套方案必须命中本场景的标志性关键字（防串台）。"""
    cmds_map = inspector.BUILTIN_SCHEMES[name]["commands"]
    for vendor, cmds in cmds_map.items():
        blob = " ".join(cmds).lower()
        assert any(kw in blob for kw in KEYWORDS[name]), f"{name}/{vendor} 缺场景关键字"


def test_vxlan_scheme_covers_dc_vendors():
    cmds = inspector.BUILTIN_SCHEMES["VXLAN+EVPN"]["commands"]
    assert {"huawei", "cisco", "h3c"} <= set(cmds)
    assert any("nve" in c.lower() for c in cmds["huawei"])
    assert any("l2vpn evpn" in c.lower() for c in cmds["cisco"])
    assert any("l2vpn evpn" in c.lower() for c in cmds["h3c"])


def test_roce_scheme_targets_lossless():
    cmds = inspector.BUILTIN_SCHEMES["RoCEv2 无损"]["commands"]
    huawei_blob = " ".join(cmds["huawei"]).lower()
    assert "pfc" in huawei_blob                      # PFC 无损队列
    cisco_blob = " ".join(cmds["cisco"]).lower()
    assert "priority-flow-control" in cisco_blob or "queuing" in cisco_blob


def test_scheme_missing_vendor_skipped():
    """方案没有该厂商命令集 → run_batch 自动跳过（mock SSH，不发真实连接）。"""
    fake_scheme = {"huawei": ["display version"]}       # 故意没有 cisco
    hw = Device(host="192.0.2.1", vendor="huawei", username="a", password="b")
    cs = Device(host="192.0.2.2", vendor="cisco", username="a", password="b")

    def fake_run_device(dev, cmds, timeout=15.0, port=None):
        r = inspector.DeviceResult(host=dev.host, vendor=dev.vendor)
        for c in cmds:
            r.commands.append(inspector.CommandResult(c, c, "ok"))
        r.finalize_status()
        return r

    with patch.object(inspector, "run_device", fake_run_device):
        results, skipped = inspector.run_batch([hw, cs], fake_scheme, workers=2)
    assert [r.host for r in results] == ["192.0.2.1"]
    assert skipped and "192.0.2.2" in skipped[0]


def test_run_batch_all_covered_no_skip():
    fake_scheme = {"huawei": ["display version"], "cisco": ["show version"]}

    def fake_run_device(dev, cmds, timeout=15.0, port=None):
        r = inspector.DeviceResult(host=dev.host, vendor=dev.vendor)
        r.commands.append(inspector.CommandResult(cmds[0], cmds[0], "ok"))
        r.finalize_status()
        return r

    devices = [Device(host="192.0.2.1", vendor="huawei"),
               Device(host="192.0.2.2", vendor="cisco")]
    with patch.object(inspector, "run_device", fake_run_device):
        results, skipped = inspector.run_batch(devices, fake_scheme, workers=2)
    assert not skipped and len(results) == 2
