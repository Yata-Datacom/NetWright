"""ssh_client.py — paramiko SSH 执行器：网络设备用交互 shell（免 exec 通道限制），Linux 用 exec。

每台设备一个独立连接，跑完即断（与 NetPilot/Inspection 同一套哲学）。
"""
from __future__ import annotations

import re

from .inspector import DISABLE_PAGING

_PROMPTS = re.compile(r"[<\[][\w\-.]+[>\]]\s*$|#\s*$|\$\s*$")


def run_commands(device, commands: list[str], timeout: float = 15.0,
                 port: int | None = None) -> list[tuple[str, str, str, str]]:
    """登录设备依次执行命令。

    :return: [(title, command, output, error)]；error 非空表示该命令失败。
    :raises Exception: 连接/认证失败时抛出（调用方转成 DeviceResult.error）。
    """
    if getattr(device, "protocol", "ssh") == "telnet":
        from .telnet_client import telnet_run_commands
        return telnet_run_commands(device, commands, timeout=timeout)
    import time

    import paramiko

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())  # noqa: S507  内网工具定位；严格校验见 SECURITY.md
    port = port or device.port or 22
    client.connect(device.host, port=port, username=device.username,
                   password=device.password, timeout=10, allow_agent=False,
                   look_for_keys=False, banner_timeout=15, auth_timeout=15)

    results: list[tuple[str, str, str, str]] = []
    try:
        if device.vendor == "linux":
            for cmd in commands:
                try:
                    _, stdout, stderr = client.exec_command(cmd, timeout=timeout)
                    out = stdout.read().decode("utf-8", "replace")
                    err = stderr.read().decode("utf-8", "replace").strip()
                    results.append((cmd, cmd, out, err[:300]))
                except Exception as e:
                    results.append((cmd, cmd, "", str(e)))
            return results

        # 网络设备：交互 shell + 关分页
        channel = client.invoke_shell()
        time.sleep(0.6)
        _drain(channel)
        paging = DISABLE_PAGING.get(device.vendor)
        if paging:
            channel.sendall(paging + "\n")
            time.sleep(0.4)
            _drain(channel)
        for cmd in commands:
            channel.sendall(cmd + "\n")
            output = _read_until_quiet(channel, timeout)
            results.append((cmd, cmd, output, ""))
        channel.close()
    finally:
        try:
            client.close()
        except Exception:
            pass
    return results


def _drain(channel):
    while channel.recv_ready():
        channel.recv(65535)


def _read_until_quiet(channel, timeout: float, quiet_window: float = 0.8,
                      max_wait: float | None = None) -> str:
    """持续读输出直到 quiet_window 内无新数据或超时。"""
    import time
    deadline = time.monotonic() + timeout
    chunks: list[bytes] = []
    last_data = time.monotonic()
    max_wait = max_wait or timeout + 15
    hard_deadline = time.monotonic() + max_wait
    while time.monotonic() < deadline and time.monotonic() < hard_deadline:
        got = False
        while channel.recv_ready():
            chunks.append(channel.recv(65535))
            got = True
            last_data = time.monotonic()
        if time.monotonic() - last_data >= quiet_window:
            break
        if not got:
            time.sleep(0.05)
    text = b"".join(chunks).decode("utf-8", "replace")
    # 去掉回显的首个命令行与末尾提示符
    lines = text.replace("\r\n", "\n").split("\n")
    if lines and lines[0].strip():
        lines = lines[1:]
    while lines and (_PROMPTS.search(lines[-1]) or not lines[-1].strip()):
        lines.pop()
    return "\n".join(lines)
