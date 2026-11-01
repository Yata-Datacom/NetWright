"""telnet_client.py — 轻量 Telnet 客户端（标准库实现）。

支持：IAC 协商字节剥离、登录（用户名/密码提示）、静默窗口读输出。
面向网络设备的"够用"实现；不做完整 RFC 854 终端仿真。
"""
from __future__ import annotations

import re
import socket
import time

IAC = 0xFF


def _strip_iac(data: bytes) -> bytes:
    """剥离 Telnet 协商序列（0xFF + 命令字节），保留纯文本。"""
    out = bytearray()
    i = 0
    while i < len(data):
        b = data[i]
        if b == IAC:
            if i + 1 < len(data) and data[i + 1] == IAC:
                out.append(IAC)       # 转义的双 0xFF = 字面 0xFF
                i += 2
                continue
            i += 2                    # IAC + 命令（DO/DONT/WONT/WILL/SB）
            # 跳过 SB 子协商直到 IAC SE
            if i >= 2 and len(data) >= i and data[i - 1] in (250,):  # SB=250
                while i < len(data):
                    if data[i] == IAC and i + 1 < len(data) and data[i + 1] == 240:
                        i += 2
                        break
                    i += 1
            continue
        out.append(b)
        i += 1
    return bytes(out)


def _recv_until(sock, patterns: list[str], timeout: float, quiet: float = 0.6) -> str:
    """持续读直到命中任一模式或静默窗口超时。"""
    deadline = time.monotonic() + timeout
    buf = b""
    last = time.monotonic()
    compiled = [re.compile(p, re.I) for p in patterns]
    while time.monotonic() < deadline:
        sock.settimeout(0.2)
        try:
            chunk = sock.recv(4096)
            if chunk:
                buf += _strip_iac(chunk)
                last = time.monotonic()
                text = buf.decode("utf-8", "replace")
                if any(c.search(text) for c in compiled):
                    break
        except socket.timeout:
            pass
        except OSError:
            break
        if time.monotonic() - last >= quiet and buf:
            break
    return buf.decode("utf-8", "replace")


def _read_quiet(sock, timeout: float, quiet: float = 0.7) -> str:
    """静默窗口读：无新数据 quiet 秒即返回。"""
    deadline = time.monotonic() + timeout
    buf = b""
    last = time.monotonic()
    while time.monotonic() < deadline:
        sock.settimeout(0.2)
        try:
            chunk = sock.recv(4096)
            if chunk:
                buf += _strip_iac(chunk)
                last = time.monotonic()
        except socket.timeout:
            pass
        except OSError:
            break
        if time.monotonic() - last >= quiet:
            break
    return buf.decode("utf-8", "replace")


_LOGIN_PATTERNS = [r"username[:\s]*$", r"login[:\s]*$", r"password[:\s]*$",
                   r"user ?name"]


def telnet_run_commands(device, commands: list[str], timeout: float = 15.0,
                        port: int = 23) -> list[tuple[str, str, str, str]]:
    """Telnet 登录并执行命令。

    :return: [(title, command, output, error)]
    :raises Exception: 连接/认证失败。
    """
    sock = socket.create_connection((device.host, port), timeout=10)
    results: list[tuple[str, str, str, str]] = []
    try:
        # 登录流程：提示什么就应答什么
        banner = _recv_until(sock, _LOGIN_PATTERNS + [r"[>#\]]\s*$"], timeout)
        low = banner.lower()
        if re.search(r"username|login|user ?name", low):
            sock.sendall(device.username.encode() + b"\n")
            time.sleep(0.3)
            banner += _recv_until(sock, [r"password"], timeout)
            sock.sendall(device.password.encode() + b"\n")
            time.sleep(0.5)
            _read_quiet(sock, 2.0)
        elif re.search(r"password", low):
            sock.sendall(device.password.encode() + b"\n")
            time.sleep(0.5)
            _read_quiet(sock, 2.0)

        for cmd in commands:
            sock.sendall(cmd.encode() + b"\n")
            time.sleep(0.25)
            output = _read_quiet(sock, timeout)
            lines = output.replace("\r\n", "\n").split("\n")
            if lines and lines[0].strip():
                lines = lines[1:]                      # 去掉回显
            while lines and (not lines[-1].strip() or
                             re.search(r"[>#\]]\s*$", lines[-1])):
                lines.pop()
            results.append((cmd, cmd, "\n".join(lines), ""))
    finally:
        try:
            sock.close()
        except OSError:
            pass
    return results
