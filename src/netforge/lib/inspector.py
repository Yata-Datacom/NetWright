"""inspector.py — 批量巡检：内置方案库 + 异常规则 + 结果模型 + HTML 报告（纯逻辑）。

SSH 执行在 ssh_client.py；本模块只做数据与判断，方便单测。
"""
from __future__ import annotations

import html
import re
from concurrent import futures
from dataclasses import dataclass, field

# ── 内置巡检方案（场景 → 厂商 → 命令列表）─────────────────────────────
BUILTIN_SCHEMES: dict[str, dict[str, list[str]]] = {
    "标准巡检": {
        "desc": "版本 / 配置摘要 / 接口 / CPU / 内存 / 日志",
        "commands": {
        "huawei": ["display version", "display ip interface brief", "display cpu-usage",
                   "display memory-usage", "display logbuffer size", "display alarm active"],
        "cisco": ["show version", "show ip interface brief", "show processes cpu sorted | exclude 0.00%",
                  "show memory statistics", "show logging | last 20"],
        "h3c": ["display version", "display ip interface brief", "display cpu-usage",
                "display memory", "display logbuffer"],
        "ruijie": ["show version", "show ip interface brief", "show cpu", "show memory",
                   "show logging | include ERR|CRIT"],
        "linux": ["hostname", "uname -r", "uptime", "free -h", "df -h --total",
                  "systemctl --failed --no-pager"],
        "mikrotik": ["/system identity print", "/system resource print",
                     "/ip address print", "/ip route print", "/log print without-paging"],
        "vyos": ["show interfaces", "show ip route summary", "show dhcp server leases",
                 "show log last 50"],
        "sonic": ["show version", "show interfaces status", "show vlan brief",
                  "show ip route summary", "show logging 50"],
        },
    },
    "硬件健康": {
        "desc": "光功率 / 电源 / 风扇 / 温度 / 硬件告警",
        "commands": {
        "huawei": ["display transceiver diagnosis interface all", "display device",
                   "display power", "display fan", "display temperature all", "display alarm active"],
        "cisco": ["show environment all", "show interfaces transceiver detail", "show inventory"],
        "h3c": ["display transceiver diagnosis interface", "display device", "display power",
                "display fan", "display alarm active"],
        "ruijie": ["show environment", "show inventory", "show interfaces transceiver"],
        "linux": ["dmesg -T | tail -40", "sensors 2>/dev/null || cat /proc/uptime"],
        "mikrotik": ["/system health print", "/system resource print",
                     "/system routerboard print"],
        "vyos": ["show hardware detail", "show interfaces detail"],
        "sonic": ["show platform summary", "show platform psustatus",
                  "show platform temperature", "show platform ssdhealth"],
        },
    },
    "链路与拓扑": {
        "desc": "STP / 邻居 / MAC·ARP / 链路聚合",
        "commands": {
        "huawei": ["display stp brief", "display lldp neighbor brief", "display mac-address",
                   "display arp", "display eth-trunk"],
        "cisco": ["show spanning-tree summary", "show cdp neighbors", "show etherchannel summary",
                  "show mac address-table"],
        "h3c": ["display stp brief", "display lldp neighbor-information brief",
                "display link-aggregation summary", "display mac-address"],
        "ruijie": ["show spanning-tree summary", "show cdp neighbors", "show etherchannel summary"],
        "linux": ["ip -br link", "ip -br addr", "ip neigh"],
        "mikrotik": ["/interface print detail", "/ip neighbor print", "/ip arp print",
                     "/interface bridge vlan print"],
        "vyos": ["show lldp neighbors", "show arp", "show interfaces detail"],
        "sonic": ["show lldp table", "show mac", "show portchannel"],
        },
    },
    "安全基线": {
        "desc": "SSH / 用户 / ACL / SNMP / 暴露面核查",
        "commands": {
        "huawei": ["display ssh server status", "display users", "display acl all",
                   "display snmp-agent community", "display http server"],
        "cisco": ["show ip ssh", "show users", "show access-lists", "show snmp community"],
        "h3c": ["display ssh server status", "display users", "display acl all",
                "display snmp-agent community"],
        "ruijie": ["show ip ssh", "show users", "show access-lists"],
        "linux": ["ss -tunlp", "last -n 15", "lastb -n 20", "journalctl -p warning -n 40 --no-pager"],
        "mikrotik": ["/ip service print", "/user print", "/ip firewall filter print",
                     "/snmp print"],
        "vyos": ["show configuration commands", "show firewall", "show log last 30"],
        "sonic": ["show acl table", "show users", "show logging 30"],
        },
    },
    # ── 高级场景（无 SDN 控制器手工环境）────────────────────────────
    "VXLAN+EVPN": {
        "desc": "数据中心 Overlay：VNI/隧道/EVPN 邻居/MAC 路由（手工 BGP EVPN）",
        "commands": {
            "huawei": ["display vxlan vni", "display vxlan tunnel", "display interface nve 1",
                       "display bgp evpn peer", "display bgp evpn all routing-table",
                       "display bridge-domain"],
            "cisco": ["show nve vni", "show nve peers", "show bgp l2vpn evpn summary",
                      "show mac address-table vni", "show interface nve1"],
            "h3c": ["display vxlan", "display vxlan tunnel", "display bgp peer l2vpn evpn",
                    "display evpn ipv4 auto-discovery", "display interface tunnel"],
        },
    },
    "MPLS/SR 骨干": {
        "desc": "LDP/LSP、VPNv4 邻居、SR Prefix-SID 转发表（PE/骨干排查）",
        "commands": {
            "huawei": ["display mpls lsp", "display mpls ldp session", "display mpls vpn-instance",
                       "display bgp vpnv4 all summary",
                       "display segment-routing prefix mpls forwarding"],
            "cisco": ["show mpls ldp neighbor", "show mpls forwarding-table", "show mpls interfaces",
                      "show bgp vpnv4 unicast all summary",
                      "show mpls label range"],
            "h3c": ["display mpls lsp", "display mpls ldp peer", "display bgp vpnv4 all",
                    "display ip vpn-instance"],
        },
    },
    "堆叠与M-LAG": {
        "desc": "堆叠/集群状态 + 双活检测（CSS/IRF/StackWise、M-LAG/DRNI/vPC/VSU）",
        "commands": {
            "huawei": ["display stack", "display css status", "display dfs-group 1 m-lag",
                       "display eth-trunk"],
            "h3c": ["display irf", "display irf configuration", "display drni summary",
                    "display drni keepalive"],
            "cisco": ["show vpc brief", "show vpc role", "show switch detail"],
            "ruijie": ["show vsu", "show vsu link", "show ethernet-link"],
        },
    },
    "RoCEv2 无损": {
        "desc": "AI/存储无损网：PFC 协商与 PAUSE 计数、ECN/WRED、ETS 带宽（命令随型号有差异）",
        "commands": {
            "huawei": ["display dcb", "display dcb pfc interface", "display dcb ets"],
            "cisco": ["show priority-flow-control", "show queuing interface",
                      "show policy-map type queuing"],
            "h3c": ["display priority-flow-control", "display qos wred interface",
                    "display qos policy interface"],
        },
    },
    "IPv6 与过渡": {
        "desc": "v6 接口/邻居表、OSPFv3/BGP v6、DHCPv6、隧道与 NAT64 状态",
        "commands": {
            "huawei": ["display ipv6 interface brief", "display ipv6 neighbors",
                       "display ospfv3 peer", "display bgp ipv6 peer",
                       "display dhcpv6 pool", "display ipv6 routing-table"],
            "cisco": ["show ipv6 interface brief", "show ipv6 neighbors",
                      "show ipv6 ospf neighbor", "show bgp ipv6 unicast summary",
                      "show ipv6 dhcp pool"],
            "h3c": ["display ipv6 interface brief", "display ipv6 neighbors",
                    "display ospfv3", "display bgp peer ipv6 unicast",
                    "display dhcpv6 pool"],
            "linux": ["ip -6 addr", "ip -6 route", "ip -6 neigh", "ss -6 -tunlp"],
            "mikrotik": ["/ipv6 address print", "/ipv6 route print", "/ipv6 neighbor print"],
            "vyos": ["show ipv6 route", "show interfaces detail", "show ipv6 neighbors"],
            "sonic": ["show ipv6 route", "show ipv6 bgp summary"],
        },
    },
    "无线 WLAN": {
        "desc": "AC/AP 状态：AP 上线、SSID/VAP、客户端、射频（华为/H3C/思科 WLC/MikroTik）",
        "commands": {
            "huawei_ac": ["display ap all", "display vap-profile all", "display ssid-profile all",
                          "display station all", "display radio all",
                          "display capwap configuration"],
            "h3c_ac": ["display wlan ap all", "display wlan service-template",
                       "display wlan client", "display wlan ap-group all"],
            "cisco_wlc": ["show ap summary", "show wlan summary", "show client summary",
                          "show ap join stats summary"],
            "mikrotik": ["/interface wireless print", "/interface wireless registration-table print"],
        },
    },
}

