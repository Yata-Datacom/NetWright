"""R14 模板引擎契约测试：{{#if}} / {{#each}} / 行号报错 / 旧模板零回归。"""

from __future__ import annotations

import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)


from netwright.lib import generator as gen


# ── {{#if}} ─────────────────────────────────────────────────────────
def test_if_true_branch_renders():
    text = "vlan 10\n{{#if dhcp}}dhcp relay {{dhcp_server}}\n{{/if}}vlan 20\n"
    out = gen.render_template(text, {"dhcp": "yes", "dhcp_server": "10.0.0.1"})
    assert out == "vlan 10\ndhcp relay 10.0.0.1\nvlan 20\n"


def test_if_false_branch_skipped_without_missing_errors():
    """假分支整段不输出，分支里的变量也不参与缺失检查。"""
    text = "a\n{{#if dhcp}}ip helper {{dhcp_server}}\n{{/if}}b\n"
    out = gen.render_template(text, {"dhcp": ""})          # dhcp_server 未提供
    assert out == "a\nb\n"
    out = gen.render_template(text, {})                    # 条件缺省 = 假
    assert out == "a\nb\n"


def test_if_falsy_values():
    text = "x{{#if flag}}Y{{/if}}z\n"
    for falsy in ("0", "false", "False", "", "none", "no"):
        assert gen.render_template(text, {"flag": falsy}) == "xz\n", falsy
    assert gen.render_template(text, {"flag": "1"}) == "xYz\n"
    assert gen.render_template(text, {"flag": "true"}) == "xYz\n"


def test_if_missing_condition_is_falsy_not_error():
    """条件变量缺失 = 假（开关可选），与普通变量缺失报错相区分。"""
    assert gen.render_template("a{{#if flag}}Y{{/if}}b", {}) == "ab"
    with pytest.raises(ValueError) as exc:
        gen.render_template("a{{#if flag}}{{need}} {{/if}}b", {"flag": "1"})
    assert "缺少变量" in str(exc.value) and "need" in str(exc.value)


# ── {{#each}} ───────────────────────────────────────────────────────
def test_each_renders_per_item():
    text = "{{#each vlan_list}}switchport trunk allowed vlan add {{item}}\n{{/each}}"
    out = gen.render_template(text, {"vlan_list": "10,20,30"})
    assert out == ("switchport trunk allowed vlan add 10\n"
                   "switchport trunk allowed vlan add 20\n"
                   "switchport trunk allowed vlan add 30\n")


def test_each_empty_list_renders_nothing():
    text = "head\n{{#each vlan_list}}vlan {{item}}\n{{/each}}tail\n"
    assert gen.render_template(text, {"vlan_list": ""}) == "head\ntail\n"
    assert gen.render_template(text, {}) == "head\ntail\n"
    assert gen.render_template(text, {"vlan_list": "， "}) == "head\ntail\n"


def test_each_mixes_item_with_outer_variables():
    """块内 {{item}} 与外部变量并存（嵌套变量）。"""
    text = ("{{#each vlan_list}}vlan {{item}}\n"
            " description {{vlan_desc}}-{{item}}\n{{/each}}")
    out = gen.render_template(text, {"vlan_list": "10,20", "vlan_desc": "Users"})
    assert out == ("vlan 10\n description Users-10\n"
                   "vlan 20\n description Users-20\n")


def test_each_accepts_python_list_value():
    text = "{{#each ports}}interface {{item}}\n{{/each}}"
    assert gen.render_template(text, {"ports": ["GE0/0/1", "GE0/0/2"]}) == \
        "interface GE0/0/1\ninterface GE0/0/2\n"


def test_nested_blocks_if_inside_each():
    text = ("{{#each vlan_list}}vlan {{item}}\n"
            "{{#if voice}} voice-vlan {{item}}0\n{{/if}}{{/each}}")
    out = gen.render_template(text, {"vlan_list": "10,20", "voice": "yes"})
    assert out == "vlan 10\n voice-vlan 100\nvlan 20\n voice-vlan 200\n"


# ── 报错与行号 ───────────────────────────────────────────────────────
def test_unclosed_block_error_has_line_number():
    text = "line1\nline2\nline3\n{{#if flag}}body\n"
    with pytest.raises(ValueError) as exc:
        gen.render_template(text, {"flag": "1"})
    assert "第 4 行：{{#if}} 缺少 {{/if}}" in str(exc.value)


def test_unclosed_each_error_has_line_number():
    text = "{{#each vlans}}\n\n\n{{item}}\n"
    with pytest.raises(ValueError) as exc:
        gen.render_template(text, {"vlans": "1"})
    assert "第 1 行：{{#each}} 缺少 {{/each}}" in str(exc.value)


def test_stray_close_error_has_line_number():
    with pytest.raises(ValueError) as exc:
        gen.render_template("ok\n{{/if}}\n", {})
    assert "第 2 行" in str(exc.value) and "{{/if}}" in str(exc.value)


def test_mismatched_close_error():
    text = "{{#if flag}}\n{{/each}}\n"
    with pytest.raises(ValueError) as exc:
        gen.render_template(text, {"flag": "1"})
    assert "{{/each}} 与第 1 行的 {{#if}} 不匹配" in str(exc.value)


def test_legacy_placeholder_errors_unchanged():
    """旧语义不回归：缺变量报错、非法占位符残留报错。"""
    with pytest.raises(ValueError) as exc:
        gen.render_template("ip {{mgmt_ip}}\n", {"hostname": "A"})
    assert "缺少变量" in str(exc.value) and "mgmt_ip" in str(exc.value)
    with pytest.raises(ValueError) as exc:
        gen.render_template("{{9bad}}", {})
    assert "无法识别的占位符" in str(exc.value)


# ── template_variables 的块语义 ─────────────────────────────────────
def test_template_variables_understands_blocks():
    text = ("sysname {{hostname}}\n"
            "{{#if dhcp}}helper {{dhcp_server}}\n{{/if}}"
            "{{#each vlan_list}}vlan {{item}}\n{{/each}}")
    assert gen.template_variables(text) == ["hostname", "dhcp_server", "vlan_list"]


# ── 存量模板零回归 ───────────────────────────────────────────────────
def test_every_builtin_template_renders_clean_with_engine_upgrade():
    """AST 引擎上线后，116 个存量模板必须全部仍能渲染且零残留。"""
    tpls = gen.list_builtin_templates()
    assert len(tpls) >= 116, f"存量模板数量异常：{len(tpls)}"
    for t in tpls:
        variables = {v: "1" for v in t["vars"]}
        variables.update({"hostname": "SW-1", "mgmt_vlan": "11",
                          "mgmt_ip": "192.0.2.1", "mask": "255.255.255.0",
                          "gateway": "192.0.2.254", "access_vlan": "10",
                          "vlan_batch": "10 20"})
        cfg = gen.render_template(t["text"], variables)
        assert "{{" not in cfg, f"{t['file']} 渲染后残留占位符"


def test_realistic_dhcp_relay_template():
    """端到端场景：有 vlan 200 才生成 DHCP 中继（R14 的动机用例）。"""
    text = ("vlan batch {{vlan_batch}}\n"
            "{{#if dhcp_relay}}interface Vlanif200\n"
            " dhcp relay server-ip {{dhcp_server}}\n{{/if}}")
    assert gen.render_template(text, {"vlan_batch": "10 200"}) == "vlan batch 10 200\n"
    out = gen.render_template(text, {"vlan_batch": "10 200", "dhcp_relay": "yes",
                                     "dhcp_server": "10.0.0.1"})
    assert "dhcp relay server-ip 10.0.0.1" in out
