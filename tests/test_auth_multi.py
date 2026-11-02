"""R6 多 token 与审计契约测试：只读 scope / 轮换 / 吊销 / 来源审计。"""

from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)


from netwright.lib.controller import deploy as deploy_mod
from netwright.lib.inventory import Device, Inventory
from netwright.sdn import ControllerStore, nbapi
from netwright.sdn.auth import TokenAuth


def _store(tmp_path, auth: TokenAuth | None = None) -> ControllerStore:
    inv = Inventory(str(tmp_path / "dev.json"))
    inv.add(Device(host="192.0.2.1", vendor="huawei", hostname="A"))
    return ControllerStore(inv, auth=auth or TokenAuth("primary-secret"))


def _dispatch(store, method, path, body=None, token="", client="203.0.113.9"):
    return nbapi.dispatch(store, method, path, body,
                          headers={"Authorization": f"Bearer {token}"}, client=client)


def test_readonly_token_can_get_but_not_post(tmp_path):
    """只读 token：GET 放行；POST /api/v2/intents/deploy → 403。"""
    auth = TokenAuth("primary-secret")
    readonly = auth.issue("read", "ci-script")
    store = _store(tmp_path, auth)

    status, body = _dispatch(store, "GET", "/api/v2/snapshot", token=readonly)
    assert status == 200 and body["ok"] is True

    status, body = _dispatch(store, "POST", "/api/v2/intents/deploy",
                             {"run_ids": ["pol-0001"]}, token=readonly)
    assert status == 403, body
    assert "只读" in body["message"]
    assert status != 401, "scope 不足不是身份问题"


def test_invalid_token_is_401_not_403(tmp_path):
    store = _store(tmp_path)
    status, body = _dispatch(store, "GET", "/api/v2/snapshot", token="wrong-token")
    assert status == 401 and "hint" in body
    status, _ = _dispatch(store, "GET", "/api/v2/snapshot", token="")
    assert status == 401


def test_primary_token_rotation_invalidates_old(tmp_path):
    """轮换后旧 token 立即 401，新 token 可用；子 token 不受影响。"""
    auth = TokenAuth("old-primary")
    sub = auth.issue("read", "reporter")
    store = _store(tmp_path, auth)

    new_token = auth.rotate()
    status, _ = _dispatch(store, "GET", "/api/v2/snapshot", token="old-primary")
    assert status == 401, "轮换后旧主 token 必须 401"
    status, _ = _dispatch(store, "GET", "/api/v2/snapshot", token=new_token)
    assert status == 200
    status, _ = _dispatch(store, "GET", "/api/v2/snapshot", token=sub)
    assert status == 200, "子 token 不随主 token 轮换失效"


def test_revoke_subtoken(tmp_path):
    auth = TokenAuth("primary-secret")
    sub = auth.issue("write", "automation")
    store = _store(tmp_path, auth)

    status, _ = _dispatch(store, "POST", "/api/v2/topology/sync", token=sub)
    assert status == 200, "write scope 子 token 可以 POST"
    assert auth.revoke(sub) is True
    assert auth.revoke(sub) is False            # 重复吊销
    assert auth.revoke(auth.token) is False     # 主 token 不能单独吊销
    status, _ = _dispatch(store, "GET", "/api/v2/snapshot", token=sub)
    assert status == 401, "吊销后的子 token 必须 401"


def test_every_request_audited_with_ip_and_label(tmp_path):
    """审计里能看到每次调用的来源：IP + token label；被拒的调用也留痕。"""
    auth = TokenAuth("primary-secret")
    readonly = auth.issue("read", "ci-script")
    store = _store(tmp_path, auth)
    before = len(deploy_mod.audit_tail(500))

    _dispatch(store, "GET", "/api/v2/snapshot", token=readonly, client="10.1.1.7")
    _dispatch(store, "POST", "/api/v2/intents/deploy", {"run_ids": []},
              token=readonly, client="10.1.1.7")
    _dispatch(store, "GET", "/api/v2/snapshot", token="bad-token", client="10.1.1.8")

    entries = deploy_mod.audit_tail(500)[before:]
    api_entries = [e for e in entries if e.get("action", "").startswith("api.")]
    labels = {(e["action"], e.get("token"), e.get("ip")) for e in api_entries}
    assert ("api.request", "ci-script", "10.1.1.7") in labels, \
        f"成功调用应带 token label 与 IP：{labels}"
    assert ("api.auth_denied", "ci-script", "10.1.1.7") in labels, \
        "只读 token 的写尝试应记 DENIED 且可追溯到 label"
    assert ("api.auth_denied", "-", "10.1.1.8") in labels, \
        "无效 token 的访问也应留痕"


def test_settings_roundtrip_keeps_subtokens(tmp_path):
    """from_settings 恢复子 token；export 不含主 token（主 token 走专用键）。"""
    auth = TokenAuth("primary-secret")
    readonly = auth.issue("read", "ci-script")
    write = auth.issue("write", "automation")
    settings = {"api_token": auth.token, "api_tokens": auth.export()}

    restored = TokenAuth.from_settings(settings)
    assert restored.token == "primary-secret"
    assert restored.tokens[readonly]["scope"] == "read"
    assert restored.tokens[write]["scope"] == "write"
    assert restored.tokens["primary-secret"]["scope"] == "write"
    assert "primary-secret" not in settings["api_tokens"], \
        "export 不含主 token（避免两处存储不一致）"


def test_legacy_single_token_api_still_works(tmp_path):
    """兼容：TokenAuth("secret") + check() 的旧用法不回归。"""
    auth = TokenAuth("secret")
    assert auth.check("/api/v2/snapshot", "Bearer secret") is True
    assert auth.check("/api/v2/snapshot", "Bearer nope") is False
    assert auth.check("/api/v2/health", "") is True, "健康检查保持公开"


def test_public_health_open_to_all(tmp_path):
    store = _store(tmp_path)
    status, body = _dispatch(store, "GET", "/api/v2/health", token="")
    assert status == 200 and body["ok"] is True
