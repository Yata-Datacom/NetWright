"""auth.py — 北向 REST 的令牌鉴权（默认全开，除健康检查外都要 token）。

为什么不用用户名密码：控制器是"工具型服务"，调用方是脚本/CI/另一个程序，
一个可轮换的 Bearer token 比账号体系更贴合场景，也更容易在 UI 里展示与复制。

安全边界（明确写出来，避免误判）：
  * 只监听 127.0.0.1，token 是**第二道闸**，不是公网防护；
  * token 存在 `netwright_settings.json`（本地文件），可以一键轮换；
  * 比较用 :func:`hmac.compare_digest`，避免时序侧信道。
"""
from __future__ import annotations

import hmac
import secrets as _secrets

TOKEN_BYTES = 24          # → 48 位十六进制，足够暴力不可猜
SETTINGS_KEY = "api_token"
PUBLIC_PATHS = ("/api/v2/health",)


def new_token() -> str:
    return _secrets.token_hex(TOKEN_BYTES)


class TokenAuth:
    """极简 Bearer/X-API-Token 校验器。"""

    def __init__(self, token: str = "", enabled: bool = True):
        self.token = token or new_token()
        self.enabled = enabled

    # ── 持久化（由 app 负责写回 settings）──
    @classmethod
    def from_settings(cls, settings: dict) -> TokenAuth:
        token = str(settings.get(SETTINGS_KEY) or "")
        auth = cls(token)
        settings[SETTINGS_KEY] = auth.token
        return auth

    def rotate(self) -> str:
        self.token = new_token()
        return self.token

    # ── 校验 ──
    def is_public(self, path: str) -> bool:
        route = (path or "").split("?")[0].rstrip("/")
        return route in PUBLIC_PATHS

    def check(self, path: str, authorization: str = "", api_token: str = "") -> bool:
        """返回是否放行。``path`` 是原始请求路径（含 query 也行）。"""
        if not self.enabled or self.is_public(path):
            return True
        presented = ""
        authorization = (authorization or "").strip()
        if authorization.lower().startswith("bearer "):
            presented = authorization[7:].strip()
        elif api_token:
            presented = api_token.strip()
        if not presented or not self.token:
            return False
        return hmac.compare_digest(presented, self.token)

    def masked(self) -> str:
        """UI 里默认展示的掩码形式。"""
        if len(self.token) <= 8:
            return "••••••"
        return f"{self.token[:4]}••••••••{self.token[-4:]}"
