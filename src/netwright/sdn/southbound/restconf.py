"""restconf.py — RESTCONF 南向适配器（v3.11 起为完整实装的只读 + 写入通道）。

为什么先做 RESTCONF：标准库 urllib 就能完成 HTTPS + JSON，不引入第三方依赖；
SONiC / 云网设备 / 新一代园区设备普遍提供 ``/restconf/data/...`` 接口，
比 CLI 回显解析稳，比 NETCONF 少一层会话状态。

实现边界（诚实说明）：
  * 支持 GET / PATCH / POST / DELETE，Basic Auth；
  * TLS 默认校验证书，可用 ``verify_tls=False`` 关闭（内网自签名场景，需自己承担风险）；
  * 不支持 SSE 订阅（``/restconf/streams``），需要时再补；
  * 错误统一抛 :class:`RestconfError`，带 HTTP 状态码与响应片段，便于上层展示。
"""
from __future__ import annotations

import base64
import json
import ssl
import urllib.error
import urllib.request

from .base import Capability, CommandOutput, SouthboundAdapter, UnsupportedOperation

JSON_ACCEPT = "application/yang-data+json"


class RestconfError(RuntimeError):
    """RESTCONF 调用失败（网络/HTTP 状态/JSON 解析）。"""

    def __init__(self, message: str, status: int = 0, body: str = ""):
        super().__init__(message)
        self.status = status
        self.body = body


class RestconfAdapter(SouthboundAdapter):
    protocol = "restconf"
    display_name = "RESTCONF"
    description = "HTTPS/YANG 南向：面向 SONiC 与云网设备的结构化读写"
    capabilities = frozenset({
        Capability.CONFIG_READ, Capability.CONFIG_WRITE, Capability.STATE_READ,
    })
    transport = "HTTPS 443"
    requires = ()

    def __init__(self, bus=None, scheme: str = "https", port: int | None = None,
                 verify_tls: bool = True, ca_file: str | None = None):
        super().__init__(bus)
        self.scheme = scheme
        self.port = port
        self.verify_tls = verify_tls
        self.ca_file = ca_file

    def available(self) -> bool:
        return True       # 标准库即可

    def note(self) -> str:
        return "已实装 GET/PATCH/POST/DELETE（Basic Auth；TLS 可配）"

    # ── 适配器契约 ──
    def run_commands(self, device, commands: list[str], timeout: float = 15.0) -> list[CommandOutput]:
        raise UnsupportedOperation("RESTCONF 不接受 CLI 命令：请用 get_path / patch_path")

    def read_config(self, device, timeout: float = 15.0) -> str:
        """读取设备全部可读数据（``GET /restconf/data``），返回格式化 JSON 文本。"""
        data = self.get_path(device, "", timeout=timeout)
        return json.dumps(data, ensure_ascii=False, indent=2)

    # ── HTTP 原语 ──
    def get_path(self, device, path: str = "", timeout: float = 10.0) -> dict:
        status, body = self._request(device, "GET", path, timeout=timeout)
        if not body:
            return {}
        try:
            return json.loads(body)
        except ValueError as exc:
            raise RestconfError(f"RESTCONF 返回的不是 JSON：{body[:120]}", status) from exc

    def patch_path(self, device, path: str, payload: dict, timeout: float = 10.0) -> int:
        return self._request(device, "PATCH", path, payload=payload, timeout=timeout)[0]

    def post_path(self, device, path: str, payload: dict, timeout: float = 10.0) -> int:
        return self._request(device, "POST", path, payload=payload, timeout=timeout)[0]

    def delete_path(self, device, path: str, timeout: float = 10.0) -> int:
        return self._request(device, "DELETE", path, timeout=timeout)[0]

    # ── 内部 ──
    def _url(self, device, path: str) -> str:
        host = getattr(device, "host", "") or ""
        if not host:
            raise RestconfError("设备地址为空")
        port = self.port or getattr(device, "restconf_port", None) or (
            443 if self.scheme == "https" else 80)
        route = (path or "").lstrip("/")
        url = f"{self.scheme}://{host}:{port}/restconf/data"
        return f"{url}/{route}" if route else url

    def _context(self):
        if self.scheme != "https":
            return None
        if not self.verify_tls:
            return ssl._create_unverified_context()      # noqa: S323  内网自签名显式选择
        return ssl.create_default_context(cafile=self.ca_file)

    def _headers(self, device) -> dict:
        user = getattr(device, "username", "") or ""
        password = getattr(device, "password", "") or ""
        token = base64.b64encode(f"{user}:{password}".encode()).decode("ascii")
        return {"Authorization": f"Basic {token}",
                "Accept": JSON_ACCEPT,
                "Content-Type": JSON_ACCEPT}

    def _request(self, device, method: str, path: str, payload: dict | None = None,
                 timeout: float = 10.0) -> tuple[int, str]:
        url = self._url(device, path)
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8") if payload is not None else None
        request = urllib.request.Request(url, data=data, method=method,
                                         headers=self._headers(device))
        try:
            with urllib.request.urlopen(request, timeout=timeout,
                                        context=self._context()) as resp:  # noqa: S310  内网设备
                return resp.status, resp.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as exc:
            body = ""
            try:
                body = exc.read().decode("utf-8", "replace")[:400]
            except Exception:      # noqa: BLE001
                pass
            raise RestconfError(f"RESTCONF {method} {path or '/'} 失败：HTTP {exc.code}",
                                status=exc.code, body=body) from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise RestconfError(f"RESTCONF {method} {path or '/'} 连接失败：{exc}") from exc

    # ── 便捷方法（按需扩展）──
    def get_interfaces(self, device, timeout: float = 10.0) -> dict:
        """OpenConfig 接口表（SONiC / 多数云网设备通用）。"""
        return self.get_path(device, "openconfig-interfaces:interfaces", timeout=timeout)
