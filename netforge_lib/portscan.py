"""portscan.py — TCP 端口扫描与 ICMP 在线检测。

纯逻辑 + 线程池 IO；UI 只做展示。Windows 在线检测用系统 ping（无需管理员）。
"""
from __future__ import annotations

import concurrent.futures as futures
import ipaddress
import re
import socket
import subprocess
from dataclasses import dataclass

# 常用端口速查（TCP）
COMMON_PORTS: dict[int, str] = {
    21: "FTP", 22: "SSH", 23: "Telnet", 25: "SMTP", 53: "DNS",
    67: "DHCP Server", 68: "DHCP Client", 69: "TFTP", 80: "HTTP",
    110: "POP3", 123: "NTP", 135: "RPC", 139: "NetBIOS", 143: "IMAP",
    161: "SNMP", 389: "LDAP", 443: "HTTPS", 445: "SMB", 514: "Syslog",
    623: "IPMI", 830: "NETCONF", 873: "rsync", 1080: "SOCKS",
    1433: "MSSQL", 1521: "Oracle", 2049: "NFS", 3389: "RDP",
    5060: "SIP", 5432: "PostgreSQL", 6379: "Redis", 8080: "HTTP-Alt",
    8443: "HTTPS-Alt", 9090: "WebGUI", 9418: "git",
}


@dataclass
class PortResult:
    port: int
    state: str          # open / closed / filtered
    service: str


@dataclass
class PingResult:
    ip: str
    alive: bool
    delay_ms: float     # -1 表示不可达
    hostname: str = ""


def parse_ports(spec: str) -> list[int]:
    """解析端口描述：'22,80,443' / '1-1024' / '22 80 8000-8100' 混合。

    :raises ValueError: 非法端口或范围过大（>8192 个）。
    """
    ports: set[int] = set()
    spec = (spec or "").strip()
    if not spec:
        raise ValueError("请填写端口")
    for token in re.split(r"[,\s;；，、]+", spec):
        if not token:
            continue
        m = re.fullmatch(r"(\d{1,5})-(\d{1,5})", token)
        if m:
            lo, hi = int(m.group(1)), int(m.group(2))
            if lo > hi or not (1 <= lo <= 65535) or not (1 <= hi <= 65535):
                raise ValueError(f"端口范围非法: {token}")
            ports.update(range(lo, hi + 1))
        elif token.isdigit():
            p = int(token)
            if not (1 <= p <= 65535):
                raise ValueError(f"端口非法: {token}")
            ports.add(p)
        else:
            raise ValueError(f"无法识别的端口描述: {token}")
    if len(ports) > 8192:
        raise ValueError("单次扫描端口数过多（上限 8192），请缩小范围")
    return sorted(ports)


def parse_ip_targets(spec: str) -> list[str]:
    """解析检测目标：单 IP / CIDR / a-b 区间 / 逗号混合，展开为 IP 列表。

    :raises ValueError: 非法输入或展开后超过 4096 个地址。
    """
    ips: list[str] = []
    seen: set[str] = set()
    for token in re.split(r"[,\s;；，、]+", (spec or "").strip()):
        if not token:
            continue
        try:
            m = re.fullmatch(r"(\d{1,3}(?:\.\d{1,3}){3})-(\d{1,3}(?:\.\d{1,3}){3})", token)
            if m:
                start, end = ipaddress.IPv4Address(m.group(1)), ipaddress.IPv4Address(m.group(2))
                if int(start) > int(end):
                    raise ValueError(f"区间起止颠倒: {token}")
                for ip_int in range(int(start), int(end) + 1):
                    ip = str(ipaddress.IPv4Address(ip_int))
                    if ip not in seen:
                        seen.add(ip)
                        ips.append(ip)
                continue
            # 末八位简写：192.0.2.10-12
            m = re.fullmatch(r"(\d{1,3}(?:\.\d{1,3}){2})\.(\d{1,3})-(\d{1,3})", token)
            if m:
                base = m.group(1)
                lo, hi = int(m.group(2)), int(m.group(3))
                if lo > hi or lo < 0 or hi > 255:
                    raise ValueError(f"区间非法: {token}")
                for last in range(lo, hi + 1):
                    ip = f"{base}.{last}"
                    if ip not in seen:
                        seen.add(ip)
                        ips.append(ip)
                continue
            if "/" in token:
                for ip in ipaddress.ip_network(token, strict=False).hosts():
                    if str(ip) not in seen:
                        seen.add(str(ip))
                        ips.append(str(ip))
                continue
            ipaddress.IPv4Address(token)  # 校验
            if token not in seen:
                seen.add(token)
                ips.append(token)
        except ValueError as e:
            raise ValueError(f"无法解析目标: {token} ({e})") from e
    if len(ips) > 4096:
        raise ValueError("单次检测地址数过多（上限 4096），请缩小范围")
    return ips


