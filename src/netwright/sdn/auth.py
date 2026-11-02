"""auth.py — 北向 REST 的令牌鉴权（多 token + 只读 scope + 轮换记录，R6）。

为什么不用用户名密码：控制器是"工具型服务"，调用方是脚本/CI/另一个程序，
一个可轮换的 Bearer token 比账号体系更贴合场景，也更容易在 UI 里展示与复制。

token 模型（R6 起）：
  * **主 token**（write）：GUI「REST API」页展示的那个，``rotate()`` 一键轮换；
  * **子 token**（read/write）：``issue(scope, label)`` 发给脚本/同事，
    只读 token 只能 GET，写操作返回 403；可单独 ``revoke``，不影响主 token；
  * 所有 token 存 ``tokens: dict[token, {"scope", "label"}]``，由 app 持久化到
    settings（键 ``api_tokens``）；轮换历史记录在 ``rotation_log``（内存）。

安全边界（明确写出来，避免误判）：
  * 只监听 127.0.0.1，token 是**第二道闸**，不是公网防护；
  * token 存在 `netwright_settings.json`（本地文件），可以一键轮换；
  * 比较用 :func:`hmac.compare_digest` 逐一比对，避免时序侧信道。
"""
from __future__ import annotations

import hmac
import secrets as _secrets
import time

TOKEN_BYTES = 24          # → 48 位十六进制，足够暴力不可猜
SETTINGS_KEY = "api_token"
SUBTOKENS_KEY = "api_tokens"
PUBLIC_PATHS = ("/api/v2/health",)
SCOPES = ("read", "write")


def new_token() -> str:
    return _secrets.token_hex(TOKEN_BYTES)


class TokenAuth:
    """多 token Bearer/X-API-Token 校验器（read/write 两档 scope）。"""

    def __init__(self, token: str = "", enabled: bool = True):
        self.enabled = enabled
        self.tokens: dict[str, dict] = {}
        self.rotation_log: list[dict] = []      # [{time, action, label}]
        self.token = ""
        self.set_primary(token or new_token())

    # ── 持久化（由 app 负责写回 settings）──
    @classmethod
    def from_settings(cls, settings: dict) -> TokenAuth:
        token = str(settings.get(SETTINGS_KEY) or "")
        auth = cls(token)
        subs = settings.get(SUBTOKENS_KEY)
        if isinstance(subs, dict):
            for sub, info in subs.items():
                if isinstance(info, dict) and isinstance(info.get("scope"), str):
                    auth.tokens[str(sub)] = {"scope": info["scope"],
                                             "label": str(info.get("label", ""))}
        settings[SETTINGS_KEY] = auth.token
        settings[SUBTOKENS_KEY] = auth.export()
        return auth

    def export(self) -> dict:
        """子 token 快照（不含主 token；主 token 走 SETTINGS_KEY）。"""
        return {t: {"scope": info["scope"], "label": info["label"]}
                for t, info in self.tokens.items() if t != self.token}

    # ── 生命周期 ──
    def set_primary(self, token: str) -> str:
        if self.token and self.token in self.tokens:
            old = self.tokens.pop(self.token)
            self.rotation_log.append({"time": time.time(), "action": "rotated_out",
                                      "label": old.get("label", "primary")})
        self.token = token
        self.tokens[token] = {"scope": "write", "label": "primary"}
        return token

    def rotate(self) -> str:
        """轮换主 token：旧 token 立即 401。"""
        return self.set_primary(new_token())

    def issue(self, scope: str = "read", label: str = "") -> str:
        """发一个子 token；scope 只支持 read / write（默认 read）。"""
        token = new_token()
        self.tokens[token] = {"scope": scope if scope in SCOPES else "read",
                              "label": label or f"sub-{len(self.tokens)}"}
        self.rotation_log.append({"time": time.time(), "action": "issued",
                                  "label": self.tokens[token]["label"]})
        return token

    def revoke(self, token: str) -> bool:
        """吊销子 token；主 token 不可单独吊销（请走 rotate）。"""
        if token == self.token or token not in self.tokens:
            return False
        info = self.tokens.pop(token)
        self.rotation_log.append({"time": time.time(), "action": "revoked",
                                  "label": info.get("label", "")})
        return True

    def label_of(self, token: str) -> str:
        return (self.tokens.get(token) or {}).get("label", "")

    # ── 校验 ──
    def is_public(self, path: str) -> bool:
        route = (path or "").split("?")[0].rstrip("/")
        return route in PUBLIC_PATHS

    @staticmethod
    def _presented(authorization: str, api_token: str) -> str:
        authorization = (authorization or "").strip()
        if authorization.lower().startswith("bearer "):
            return authorization[7:].strip()
        return (api_token or "").strip()

    def lookup(self, authorization: str = "", api_token: str = "") -> dict | None:
        """按呈现的 token 查信息；用 compare_digest 防时序侧信道。"""
        presented = self._presented(authorization, api_token)
        if not presented:
            return None
        for token, info in self.tokens.items():
            if hmac.compare_digest(presented, token):
                return info
        return None

    def authorize(self, path: str, method: str = "GET",
                  authorization: str = "", api_token: str = "") -> tuple[bool, str, str]:
        """完整鉴权：返回 (ok, token_label, error)。

        401（无效 token）与 403（scope 不足）在这里区分；
        只读 token 只能 GET，其余方法一律 403。
        """
        if not self.enabled or self.is_public(path):
            return True, "public", ""
        info = self.lookup(authorization, api_token)
        if info is None:
            return False, "", "缺少或无效的 API token"
        if (method or "GET").upper() != "GET" and info.get("scope") != "write":
            return False, info.get("label", ""), \
                "只读 token 无权执行写操作（scope=read）"
        return True, info.get("label", ""), ""

    def check(self, path: str, authorization: str = "", api_token: str = "") -> bool:
        """兼容旧接口：返回是否放行（不区分 401/403）。"""
        ok, _label, _err = self.authorize(path, "GET", authorization, api_token)
        return ok

    def masked(self) -> str:
        """UI 里默认展示的掩码形式。"""
        if len(self.token) <= 8:
            return "••••••"
        return f"{self.token[:4]}••••••••{self.token[-4:]}"
