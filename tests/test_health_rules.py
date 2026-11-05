"""健康采样（SNMP）与可配置合规规则。"""
from __future__ import annotations

import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from netwright.lib import health
from netwright.lib.compliance import load_rules, scan


class _Device:
    host = "192.0.2.1"
    display_name = "核心A"


def _fake_getter(values: dict[str, object]):
    def getter(host, community, oid, timeout=2.0):
        if oid in values:
            value = values[oid]
            if isinstance(value, Exception):
                raise value
            return oid, value
        raise TimeoutError("no answer")
    return getter


def test_collect_computes_cpu_mem_uptime():
    getter = _fake_getter({
        health.OID_CPU_1MIN: 37,
        health.OID_MEM_TOTAL: 1000,
        health.OID_MEM_AVAIL: 250,
        health.OID_SYS_UPTIME: 360000,
    })
    result = health.collect(_Device(), "public", getter=getter)
    assert result["ok"]
    assert result["cpu_util"] == 37
    assert result["mem_util"] == 75.0
    assert result["uptime_hours"] == 1.0
    assert result["errors"] == {}


def test_collect_keeps_partial_results_and_errors():
    getter = _fake_getter({health.OID_CPU_1MIN: 12,
                           health.OID_MEM_TOTAL: TimeoutError("timeout")})
    result = health.collect(_Device(), "public", getter=getter)
    assert result["cpu_util"] == 12
    assert "mem_total_kb" in result["errors"]
    assert "mem_util" not in result


def test_collect_all_failing_is_not_ok():
    result = health.collect(_Device(), "public", getter=_fake_getter({}))
    assert result["ok"] is False
    assert len(result["errors"]) == len(health.DEFAULT_OIDS)


def test_load_rules_from_custom_file(tmp_path):
    path = tmp_path / "compliance.json"
    path.write_text(json.dumps({"rules": [
        {"id": "custom.telnet", "title": "禁 Telnet", "severity": "high",
         "pattern": r"telnet\s+server\s+enable", "hint": "关掉它"},
        {"id": "custom.ntp", "title": "要 NTP", "severity": "low",
         "pattern": r"ntp\s+server", "missing": True},
    ]}), encoding="utf-8")
    rules = load_rules(str(path))
    assert len(rules) == 2
    findings = scan("telnet server enable\n", rules=rules)
    assert {f.rule_id for f in findings} == {"custom.telnet", "custom.ntp"}


def test_missing_rule_file_falls_back_to_builtin(tmp_path):
    rules = load_rules(str(tmp_path / "nope.json"))
    assert len(rules) >= 8