# 关分页命令（进入交互后先发）
DISABLE_PAGING = {
    "huawei": "screen-length 0 temporary",
    "h3c": "screen-length disable",
    "cisco": "terminal length 0",
    "ruijie": "terminal length 0",
    "mikrotik": None,          # RouterOS print 自带分页控制（无参不分页）
    "vyos": None,              # FRR show 默认不分页
    "sonic": "terminal length 0",
    "huawei_ac": "screen-length 0 temporary",
    "h3c_ac": "screen-length disable",
    "cisco_wlc": "terminal length 0",
    "linux": None,
}

# ── 异常规则（对"命令标题 + 输出"做正则判断）──────────────────────────
@dataclass
class Anomaly:
    severity: str      # critical / warning
    title: str
    message: str


ANOMALY_RULES: list[dict] = [
    {"pattern": r"CPU usage.*?(\d{2,3})%", "threshold": 80, "compare": ">",
     "severity": "warning", "title": "CPU 使用率过高", "parse": "int",
     "applies": ("huawei", "h3c", "ruijie", "cisco")},
    {"pattern": r"Memory Usage.*?(\d{1,3})%", "threshold": 85, "compare": ">",
     "severity": "warning", "title": "内存使用率过高", "parse": "int",
     "applies": ("huawei", "h3c")},
    {"pattern": r"(\d+)\s+input errors", "threshold": 0, "compare": ">",
     "severity": "warning", "title": "接口存在 input errors", "parse": "int",
     "applies": ("huawei", "h3c", "cisco", "ruijie")},
    {"pattern": r"(power|POWER).{0,40}(abnormal|fault|absent|failed)", "threshold": 0,
     "compare": "exists", "severity": "critical", "title": "电源异常",
     "applies": ("huawei", "h3c", "cisco", "ruijie")},
    {"pattern": r"(fan|FAN).{0,40}(abnormal|fault|absent|failed)", "threshold": 0,
     "compare": "exists", "severity": "critical", "title": "风扇异常",
     "applies": ("huawei", "h3c", "cisco", "ruijie")},
    {"pattern": r"rx ?power.*?(-\d+\.?\d*)\s*dBm", "threshold": -20.0, "compare": "<",
     "severity": "warning", "title": "光功率偏低（收光 < -20dBm）", "parse": "float",
     "applies": ("huawei", "h3c", "cisco", "ruijie")},
    {"pattern": r"temperature.{0,30}(\d{2,3})", "threshold": 65, "compare": ">",
     "severity": "warning", "title": "温度偏高", "parse": "int",
     "applies": ("huawei", "h3c", "cisco", "ruijie")},
    {"pattern": r"(\d+)\s+failed", "threshold": 0, "compare": ">",
     "severity": "warning", "title": "存在失败的 systemd 服务", "parse": "int",
     "applies": ("linux",)},
    {"pattern": r"(\d+\.\d+),\s*\d+\.\d+,\s*\d+\.\d+", "threshold": 4.0, "compare": ">",
     "severity": "warning", "title": "系统负载过高（load average）", "parse": "float",
     "applies": ("linux",)},
]


