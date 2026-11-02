"""netconf.py — NETCONF 南向适配器（v3.11：可注入会话的实现）。

不把 ncclient 写死的原因：
  * 本机/CI 常常没装 ncclient，直接 import 会让整个控制器起不来；
  * 会话层（SSH 子系统 + 分块 framing）是最容易出问题的部分，ncclient 已经做得很好，
    我们只负责"把意图翻译成 edit-config"这一层；
  * 通过 ``session_factory`` 注入假会话即可单测 RPC 组装，不需要真设备。

会话对象（鸭子类型）只需实现：
  ``get_config(source=..., filter=...)`` → 带 ``.data``/``.xml`` 的结果
  ``edit_config(target=..., config=...)``
  ``close()``
"""
from __future__ import annotations

import importlib.util

from .base import Capability, CommandOutput, SouthboundAdapter, UnsupportedOperation


class NetconfError(RuntimeError):
    """NETCONF 会话或 RPC 失败。"""


class NetconfAdapter(SouthboundAdapter):
    protocol = "netconf"
    display_name = "NETCONF"
    description = "结构化配置南向：get-config / edit-config，替代 CLI 回显解析"
    capabilities = frozenset({
        Capability.CONFIG_READ, Capability.CONFIG_WRITE, Capability.STATE_READ,
        Capability.EVENT_STREAM,
    })
    transport = "TCP 830 / SSH 子系统"
    requires = ("ncclient>=0.6",)

    def __init__(self, bus=None, session_factory=None, port: int = 830,
                 timeout: float = 30.0):
        super().__init__(bus)
        self.session_factory = session_factory
        self.port = port
        self.timeout = timeout

    def available(self) -> bool:
        return self.session_factory is not None or importlib.util.find_spec("ncclient") is not None

    def note(self) -> str:
        if self.session_factory is not None:
            return "已注入自定义会话（测试/嵌入场景）"
        return "已实装 get-config/edit-config（需要 ncclient）"

    # ── 契约 ──
    def run_commands(self, device, commands: list[str], timeout: float = 15.0) -> list[CommandOutput]:
        raise UnsupportedOperation("NETCONF 不接受 CLI 命令：请用 get_config / edit_config")

    def read_config(self, device, timeout: float = 15.0) -> str:
        return self.get_config(device)

    # ── 会话 ──
    def _open(self, device):
        if self.session_factory is not None:
            return self.session_factory(device)
        if importlib.util.find_spec("ncclient") is None:
            raise UnsupportedOperation("缺少依赖 ncclient，无法建立 NETCONF 会话")
        from ncclient import manager           # 延迟导入：没装也能用其他功能

        return manager.connect(
            host=device.host, port=self.port,
            username=getattr(device, "username", ""),
            password=getattr(device, "password", ""),
            hostkey_verify=False,              # 与 SSH 通道保持一致的内网取舍
            allow_agent=False, look_for_keys=False,
            timeout=self.timeout,
        )

    def _with_session(self, device, fn):
        session = self._open(device)
        try:
            return fn(session)
        except UnsupportedOperation:
            raise
        except Exception as exc:      # noqa: BLE001  第三方异常统一包装
            raise NetconfError(f"NETCONF 调用失败：{exc}") from exc
        finally:
            try:
                session.close()
            except Exception:      # noqa: BLE001
                pass

    # ── RPC ──
    def get_config(self, device, source: str = "running", filter_xml: str | None = None) -> str:
        """取配置；返回原始 XML 文本。"""
        def call(session):
            kwargs = {"source": source}
            if filter_xml:
                kwargs["filter"] = ("subtree", filter_xml)
            reply = session.get_config(**kwargs)
            return getattr(reply, "data", None) or getattr(reply, "xml", "") or str(reply)

        return self._with_session(device, call)

    def edit_config(self, device, config_xml: str, target: str = "candidate",
                    default_operation: str = "merge") -> str:
        """写配置（默认 candidate + merge，调用方负责 commit）。"""
        if not (config_xml or "").strip():
            raise ValueError("配置为空")

        def call(session):
            reply = session.edit_config(target=target, config=config_xml,
                                        default_operation=default_operation)
            return getattr(reply, "xml", "") or str(reply or "ok")

        return self._with_session(device, call)

    def commit(self, device) -> str:
        def call(session):
            reply = session.commit()
            return getattr(reply, "xml", "") or str(reply or "ok")

        return self._with_session(device, call)

    def discard(self, device) -> str:
        def call(session):
            reply = session.discard_changes()
            return getattr(reply, "xml", "") or str(reply or "ok")

        return self._with_session(device, call)
