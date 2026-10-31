"""平台核心测试：凭据保护 / 设备清单 / 配置生成 / 巡检逻辑。"""

from __future__ import annotations

import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, 'src')
if SRC not in sys.path:
    sys.path.insert(0, SRC)


from netforge.lib import generator as gen
from netforge.lib import inspector, secrets
from netforge.lib.inventory import Device, Inventory


# ── 凭据保护 ────────────────────────────────────────────────────────
def test_secrets_roundtrip():
    token = secrets.protect("Pass@123")
    assert secrets.protection_kind(token) in ("dpapi", "plain")
    assert secrets.unprotect(token) == "Pass@123"


def test_secrets_empty_and_plain_passthrough():
    assert secrets.protect("") == ""
    assert secrets.unprotect("") == ""
    assert secrets.unprotect("rawtext") == "rawtext"   # 兼容旧明文


# ── 设备清单 ────────────────────────────────────────────────────────
def test_inventory_crud(tmp_path):
    inv = Inventory(str(tmp_path / "dev.json"))
    d = inv.add(Device(host="192.0.2.1", vendor="huawei", username="admin", password="p@ss"))
    assert d.display_name == "192.0.2.1"
    with pytest.raises(ValueError):
        inv.add(Device(host="192.0.2.1"))
    inv.update(0, Device(host="192.0.2.1", hostname="核心A", vendor="huawei"))
    assert inv.devices[0].hostname == "核心A"
    inv.remove(0)
    assert not inv.devices


def test_inventory_persists_encrypted(tmp_path):
    path = str(tmp_path / "dev.json")
    inv = Inventory(path)
    inv.add(Device(host="192.0.2.1", password="Secret!123"))
    raw = open(path, encoding="utf-8").read()
    assert "Secret!123" not in raw, "密码明文落盘！"
    inv2 = Inventory(path)
    assert inv2.devices[0].password == "Secret!123"


def test_inventory_csv_roundtrip(tmp_path):
    inv = Inventory(str(tmp_path / "dev.json"))
    text = ("host,port,vendor,username,password\n"
            "192.0.2.1,22,huawei,admin,P1\n"
            "192.0.2.2,22,cisco,admin,P2\n")
    added, warns = inv.import_csv(text)
    assert added == 2 and not warns
    out = inv.export_csv()
    assert "192.0.2.1" in out and "huawei" in out
    # 重复导入 → 全部跳过
    added2, warns2 = inv.import_csv(text)
    assert added2 == 0 and len(warns2) == 2


# ── 配置生成 ────────────────────────────────────────────────────────
def test_builtin_templates_available():
    tpls = gen.list_builtin_templates()
    assert len(tpls) >= 116, f"模板库应 ≥116 条，实际 {len(tpls)}"
    vendors = {t["vendor"] for t in tpls}
    assert {"huawei", "cisco", "h3c"} <= vendors


def test_advanced_scenarios_present():
    """无 SDN 控制器手工场景：VXLAN+EVPN / MSTP / MPLS / M-LAG / 堆叠 / RoCEv2 / SR。"""
    names = " ".join(t["name"] for t in gen.list_builtin_templates())
    for kw in ("VXLAN", "MSTP", "MPLS", "M-LAG", "堆叠", "RoCEv2", "SR-MPLS",
               "数据中心基线", "SLAAC", "有状态 DHCPv6", "NAT64", "SRv6",
               "MikroTik", "VyOS", "SONiC", "无线 AC", "WLC"):
        assert kw in names, f"缺少场景: {kw}"


def test_every_template_renders_clean():
    """全部模板用占位值渲染，不允许任何残留 {{}}（宁报错不下发坏配置）。"""
    for t in gen.list_builtin_templates():
        variables = {v: "1" for v in t["vars"]}
        variables.update({"hostname": "SW-1", "mgmt_vlan": "11", "mgmt_ip": "192.0.2.1",
                          "mask": "255.255.255.0", "gateway": "192.0.2.254",
                          "access_vlan": "10", "vlan_batch": "10 20"})
        cfg = gen.render_template(t["text"], variables)
        assert "{{" not in cfg, f"{t['file']} 渲染后残留占位符"