def detect_anomalies(devtype: str, title: str, output: str) -> list[Anomaly]:
    """对一段命令输出跑异常规则。"""
    found: list[Anomaly] = []
    if not output:
        return found
    for rule in ANOMALY_RULES:
        if devtype not in rule["applies"]:
            continue
        m = re.search(rule["pattern"], output, re.IGNORECASE)
        if not m:
            continue
        cmp = rule["compare"]
        if cmp == "exists":
            hit, detail = True, f"输出命中特征: {m.group(0)[:60]}"
        else:
            try:
                value = float(m.group(1))
            except (ValueError, IndexError):
                continue
            threshold = float(rule["threshold"])
            hit = value > threshold if cmp == ">" else value < threshold
            detail = f"检测值 {value}，阈值 {threshold}"
        if hit:
            found.append(Anomaly(rule["severity"], rule["title"], detail))
    return found


# ── 巡检结果模型 ──────────────────────────────────────────────────────
@dataclass
class CommandResult:
    title: str
    command: str
    output: str = ""
    error: str = ""
    anomalies: list[Anomaly] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.error


@dataclass
class DeviceResult:
    host: str
    vendor: str
    status: str = "PENDING"     # OK / WARNING / FAILED / UNREACHABLE
    commands: list[CommandResult] = field(default_factory=list)
    error: str = ""
    cost_ms: int = 0

    @property
    def anomalies(self) -> list[Anomaly]:
        out = []
        for c in self.commands:
            out.extend(c.anomalies)
        return out

    @property
    def critical_count(self) -> int:
        return sum(1 for a in self.anomalies if a.severity == "critical")

    def finalize_status(self):
        if self.error and not self.commands:
            self.status = "UNREACHABLE" if "unreachable" in self.error.lower() else "FAILED"
            return
        if self.critical_count:
            self.status = "FAILED"
        elif self.anomalies or any(not c.ok for c in self.commands):
            self.status = "WARNING"
        else:
            self.status = "OK"


