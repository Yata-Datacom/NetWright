"""配置合规检查（A）：规则命中、扣分、证据行号。"""
from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from netwright.lib.compliance import report, scan, score

BAD = """sysname SW-1
telnet server enable
snmp-server community public ro
enable password Cisco123
ip http server
line vty 0 4
 transport input telnet
"""

GOOD = """sysname SW-2
ntp server 10.0.0.10
logging host 10.0.0.20
banner motd ^C Only authorized access ^C
line vty 0 4
 transport input ssh
 exec-timeout 5 0
"""


def test_bad_config_hits_expected_rules():
    ids = {f.rule_id for f in scan(BAD)}
    assert {"telnet.enabled", "snmp.default-community", "password.plaintext",
            "http.server", "vty.no-timeout", "ntp.missing",
            "logging.missing", "banner.missing"} <= ids


def test_good_config_is_clean_except_nothing():
    assert scan(GOOD) == []
    assert score([]) == 100


def test_finding_has_evidence_line_number():
    finding = next(f for f in scan(BAD) if f.rule_id == "snmp.default-community")
    assert finding.line_no == 3
    assert "public" in finding.evidence


def test_vty_with_timeout_is_not_reported():
    text = "line vty 0 4\n exec-timeout 10 0\n"
    assert "vty.no-timeout" not in {f.rule_id for f in scan(text)}


def test_score_deducts_by_severity_and_floors_at_zero():
    assert score(scan(BAD)) == 0          # 多个 critical，扣到 0
    one_low = scan("line vty 0 4\n")
    assert 0 < score(one_low) < 100


def test_report_shape_and_sorting():
    result = report(BAD, device="SW-1")
    assert result["device"] == "SW-1"
    assert result["total"] >= 6
    assert result["score"] == 0
    severities = [f["severity"] for f in result["findings"]]
    assert severities == sorted(severities, key=lambda s: {"critical": 0, "high": 1,
                                                           "medium": 2, "low": 3}[s])