def test_render_no_leftovers():
    text = "sysname {{hostname}}\nip {{mgmt_ip}}\n"
    assert "missing" not in gen.render_template(text, {"hostname": "A", "mgmt_ip": "1.1.1.1"}).lower()
    with pytest.raises(ValueError):
        gen.render_template(text, {"hostname": "A"})     # 缺 mgmt_ip
    with pytest.raises(ValueError):
        gen.render_template("{{9bad}}", {})              # 非法占位符名 → 残留检测


def test_generate_and_conflict():
    tpl = "sysname {{hostname}}\n"
    files = gen.generate(tpl, [{"hostname": "A"}, {"hostname": "B"}])
    assert files == [("A.cfg", "sysname A\n"), ("B.cfg", "sysname B\n")]
    with pytest.raises(ValueError):
        gen.generate(tpl, [{"hostname": "A"}, {"hostname": "A"}])
    with pytest.raises(ValueError):
        gen.generate(tpl, [{"hostname": ""}])
    with pytest.raises(ValueError):
        gen.generate(tpl, [])


def test_write_outputs(tmp_path):
    n = gen.write_outputs(str(tmp_path), [("a.cfg", "x\ny"), ("b.cfg", "z")], eol="\r\n")
    assert n == 2
    raw = open(tmp_path / "a.cfg", "rb").read()
    assert raw == b"x\r\ny\r\n"


# ── 巡检逻辑 ────────────────────────────────────────────────────────
def test_schemes_cover_vendors():
    # AC/WLC 类方案的厂商键为 huawei_ac/h3c_ac/cisco_wlc，做别名归一后校验
    aliases = {"huawei_ac": "huawei", "h3c_ac": "h3c", "cisco_wlc": "cisco"}
    for name, scheme in inspector.BUILTIN_SCHEMES.items():
        vendors = {aliases.get(v, v) for v in scheme["commands"]}
        assert {"huawei", "cisco", "h3c"} <= vendors, name
        for vendor, cmds in scheme["commands"].items():
            assert cmds and all(c.strip() for c in cmds)


def test_detect_cpu_anomaly():
    out = "CPU usage: 92%"
    alerts = inspector.detect_anomalies("huawei", "CPU", out)
    assert any(a.title == "CPU 使用率过高" for a in alerts)
    assert not inspector.detect_anomalies("huawei", "CPU", "CPU usage: 20%")


def test_detect_rx_power_anomaly():
    alerts = inspector.detect_anomalies("huawei", "光模块", "rx power -23.5 dBm")
    assert any("光功率" in a.title for a in alerts)


def test_detect_linux_failed_service():
    alerts = inspector.detect_anomalies("linux", "服务", "3 loaded units listed... 2 failed")
    assert any("systemd" in a.title for a in alerts)


def test_device_result_status():
    r = inspector.DeviceResult(host="192.0.2.1", vendor="huawei")
    r.commands.append(inspector.CommandResult("CPU", "display cpu-usage", "CPU usage: 95%",
                                              anomalies=[inspector.Anomaly("warning", "CPU", "95>80")]))
    r.finalize_status()
    assert r.status == "WARNING"
    r.commands[0].anomalies.append(inspector.Anomaly("critical", "电源异常", "Fault"))
    r.finalize_status()
    assert r.status == "FAILED"


def test_html_report_masks_nothing_sensitive_but_escapes():
    r = inspector.DeviceResult(host="192.0.2.1", vendor="huawei", status="OK")
    r.commands.append(inspector.CommandResult("show version", "show version",
                                              "<script>alert(1)</script> ok"))
    r.finalize_status()
    html = inspector.build_html_report([r], "标准巡检")
    assert "<script>alert(1)</script>" not in html     # 输出被转义
    assert "192.0.2.1" in html and "OK" in html