def run_device(device, scheme_commands: list[str], timeout: float = 15.0,
               port: int | None = None) -> DeviceResult:
    """SSH 登录单台设备跑一套命令（阻塞，调用方自行放线程池）。

    :param device: inventory.Device
    :param scheme_commands: 该厂商的命令列表
    """
    import time as _time

    from .ssh_client import run_commands

    res = DeviceResult(host=device.host, vendor=device.vendor)
    t0 = _time.monotonic()
    try:
        outputs = run_commands(device, scheme_commands, timeout=timeout, port=port)
        for title, cmd, output, err in outputs:
            cr = CommandResult(title=title, command=cmd, output=output, error=err)
            if not err:
                cr.anomalies = detect_anomalies(device.vendor, title, output)
            res.commands.append(cr)
    except Exception as e:
        msg = str(e)
        lowered = msg.lower()
        if "timed out" in lowered or "timeout" in lowered or "unreachable" in lowered or \
                "refused" in lowered or "network" in lowered:
            res.error = f"无法连接: {msg}"
        elif "auth" in lowered or "password" in lowered or "认证" in msg:
            res.error = f"认证失败: {msg}"
        else:
            res.error = f"连接失败: {msg}"
    res.cost_ms = int((_time.monotonic() - t0) * 1000)
    res.finalize_status()
    return res


def run_batch(devices: list, scheme: dict[str, list[str]], workers: int = 20,
              timeout: float = 15.0, progress=None) -> tuple[list[DeviceResult], list[str]]:
    """并发巡检一批设备（每个设备独立 SSH 会话，跑完即断）。

    方案里没有该厂商命令集的设备会被自动跳过（避免空跑）。
    :return: (结果列表, 跳过原因列表)
    """
    results: list[DeviceResult] = []
    skipped: list[str] = []
    targets = []
    for dev in devices:
        if scheme.get(dev.vendor):
            targets.append(dev)
        else:
            skipped.append(f"{dev.display_name}（{dev.vendor} 无此方案命令集）")
    total = len(targets)
    done = 0
    with futures.ThreadPoolExecutor(max_workers=max(1, min(workers, 100))) as ex:
        futs = {ex.submit(run_device, dev, scheme.get(dev.vendor, []), timeout): dev
                for dev in targets}
        for fut in futures.as_completed(futs):
            results.append(fut.result())
            done += 1
            if progress:
                progress(done, total)
    order = {"FAILED": 0, "WARNING": 1, "OK": 2, "UNREACHABLE": 3}
    return sorted(results, key=lambda r: (order.get(r.status, 9), r.host)), skipped


