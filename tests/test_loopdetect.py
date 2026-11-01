# -*- coding: utf-8 -*-
"""环路/漂移检测 + 巡检历史 + 趋势提取测试。"""

from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from netwright.lib import history, loopdetect  # noqa: E402
from netwright.lib.loopdetect import MacRecord  # noqa: E402

HUAWEI_MAC = """
-------------------------------------------------------------------------------
MAC Address    VLAN/VSI/BD   Learned-From        Type       Age
-------------------------------------------------------------------------------
5489-98ab-cd12 10            GE0/0/1             dynamic    -
5489-98ab-cd12 10            GE0/0/2             dynamic    -
5489-1111-2222 20            GE0/0/24            dynamic    -
"""

CISCO_MAC = """
Vlan    Mac Address       Type        Interfaces
----    -----------       --------    ---------
  10    0000.1111.2222    DYNAMIC     Gi0/1
  20    5489.98ab.cd12    DYNAMIC     Gi0/2
"""

MIKROTIK_MAC = """
Flags: L - local
 #    MAC-ADDRESS        VID  ON-INTERFACE    BRIDGE
 0    AA:BB:CC:DD:EE:01  10   ether2          bridge-lan
 1    AA:BB:CC:DD:EE:01  10   ether3          bridge-lan
"""


def test_parse_mac_huawei_multi_port():
    recs = loopdetect.parse_mac_table(HUAWEI_MAC, "SW-1")
    m = {(r.mac, r.intf) for r in recs if r.mac == "5489-98ab-cd12"}
    assert m == {("5489-98ab-cd12", "GE0/0/1"), ("5489-98ab-cd12", "GE0/0/2")}


def test_parse_mac_cisco_and_h3c_style():
    recs = loopdetect.parse_mac_table(CISCO_MAC, "SW-2")
    assert any(r.mac == "0000.1111.2222" and r.intf == "Gi0/1" for r in recs)
    recs2 = loopdetect.parse_mac_table("5489-98ab-cd12 10 GE1/0/1 dynamic", "SW-3")
    assert recs2[0].intf == "GE1/0/1"


def test_parse_mac_mikrotik():
    recs = loopdetect.parse_mac_table(MIKROTIK_MAC, "R1")
    assert {(r.mac, r.intf) for r in recs} == {
        ("aa:bb:cc:dd:ee:01", "ether2"), ("aa:bb:cc:dd:ee:01", "ether3")}


def test_find_loop_same_device_multi_port():
    recs = loopdetect.collect_records([
        ("SW-1", HUAWEI_MAC), ("R1", MIKROTIK_MAC)])
    alerts = loopdetect.find_loops(recs)
    crit = [a for a in alerts if a.severity == "critical"]
    assert any("GE0/0/1" in a.message and "GE0/0/2" in a.message for a in crit)
    assert any("ether2" in a.message and "ether3" in a.message for a in crit)


def test_find_loop_cross_device():
    recs = [MacRecord("aa:bb:cc:dd:ee:ff", "SW-1", "GE0/0/1"),
            MacRecord("aa:bb:cc:dd:ee:ff", "SW-2", "GE0/0/2")]
    alerts = loopdetect.find_loops(recs)
    assert any(a.kind == "cross-device" and a.severity == "warning" for a in alerts)


def test_broadcast_mac_ignored():
    recs = loopdetect.parse_mac_table(
        "ffff.ffff.ffff 10 GE0/0/1 dynamic\n"
        "ffff.ffff.ffff 10 GE0/0/2 dynamic", "SW-1")
    assert recs == []


def test_flap_diff_port_move():
    prev = [MacRecord("aa:bb:cc:dd:ee:ff", "SW-1", "GE0/0/1")]
    curr = [MacRecord("aa:bb:cc:dd:ee:ff", "SW-1", "GE0/0/9")]
    alerts = loopdetect.diff_flapping(prev, curr)
    assert any("GE0/0/1" in a.message and "GE0/0/9" in a.message for a in alerts)


def test_flap_diff_cross_device_move():
    prev = [MacRecord("aa:bb:cc:dd:ee:ff", "SW-1", "GE0/0/1")]
    curr = [MacRecord("aa:bb:cc:dd:ee:ff", "SW-2", "GE0/0/1")]
    alerts = loopdetect.diff_flapping(prev, curr)
    assert any("迁移" in a.message for a in alerts)


def test_loop_devices_set():
    alerts = [loopdetect.LoopAlert("critical", "same-device", "m1", "x",
                                   where=[("A", "p1"), ("A", "p2")])]
    assert loopdetect.loop_devices(alerts) == {"A"}


# ── 巡检历史 / 趋势提取 ────────────────────────────────────────────
def test_history_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr(history, "_base_dir", lambda: str(tmp_path))
    history.append_history("inspection", {"scheme": "标准巡检", "ok": 3,
                                          "warn": 1, "fail": 0, "anomalies": 4,
                                          "avg_ms": 800})
    history.append_history("inspection", {"scheme": "标准巡检", "ok": 4,
                                          "warn": 0, "fail": 1, "anomalies": 2,
                                          "avg_ms": 700})
    entries = history.load_history("inspection")
    assert len(entries) == 2 and entries[-1]["fail"] == 1
    series = history.extract_series(entries, "anomalies")
    assert [v for _l, v in series] == [4.0, 2.0]
    assert all(len(l) == 8 for l, _v in series)   # HH:MM:SS


def test_history_empty(tmp_path, monkeypatch):
    monkeypatch.setattr(history, "_base_dir", lambda: str(tmp_path))
    assert history.load_history("inspection") == []
    assert history.extract_series([], "ok") == []
