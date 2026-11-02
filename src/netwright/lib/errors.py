"""errors.py — 把技术异常翻译成"人话 + 下一步"。

控制器里最容易劝退小白的一句话是 ``paramiko.ssh_exception.AuthenticationException``。
这里做一层**只加信息、不改语义**的翻译：原始异常类型仍保留在末尾（排障要用），
但用户先看到的是"哪一步失败、可能是什么原因、建议怎么做"。

约定：
  * 纯函数、不抛异常、不依赖 UI；
  * 对未知异常保持诚实：``类型: 消息``，不编造原因；
  * 可选的 ``paramiko`` 通过类名识别，不 import（未安装也能用）。
"""
from __future__ import annotations

import socket


def _name(exc: BaseException) -> str:
    return type(exc).__name__


def _chain(exc: BaseException) -> list[str]:
    names = []
    current: BaseException | None = exc
    while current is not None and len(names) < 5:
        names.append(_name(current))
        current = current.__cause__ or current.__context__
    return names


def friendly_error(exc: BaseException) -> str:
    """异常 → 面向用户的一段话（含原始信息）。"""
    names = _chain(exc)
    detail = str(exc).strip() or "（无详细信息）"

    if "AuthenticationException" in names or "BadAuthenticationType" in names:
        return ("认证失败：设备拒绝了用户名/密码（或该账号没有 SSH 权限）。"
                f"建议先「🔌 测试连接」确认端口通，再核对凭据与 AAA 配置。原始信息：{detail}")
    if "PasswordRequiredException" in names or "NoValidConnectionsError" in names:
        return (f"无法建立连接：设备可能未开启 SSH，或端口被 ACL 拦截。原始信息：{detail}")
    if "SSHException" in names:
        return (f"SSH 协商失败：设备可能只支持旧算法/密钥，或被安全策略拦截。原始信息：{detail}")
    if isinstance(exc, (socket.timeout, TimeoutError)) or "TimeoutError" in names:
        return (f"连接超时：检查管理地址/端口是否可达、ACL 是否放行，以及设备是否繁忙。原始信息：{detail}")
    if isinstance(exc, ConnectionRefusedError) or "refused" in detail.lower():
        return (f"端口拒绝连接：目标端口没有服务在监听（SSH/Telnet 未开启），或被策略拦截。原始信息：{detail}")
    if isinstance(exc, PermissionError):
        return (f"权限不足：本机无法读写目标（Windows 上常见于杀毒软件/目录 ACL）。原始信息：{detail}")
    if isinstance(exc, FileNotFoundError):
        return f"文件不存在：{detail}"
    if isinstance(exc, ValueError):
        # 业务校验错误已经是人话，原样透出
        return detail

    if "UnsupportedOperation" in names:
        return (f"该能力还没实装（或当前通道不支持）：{detail}。"
                "可换用 CLI 通道，或查看「事件 → 南向通道」里的能力位。")
    if "RestconfError" in names:
        status = getattr(exc, "status", 0)
        hint = {401: "凭据或权限问题", 403: "账号无该路径权限",
                404: "资源路径/型号不支持", 409: "配置冲突"}.get(status, "检查设备 RESTCONF 配置")
        return f"RESTCONF 失败（HTTP {status or '?'}）：{hint}。{detail}"
    if "NetconfError" in names:
        return (f"NETCONF 会话失败：确认 830 端口与 ncclient 已安装、账号有 netconf 权限。{detail}")
    if "LifecycleError" in names:
        return f"操作被状态机拒绝：{detail}（先看「运行档案」里的当前状态）"
    if "BerError" in names:
        return f"报文解析失败：{detail}"

    return f"{_name(exc)}: {detail}"


# 字符串版：适配那些已经在上游被转成文本的错误（如巡检结果里的 error 字段）
KEYWORD_RULES = (
    ("authentication failed", "认证失败：用户名/密码被拒绝，先测端口再核对账号与 AAA 配置"),
    ("auth fail", "认证失败：用户名/密码被拒绝"),
    ("timed out", "连接超时：检查地址/端口/ACL，或设备 SSH 服务是否开启"),
    ("timeout", "连接超时：检查地址/端口/ACL，或设备 SSH 服务是否开启"),
    ("refused", "端口拒绝连接：目标端口没有服务在监听或被策略拦截"),
    ("unreachable", "网络不可达：检查路由与管理网段是否互通"),
    ("no route", "网络不可达：检查路由与管理网段是否互通"),
    ("permission denied", "权限不足：账号权限或本机文件权限问题"),
    ("unsupported", "能力未实装：换通道或查看南向能力位"),
)


def friendly_text(message: str) -> str:
    """把已经是字符串的错误翻译成人话；认不出来就原样返回。"""
    text = (message or "").strip()
    if not text:
        return ""
    low = text.lower()
    for keyword, friendly in KEYWORD_RULES:
        if keyword in low:
            return f"{friendly}（原始信息：{text}）"
    return text