# ── 报告 ─────────────────────────────────────────────────────────────
def build_html_report(results: list[DeviceResult], scheme_name: str = "") -> str:
    """生成一份可直接浏览器打开的巡检报告（密码永不进入报告）。"""
    dev_rows = []
    detail_parts = []
    color = {"OK": "#16a34a", "WARNING": "#d97706", "FAILED": "#dc2626", "UNREACHABLE": "#64748b"}
    for r in results:
        anomaly_rows = "".join(
            f"<div class='anom {a.severity}'>[{a.severity.upper()}] {html.escape(a.title)}"
            f" — {html.escape(a.message)}</div>"
            for a in r.anomalies) or "<div class='anom none'>无异常</div>"
        dev_rows.append(
            f"<tr><td>{html.escape(r.host)}</td><td>{html.escape(r.vendor)}</td>"
            f"<td style='color:{color.get(r.status, '#333')}'><b>{r.status}</b></td>"
            f"<td>{r.critical_count}</td><td>{len(r.anomalies)}</td><td>{r.cost_ms} ms</td></tr>")
        cmds = "".join(
            f"<div class='cmd'><b>▸ {html.escape(c.command)}</b>"
            + ("" if c.ok else f" <span class='err'>[{html.escape(c.error)}]</span>")
            + f"<pre>{html.escape(c.output[:4000])}</pre></div>"
            for c in r.commands)
        detail_parts.append(
            f"<h3>{html.escape(r.host)} "
            f"<span class='badge' style='background:{color.get(r.status, '#333')}'>{r.status}</span></h3>"
            f"{anomaly_rows}{cmds}")

    counts: dict[str, int] = {}
    for r in results:
        counts[r.status] = counts.get(r.status, 0) + 1
    summary = " · ".join(f"{k} {v}" for k, v in sorted(counts.items()))

    return f"""<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8">
<title>NetForge 巡检报告</title><style>
body{{font-family:"Microsoft YaHei UI",sans-serif;margin:24px;background:#f4f6fa;color:#1c2534}}
table{{border-collapse:collapse;width:100%;background:#fff}}
th,td{{border:1px solid #dde3ec;padding:7px 11px;text-align:left;font-size:13px}}
th{{background:#1b355a;color:#fff}}
h3{{margin:26px 0 8px}} .badge{{color:#fff;font-size:11px;padding:2px 8px;border-radius:10px}}
.anom{{padding:4px 10px;border-radius:6px;margin:3px 0;font-size:12px}}
.anom.critical{{background:#fde8e8;color:#b91c1c}} .anom.warning{{background:#fef3c7;color:#92400e}}
.anom.none{{background:#eef2f7;color:#64748b}}
.cmd{{margin:10px 0;background:#fff;border:1px solid #dde3ec;border-radius:8px;padding:10px}}
.cmd b{{color:#1d4ed8}} .cmd .err{{color:#dc2626}}
pre{{background:#0e1a2e;color:#d7e2f2;padding:10px;border-radius:6px;overflow-x:auto;
font-family:Consolas,monospace;font-size:12px;max-height:340px;white-space:pre-wrap}}
</style></head><body>
<h2>NetForge 巡检报告{(' · ' + html.escape(scheme_name)) if scheme_name else ''}</h2>
<p>{summary}（生成时间见文件名）</p>
<table><tr><th>设备</th><th>厂商</th><th>状态</th><th>严重</th><th>告警</th><th>耗时</th></tr>
{''.join(dev_rows)}</table>
<h2>详细输出</h2>{''.join(detail_parts)}
</body></html>"""