def tcp_port(host: str, port: int, timeout: float = 1.5) -> PortResult:
    """单个 TCP connect 探测。"""
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return PortResult(port, "open", COMMON_PORTS.get(port, ""))
    except OSError:
        return PortResult(port, "closed", COMMON_PORTS.get(port, ""))


def scan_ports(host: str, ports: list[int], workers: int = 200,
               timeout: float = 1.5, progress=None) -> list[PortResult]:
    """并发 TCP 扫描，返回全部结果（open 优先排序在前）。"""
    results: list[PortResult] = []
    done = 0
    with futures.ThreadPoolExecutor(max_workers=max(1, min(workers, 500))) as ex:
        futs = {ex.submit(tcp_port, host, p, timeout): p for p in ports}
        for fut in futures.as_completed(futs):
            results.append(fut.result())
            done += 1
            if progress and done % 50 == 0:
                progress(done, len(ports))
    order = {"open": 0, "closed": 2, "filtered": 1}
    return sorted(results, key=lambda r: (order.get(r.state, 9), r.port))


def ping_host(ip: str, timeout_ms: int = 1000) -> PingResult:
    """用系统 ping 探测（Windows: ping -n 1 -w）。跨平台兼容 Linux/macOS。"""
    import sys
    if sys.platform == "win32":
        cmd = ["ping", "-n", "1", "-w", str(timeout_ms), ip]
    else:
        cmd = ["ping", "-c", "1", "-W", str(max(1, timeout_ms // 1000)), ip]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout_ms / 500 + 3)
        out = proc.stdout or ""
        alive = proc.returncode == 0 and ("TTL" in out or "ttl=" in out or "=1" in out or "1 received" in out)
        delay = -1.0
        m = re.search(r"[=<]([\d.]+)\s*ms", out) or re.search(r"time[=<]([\d.]+)\s*ms", out)
        if alive and m:
            delay = float(m.group(1))
        return PingResult(ip, alive, delay)
    except Exception:
        return PingResult(ip, False, -1.0)


def sweep_hosts(ips: list[str], workers: int = 100, timeout_ms: int = 1000,
                resolve_names: bool = False, progress=None) -> list[PingResult]:
    """并发 ping 一批地址，返回结果（存活优先，按 IP 排序）。"""
    results: list[PingResult] = []
    with futures.ThreadPoolExecutor(max_workers=max(1, min(workers, 300))) as ex:
        futs = {ex.submit(ping_host, ip, timeout_ms): ip for ip in ips}
        done = 0
        for fut in futures.as_completed(futs):
            r = fut.result()
            if resolve_names and r.alive:
                try:
                    r.hostname = socket.gethostbyaddr(r.ip)[0]
                except OSError:
                    pass
            results.append(r)
            done += 1
            if progress and done % 20 == 0:
                progress(done, len(ips))
    alive_first = sorted(results, key=lambda r: (0 if r.alive else 1, ip2int(r.ip)))
    return alive_first


def ip2int(ip: str) -> int:
    try:
        return int(ipaddress.IPv4Address(ip))
    except ValueError:
        return 0
