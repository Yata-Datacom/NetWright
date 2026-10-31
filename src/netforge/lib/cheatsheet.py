"""cheatsheet.py — 网络工程师命令速查（场景 × 厂商）。"""

from __future__ import annotations

CHEATSHEET: dict[str, dict[str, list[tuple[str, str]]]] = {
    "接口与VLAN": {
        "华为 VRP": [
            ("看接口状态", "display interface brief"),
            ("看接口 VLAN 归属", "display port vlan active"),
            ("配 Access 口", "port link-type access / port default vlan 10"),
            ("配 Trunk 口", "port link-type trunk / port trunk allow-pass vlan 10 20"),
        ],
        "思科 IOS": [
            ("看接口状态", "show interfaces status"),
            ("配 Access 口", "switchport mode access / switchport access vlan 10"),
            ("配 Trunk 口", "switchport trunk encapsulation dot1q / switchport mode trunk"),
            ("VLAN 一览", "show vlan brief"),
        ],
        "新华三 Comware": [
            ("看接口状态", "display interface brief"),
            ("配 Access 口", "port link-type access / port access vlan 10"),
            ("配 Trunk 口", "port link-type trunk / port trunk permit vlan 10 20"),
        ],
        "锐捷 RGOS": [
            ("看接口状态", "show interfaces status"),
            ("VLAN 一览", "show vlan brief"),
        ],
    },
    "链路故障": {
        "通用": [
            ("看错包（CRC/drops）", "show interfaces | include errors|CRC|drops"),
            ("看光功率", "display transceiver diagnosis interface all / show interfaces transceiver detail"),
            ("看链路震荡日志", "display logbuffer / show logging | include LINK"),
            ("看 MAC 是否漂移", "display mac-address / show mac address-table"),
        ],
    },
    "路由协议": {
        "华为 VRP": [
            ("OSPF 邻居", "display ospf peer brief"),
            ("BGP 对等体", "display bgp peer"),
            ("路由表", "display ip routing-table"),
            ("VRRP 状态", "display vrrp brief"),
        ],
        "思科 IOS": [
            ("OSPF 邻居", "show ip ospf neighbor"),
            ("BGP 摘要", "show ip bgp summary"),
            ("HSRP 状态", "show standby brief"),
            ("路由表摘要", "show ip route summary"),
        ],
        "新华三 Comware": [
            ("OSPF 邻居", "display ospf peer"),
            ("路由表", "display ip routing-table"),
            ("VRRP 状态", "display vrrp"),
        ],
    },
    "安全与管理": {
        "通用": [
            ("NETCONF 端口", "830（SSH 复用）— display ssh server status / show ip ssh"),
            ("SNMP 团体字核对", "display snmp-agent community / show snmp community"),
            ("在线用户与会话", "display users / show users"),
            ("ACL 一览", "display acl all / show access-lists"),
        ],
        "Linux": [
            ("监听端口", "ss -tunlp"),
            ("登录失败", "lastb -n 20"),
            ("失败服务", "systemctl --failed --no-pager"),
        ],
    },
    "DHCP": {
        "华为 VRP": [
            ("地址池使用情况", "display ip pool"),
            ("DHCP 服务统计", "display dhcp server statistics"),
        ],
        "思科 IOS": [
            ("租约绑定", "show ip dhcp binding"),
            ("Snooping 状态", "show ip dhcp snooping"),
        ],
        "新华三 Comware": [
            ("地址分配", "display dhcp server ip-in-use"),
        ],
    },
    "常用端口": {
        "网络服务": [
            ("SSH / NETCONF", "22 / 830"),
            ("TFTP（ZTP 开局）", "69"),
            ("SNMP / Syslog", "161 / 514"),
            ("HTTPS / HTTP-Alt", "443 / 8080"),
            ("RDP / IPMI", "3389 / 623"),
        ],
    },
}


def search(keyword: str) -> list[tuple[str, str, str, str]]:
    """按关键字过滤速查表。

    :return: (场景, 厂商, 标题, 命令) 列表；关键字匹配场景/厂商/标题/命令任意一处。
    """
    kw = (keyword or "").strip().lower()
    out = []
    for scene, vendors in CHEATSHEET.items():
        for vendor, items in vendors.items():
            for title, cmd in items:
                if not kw or kw in scene.lower() or kw in vendor.lower() \
                        or kw in title.lower() or kw in cmd.lower():
                    out.append((scene, vendor, title, cmd))
    return out
