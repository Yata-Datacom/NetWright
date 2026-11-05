"""环境自检（selfcheck）测试。"""
from __future__ import annotations

import os
import socket
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from netwright.lib.selfcheck import port_free, run_checks, summarize


def test_checks_all_have_shape():
    checks = run_checks({"rest_port": 8899})
    assert checks
    for check in checks:
        assert set(check) == {"name", "ok", "detail", "hint"}
        assert isinstance(check["ok"], bool)


def test_environment_is_healthy_in_source_tree():
    ok, line = summarize(run_checks())
    assert ok, line


def test_port_free_detects_occupied_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        sock.listen(1)
        port = sock.getsockname()[1]
        assert port_free(port) is False


def test_templates_check_reports_count():
    checks = {c["name"]: c for c in run_checks()}
    assert checks["模板库"]["ok"] is True
    assert "个模板" in checks["模板库"]["detail"]
