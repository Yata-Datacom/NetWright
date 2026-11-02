"""restconf.py — RESTCONF 南向适配器（骨架）。

RESTCONF 的价值：不用重建会话，直接对 ``/restconf/data/...`` 做 GET/PATCH，
适合云网设备与 SONiC 一类带 HTTPS API 的设备。实现计划：
  * 认证：Basic Auth（凭据来自 inventory），或后续接 token；
  * 读：``GET /restconf/data/ietf-interfaces:interfaces``；
  * 写：``PATCH`` + ``Content-Type: application/yang-data+json``；
  * 事件：``GET /restconf/streams`` 拉订阅地址，再走 SSE 长连接。
"""
from __future__ import annotations

import base64
import json
import urllib.error
import urllib.request

from .base import Capability, CommandOutput, SouthboundAdapter, UnsupportedOperation


class RestconfAdapter(SouthboundAdapter):
    protocol = "restconf"
    display_name = "RESTCONF（骨架）"
    description = "HTTPS/YANG 南向：面向云网设备与 SONiC 的结构化读写"
    capabilities = frozenset({
        Capability.CONFIG_READ, Capability.CONFIG_WRITE, Capability.STATE_READ,
    })
    transport = "HTTPS 443"
    requires = ()

    def available(self) -> bool:
        return True       # 标准库 urllib 即可，无需第三方依赖

    def note(self) -> str:
        return "骨架：仅实现了只读 GET，PATCH 与订阅待实装"

    def run_commands(self, device, commands: list[str], timeout: float = 15.0) -> list[CommandOutput]:
        raise UnsupportedOperation("RESTCONF 不接受 CLI 命令：请用 get_path/patch_path")

    # ── 只在骨架里先落地只读能力（其余保持未实装，避免半成品被误用）──
    def get_path(self, device, path: str, timeout: float = 10.0) -> dict:
        """GET ``/restconf/data/<path>``，返回解析后的 JSON。"""
        host = getattr(device, "host", "")
        if not host:
            raise ValueError("设备地址为空")
        url = f"https://{host}/restconf/data/{path.lstrip('/')}"
        request = urllib.request.Request(url, headers=self._headers(device))
        try:
            with urllib.request.urlopen(request, timeout=timeout) as resp:  # noqa: S310  内网设备
                return json.loads(resp.read().decode("utf-8", "replace") or "{}")
        except urllib.error.HTTPError as e:
            raise UnsupportedOperation(f"RESTCONF GET {path} 失败：HTTP {e.code}") from e
        except (urllib.error.URLError, TimeoutError) as e:
            raise UnsupportedOperation(f"RESTCONF GET {path} 连接失败：{e}") from e

    def patch_path(self, device, path: str, payload: dict, timeout: float = 10.0) -> int:
        raise UnsupportedOperation("RESTCONF PATCH 待实装（骨架）")

    def _headers(self, device) -> dict:
        user = getattr(device, "username", "") or ""
        password = getattr(device, "password", "") or ""
        token = base64.b64encode(f"{user}:{password}".encode()).decode("ascii")
        return {"Authorization": f"Basic {token}",
                "Accept": "application/yang-data+json",
                "Content-Type": "application/yang-data+json"}
