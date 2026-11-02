"""R15 从现网反生成基线：脱敏正确性（IP/密码/团体名绝不进模板）+ 零残留渲染。"""

from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)


from netwright.lib import generator
from netwright.lib.reverse_template import find_leaks, reverse_template

SAMPLE = """#
sysname CORE-SW-01
#
interface Vlanif11
 ip address 10.20.30.40 255.255.255.0
#
snmp-agent community read MyPub123
snmp-agent community write MyPriv456
#
user-interface vty 0 4
 set authentication password cipher %^%#SECRET123%^%#
#
ip route-static 0.0.0.0 0.0.0.0 10.20.30.1
"""


def test_original_ips_never_appear_in_template():
    tpl = reverse_template(SAMPLE, "huawei")
    for ip in ("10.20.30.40", "10.20.30.1"):
        assert ip not in tpl["text"], f"IP {ip} 泄漏进模板"
    # 网掩码与 0.0.0.0 是配置结构不是凭据，保留原样（可读性）
    assert "255.255.255.0" in tpl["text"] and "0.0.0.0" in tpl["text"]
    assert "{{ip_1}}" in tpl["text"] and "{{ip_2}}" in tpl["text"]
    assert tpl["sanitized"]["ips"] == 2


def test_password_and_community_never_appear_in_template():
    tpl = reverse_template(SAMPLE, "huawei")
    for secret in ("MyPub123", "MyPriv456", "SECRET123"):
        assert secret not in tpl["text"], f"凭据 {secret} 泄漏进模板"
    assert tpl["sanitized"]["communities"] == 2
    assert tpl["sanitized"]["passwords"] == 1
    community_vars = [v for v in tpl["vars"] if v.startswith("snmp_community")]
    password_vars = [v for v in tpl["vars"] if v.startswith("password_")]
    assert len(community_vars) == 2 and len(password_vars) == 1


def test_same_ip_shares_one_placeholder():
    config = "ip address 10.1.1.1 255.255.255.0\npeer 10.1.1.1\n"
    tpl = reverse_template(config)
    assert tpl["sanitized"]["ips"] == 1
    assert tpl["text"].count("{{ip_1}}") == 2
    assert "255.255.255.0" in tpl["text"]


def test_find_leaks_detects_and_clears():
    assert find_leaks(SAMPLE, SAMPLE) != [], "原文自身应被判定为泄漏"
    tpl = reverse_template(SAMPLE)
    assert tpl["leaks"] == [], "脱敏产物的 leaks 必须为空"
    assert find_leaks(tpl["text"], SAMPLE) == []


def test_render_roundtrip_zero_leftover():
    """候选模板喂回 render_template 必须零残留（能通过入库前的最后一关）。"""
    tpl = reverse_template(SAMPLE, "huawei")
    values = {v: f"V_{i}" for i, v in enumerate(tpl["vars"])}
    rendered = generator.render_template(tpl["text"], values)
    assert "{{" not in rendered and "}}" not in rendered
    assert "V_" in rendered, "占位值应被渲染进结果"


def test_to_policies_accepts_reversed_template(tmp_path):
    """反生成模板与 R13 闭环兼容：to_policies 能直接编译。"""
    from netwright.lib.inventory import Device, Inventory

    tpl = reverse_template(SAMPLE, "huawei")
    assert tpl["leaks"] == []
    inv = Inventory(str(tmp_path / "dev.json"))
    inv.add(Device(host="192.0.2.1", vendor="huawei", hostname="SW-REV"))
    row = {v: f"V_{v}" for v in tpl["vars"]}
    row["hostname"] = "SW-REV"
    policies = generator.to_policies(
        {"file": "reverse/candidate.cfg", "vendor": "huawei",
         "name": "反生成候选", "text": tpl["text"],
         "vars": tpl["vars"]}, [row], inv)
    assert policies and policies[0].commands
