"""intents.py — 意图目录与厂商渲染器（纯函数）。

每个意图类型声明：
  key / title / desc / fields（新手友好的表单字段：名称、类型、必填、默认值、说明）
渲染器 render(intent, device) -> list[str]：把一份意图翻译成该厂商的命令序列。
未知厂商 → 抛 ValueError（绝不猜命令）。
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

VLAN_RE = re.compile(r"^\d{1,4}$")
IPV4_RE = re.compile(r"^(\d{1,3}\.){3}\d{1,3}$")


@dataclass
class FieldSpec:
    name: str                 # 参数名
    label: str                # 表单标签（中文）
    type: str = "text"        # text / int / choice
    required: bool = True
    default: str = ""
    choices: list = field(default_factory=list)
    hint: str = ""            # 新手提示


@dataclass
class IntentSpec:
    key: str
    title: str
    desc: str
    fields: list[FieldSpec]

    def validate(self, intent: dict) -> dict:
        """校验并规范化意图参数（类型转换 / 必填 / choice），返回干净副本。"""
        out: dict = {}
        for f in self.fields:
            raw = str(intent.get(f.name, "")).strip()
            if not raw:
                if f.required:
                    raise ValueError(f"缺少必填参数: {f.label}（{f.name}）")
                if f.default:
                    raw = str(f.default)
                else:
                    continue
            if f.type == "int":
                if not raw.isdigit():
                    raise ValueError(f"{f.label} 必须是整数（收到 {raw}）")
                raw = int(raw)
            if f.type == "choice" and raw not in f.choices:
                raise ValueError(f"{f.label} 只能是 {'/'.join(map(str, f.choices))}（收到 {raw}）")
            out[f.name] = raw
        return out


def _require(cond: bool, msg: str):
    if not cond:
        raise ValueError(msg)


def _valid_ipv4(value: str) -> bool:
    import ipaddress
    try:
        ipaddress.IPv4Address(value)
        return True
    except ValueError:
        return False


# ── 各厂商渲染器（每个意图一个 dict）─────────────────────────────────
# 约定：命令列表按配置顺序返回；不做回滚（回滚由"反向意图"完成，见 README）。

def _vlan_batch(ids: list[str]) -> str:
    return " ".join(ids)


def _mask_to_prefix(mask: str) -> int:
    import ipaddress
    return bin(int(ipaddress.IPv4Address(mask))).count("1")


def _iface_cmd(vendor: str, intf: str) -> str:
    """把用户写的接口名规范化（容忍 GE0/0/1 这类简写）。"""
    def expand(name: str) -> str:
        m = re.match(r"^(Gig|Gi|GE)(\d.*)$", name, re.I)
        if m:
            return "GigabitEthernet" + m.group(2)
        m = re.match(r"^XGE(\d.*)$", name, re.I)
        if m:
            return "XGigabitEthernet" + m.group(1)
        return name
    if vendor == "huawei":
        return intf if re.match(r"^(GigabitEthernet|XGigabitEthernet|Eth-Trunk|10GE|25GE|40GE|100GE)", intf, re.I) \
            else expand(intf)
    if vendor == "cisco":
        return expand(intf)
    if vendor == "h3c":
        return intf if re.match(r"^(Gig|Ten|GE|XGE|Twenty)", intf, re.I) else expand(intf)
    return intf


INTENTS: dict[str, dict] = {
    # ────────────────────────── VLAN 部署 ──────────────────────────
    "vlan_deploy": {
        "spec": IntentSpec("vlan_deploy", "VLAN 部署",
                           "批量创建 VLAN 并写入描述（可同时下发给多台设备）",
                           [FieldSpec("vlans", "VLAN 列表", hint="逗号分隔，如 10,20,30"),
                            FieldSpec("description", "VLAN 描述", required=False, default="Users")]),
        "render": {
            "huawei": lambda p, dev: (
                ["vlan batch " + _vlan_batch(p["_ids"])]
                + [c for v in p["_ids"] for c in (f"vlan {v}", f" description {p['description']}")]
            ),
            "h3c": lambda p, dev: (
                [c for v in p["_ids"] for c in (f"vlan {v}", f" description {p['description']}")]),
            "cisco": lambda p, dev: (
                [c for v in p["_ids"] for c in (f"vlan {v}", f" name {p['description']}-{v}")]),
            "ruijie": lambda p, dev: (
                [c for v in p["_ids"] for c in (f"vlan {v}", f" name {p['description']}-{v}")]),
            "mikrotik": lambda p, dev: (
                [f"/interface vlan add vlan-id={v} name=vlan{v} comment={p['description']}-{v}"
                 for v in p["_ids"]]),
            "vyos": lambda p, dev: (
                [f"set interfaces bridge br0 vif {v} description '{p['description']}-{v}'"
                 for v in p["_ids"]]),
        },
    },
    # ────────────────────────── 端口角色 ──────────────────────────
    "port_role": {
        "spec": IntentSpec("port_role", "端口角色",
                           "把端口设为 Access/Trunk：Access 指定 PVID，Trunk 指定放行 VLAN",
                           [FieldSpec("interface", "接口", hint="如 GE0/0/1 或完整名"),
                            FieldSpec("mode", "模式", type="choice", choices=["access", "trunk"]),
                            FieldSpec("vlan", "VLAN（access=PVID；trunk=放行列表）", default="10")]),
        "render": {
            "huawei": lambda p, dev: (
                lambda i, v: ["interface " + i, " port link-type " + p["mode"]]
                + ([" port default vlan " + v] if p["mode"] == "access"
                   else [" port trunk allow-pass vlan " + _vlan_batch(v.split())])
            )(_iface_cmd("huawei", p["interface"]), p["vlan"]),
            "h3c": lambda p, dev: (
                lambda i, v: ["interface " + i, " port link-type " + p["mode"]]
                + ([" port access vlan " + v] if p["mode"] == "access"
                   else [" port trunk permit vlan " + _vlan_batch(v.split())])
            )(_iface_cmd("h3c", p["interface"]), p["vlan"]),
            "cisco": lambda p, dev: (
                lambda i, v: ["interface " + i, " switchport mode " + p["mode"]]
                + ([" switchport access vlan " + v] if p["mode"] == "access"
                   else [" switchport trunk allowed vlan " + ",".join(v.split())])
            )(_iface_cmd("cisco", p["interface"]), p["vlan"]),
            "ruijie": lambda p, dev: (
                lambda i, v: ["interface " + i, " switchport mode " + p["mode"]]
                + ([" switchport access vlan " + v] if p["mode"] == "access"
                   else [" switchport trunk allowed vlan " + ",".join(v.split())])
            )(_iface_cmd("cisco", p["interface"]), p["vlan"]),
        },
    },
    # ────────────────────────── BGP 邻居 ──────────────────────────
    "bgp_neighbor": {
        "spec": IntentSpec("bgp_neighbor", "BGP 邻居",
                           "在指定 AS 中声明邻居并激活 IPv4 单播地址族",
                           [FieldSpec("local_as", "本端 AS", type="int"),
                            FieldSpec("router_id", "Router-ID"),
                            FieldSpec("neighbor_ip", "邻居地址"),
                            FieldSpec("remote_as", "对端 AS", type="int")]),
        "render": {
            "huawei": lambda p, dev: [
                f"bgp {p['local_as']}",
                f" router-id {p['router_id']}",
                f" peer {p['neighbor_ip']} as-number {p['remote_as']}",
                " #",
                " ipv4-family unicast",
                f"  peer {p['neighbor_ip']} enable",
            ],
            "h3c": lambda p, dev: [
                f"bgp {p['local_as']}",
                f" router-id {p['router_id']}",
                f" peer {p['neighbor_ip']} as-number {p['remote_as']}",
                " address-family ipv4 unicast",
                f"  peer {p['neighbor_ip']} enable",
            ],
            "cisco": lambda p, dev: [
                "router bgp " + str(p["local_as"]),
                " bgp router-id " + str(p["router_id"]),
                " neighbor " + p["neighbor_ip"] + " remote-as " + str(p["remote_as"]),
                " address-family ipv4",
                "  neighbor " + p["neighbor_ip"] + " activate",
            ],
            "ruijie": lambda p, dev: [
                "router bgp " + str(p["local_as"]),
                " bgp router-id " + str(p["router_id"]),
                " neighbor " + p["neighbor_ip"] + " remote-as " + str(p["remote_as"]),
                " address-family ipv4",
                "  neighbor " + p["neighbor_ip"] + " activate",
            ],
            "vyos": lambda p, dev: [
                f"set protocols bgp system-as {p['local_as']}",
                f"set protocols bgp parameters router-id {p['router_id']}",
                f"set protocols bgp neighbor {p['neighbor_ip']} remote-as {p['remote_as']}",
                "set protocols bgp address-family ipv4-unicast network 192.0.2.0/24",
            ],
        },
    },
    # ────────────────────────── 静态路由 ──────────────────────────
    "static_route": {
        "spec": IntentSpec("static_route", "静态路由",
                           "下发一条静态路由（可选优先级做浮动备份）",
                           [FieldSpec("destination", "目的网段"),
                            FieldSpec("mask", "掩码", default="255.255.255.0"),
                            FieldSpec("nexthop", "下一跳"),
                            FieldSpec("preference", "优先级(1-255)", type="int", required=False, default="60")]),
        "render": {
            "huawei": lambda p, dev: [f"ip route-static {p['destination']} {p['mask']} {p['nexthop']} preference {p['preference']}"],
            "h3c": lambda p, dev: [f"ip route-static {p['destination']} {p['mask']} {p['nexthop']} preference {p['preference']}"],
            "cisco": lambda p, dev: [f"ip route {p['destination']} {p['mask']} {p['nexthop']} {p['preference']}"],
            "ruijie": lambda p, dev: [f"ip route {p['destination']} {p['mask']} {p['nexthop']} {p['preference']}"],
            "mikrotik": lambda p, dev: [
                f"/ip route add dst-address={p['destination']}/{_mask_to_prefix(p['mask'])} "
                f"gateway={p['nexthop']} comment=static"
            ],
            "vyos": lambda p, dev: [
                f"set protocols static route {p['destination']}/{_mask_to_prefix(p['mask'])} "
                f"next-hop {p['nexthop']}",
                f"set protocols static route {p['destination']}/{_mask_to_prefix(p['mask'])} "
                f"distance {p['preference']}",
            ],
        },
    },
    # ────────────────────────── 管理基线 ──────────────────────────
    "mgmt_baseline": {
        "spec": IntentSpec("mgmt_baseline", "管理基线（NTP/Syslog）",
                           "统一下发 NTP 服务器、Syslog 服务器与时区",
                           [FieldSpec("ntp_server", "NTP 服务器"),
                            FieldSpec("syslog_server", "Syslog 服务器")]),
        "render": {
            "huawei": lambda p, dev: [f"ntp-service unicast-server {p['ntp_server']}",
                                      f"info-center loghost {p['syslog_server']}"],
            "h3c": lambda p, dev: [f"ntp-service unicast-server {p['ntp_server']}",
                                   f"info-center loghost {p['syslog_server']}"],
            "cisco": lambda p, dev: [f"ntp server {p['ntp_server']}",
                                     f"logging host {p['syslog_server']}"],
            "ruijie": lambda p, dev: [f"ntp server {p['ntp_server']}",
                                      f"logging host {p['syslog_server']}"],
            "mikrotik": lambda p, dev: [
                "/system ntp client set enabled=yes servers=" + p["ntp_server"],
                "/system logging action add name=to-syslog target=remote remote=" + p["syslog_server"],
                "/system logging add topics=info action=to-syslog",
            ],
            "vyos": lambda p, dev: [
                f"set system ntp server {p['ntp_server']}",
                f"set system syslog host {p['syslog_server']} facility all level info",
            ],
        },
    },
}


def list_intents() -> list[dict]:
    """北向目录：意图类型 + 表单字段定义（REST/GUI 共用）。"""
    out = []
    for key, item in INTENTS.items():
        spec: IntentSpec = item["spec"]
        out.append({
            "key": key, "title": spec.title, "desc": spec.desc,
            "fields": [f.__dict__ for f in spec.fields],
        })
    return out


def render_intent(intent_key: str, intent: dict, vendor: str) -> list[str]:
    """把意图渲染成某厂商的命令序列（纯函数；渲染前先做参数校验）。"""
    item = INTENTS.get(intent_key)
    if not item:
        raise ValueError(f"未知意图类型: {intent_key}")
    spec: IntentSpec = item["spec"]
    params = spec.validate(intent)
    renderer = item["render"].get(vendor)
    if not renderer:
        raise ValueError(f"意图 {spec.title} 暂不支持厂商 {vendor}（可选: "
                         f"{'/'.join(item['render'].keys())}）")
    # VLAN 列表参数规范化（供渲染器复用）
    if intent_key == "vlan_deploy":
        ids = [v.strip() for v in re.split(r"[,\s，、]+", params["vlans"]) if v.strip()]
        _require(all(VLAN_RE.match(v) for v in ids), f"VLAN 列表非法: {params['vlans']}")
        params["_ids"] = ids
    if "neighbor_ip" in params:
        _require(_valid_ipv4(params["neighbor_ip"]), f"邻居地址非法: {params['neighbor_ip']}")
    if "router_id" in params:
        _require(_valid_ipv4(params["router_id"]), f"Router-ID 非法: {params['router_id']}")
    if "nexthop" in params:
        _require(_valid_ipv4(params["nexthop"]), f"下一跳非法: {params['nexthop']}")
    if "ntp_server" in params:
        _require(_valid_ipv4(params["ntp_server"]), f"NTP 服务器非法: {params['ntp_server']}")
    if "syslog_server" in params:
        _require(_valid_ipv4(params["syslog_server"]), f"Syslog 服务器非法: {params['syslog_server']}")
    cmds = renderer(params, None)
    return [str(c).strip() for c in cmds if str(c).strip() and not str(c).strip().startswith("#")]
