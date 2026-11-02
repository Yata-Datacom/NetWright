"""错误翻译测试：技术异常 → 人话，且不丢原始信息。"""

from __future__ import annotations

import os
import socket
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)


from netwright.lib.errors import friendly_error, friendly_text
from netwright.sdn.lifecycle import LifecycleError
from netwright.sdn.southbound import UnsupportedOperation
from netwright.sdn.southbound.restconf import RestconfError


def test_paramiko_auth_error_is_translated():
    import paramiko

    exc = paramiko.ssh_exception.AuthenticationException("Authentication failed.")
    text = friendly_error(exc)
    assert "认证失败" in text and "Authentication failed" in text
    assert "测试连接" in text, "应给出下一步建议"


def test_timeout_and_refused():
    assert "超时" in friendly_error(socket.timeout("timed out"))
    assert "端口拒绝" in friendly_error(ConnectionRefusedError("refused"))


def test_value_error_passes_through():
    assert friendly_error(ValueError("缺少必填参数: VLAN")) == "缺少必填参数: VLAN"


def test_unsupported_operation_points_to_capabilities():
    text = friendly_error(UnsupportedOperation("OpenFlow program_flows 待实装"))
    assert "还没实装" in text and "南向通道" in text


def test_restconf_error_includes_status_and_hint():
    text = friendly_error(RestconfError("boom", status=401))
    assert "401" in text and "凭据" in text


def test_lifecycle_error_mentions_run_state():
    text = friendly_error(LifecycleError("非法迁移 compiled → verified"))
    assert "状态机" in text and "运行档案" in text


def test_unknown_error_keeps_type():
    text = friendly_error(RuntimeError("something odd"))
    assert text.startswith("RuntimeError:") and "something odd" in text


def test_friendly_text_keywords():
    assert "认证失败" in friendly_text("Authentication failed for admin")
    assert "超时" in friendly_text("SSH timed out after 15s")
    assert friendly_text("某个没见过的错误") == "某个没见过的错误"
    assert friendly_text("") == ""


def test_friendly_error_never_raises_on_weird_exceptions():
    class Weird(Exception):
        def __str__(self):
            return ""

    assert friendly_error(Weird()).strip()
