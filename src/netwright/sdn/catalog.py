"""catalog.py — 意图目录（D）：把日常变更做成参数化、可预演的条目。

每个条目只声明"要做什么"，命令生成按厂商分派；执行仍走既有
``policy → lifecycle → reverse`` 链路（预演/下发/校验/回滚），本模块不发网络请求。

设计原则：
  * 缺必填参数 → 抛 ``ValueError``（不猜默认值）；
  * 未知厂商 → 抛 ``ValueError``（宁报错不生成错命令）；
  * 每个条目都给出 ``reverse``（能安全回滚时）与 ``risk``，供生命周期判断。
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Param:
    name: str
    label: str
    required: bool = True
    default: str = ""


@dataclass(frozen=True)
class CatalogEntry:
    key: str
    title: str
    desc: str
    risk: str
    params: tuple[Param, ...]

    def to_dict(self) -> dict:
        return {"key": self.key, "title": self.title, "desc": self.desc,
                "risk": self.risk,
                "params": [{"name": p.name, "label": p.label,
                            "required": p.required, "default": p.default}
                           for p in self.params]}


CATALOG: tuple[CatalogEntry, ...] = (
    CatalogEntry("vlan_add", "新增 VLAN", "创建 VLAN 并可选命名", "low",
                 (Param("vlan_id", "VLAN ID"), Param("name", "名称", required=False))),
    CatalogEntry("port_desc", "修改端口描述", "给接口写描述，便于台账对齐", "low",
                 (Param("interface", "接口"), Param("description", "描述"))),
    CatalogEntry("port_toggle", "开 / 关端口", "shutdown 或 undo shutdown", "medium",
                 (Param("interface", "接口"),
                  Param("state", "状态（up/down）", required=False, default="down"))),
    CatalogEntry("lacp", "链路聚合", "把两个物理口加入聚合组", "medium",
                 (Param("interfaces", "成员接口（逗号分隔）"),
                  Param("group", "聚合组号"))),
    CatalogEntry("acl_allow", "ACL 放行", "放行源到目的（扩展 ACL）", "high",
                 (Param("acl_id", "ACL 号"), Param("src", "源网段"),
                  Param("dst", "目的网段"))),
)

ENTRIES = {entry.key: entry for entry in CATALOG}

_HUAWEI = "huawei"
_CISCO = "cisco"


def _check(entry: CatalogEntry, params: dict) -> dict:
    out = {}
    for param in entry.params:
        value = str(params.get(param.name, param.default) or "").strip()
        if param.required and not value:
            raise ValueError(f"{entry.title}：缺少必填参数 {param.label}（{param.name}）")
        out[param.name] = value
    if "vlan_id" in out:
        vlan = int(out["vlan_id"])
        if not (1 <= vlan <= 4094):
            raise ValueError(f"VLAN ID 越界：{vlan}（1-4094）")
        out["vlan_id"] = str(vlan)
    if "state" in out:
        state = out["state"].lower()
        if state not in ("up", "down"):
            raise ValueError(f"state 只能是 up/down（收到 {state}）")
        out["state"] = state
    return out


def build_commands(key: str, params: dict, vendor: str) -> dict:
    """生成命令 + 反向命令。返回 {"commands": [...], "reverse": [...], "risk": str}。"""
    entry = ENTRIES.get(key)
    if entry is None:
        raise ValueError(f"未知意图：{key}（可用：{', '.join(ENTRIES)}）")
    values = _check(entry, params or {})
    vendor = (vendor or _HUAWEI).lower()
    if vendor not in (_HUAWEI, _CISCO, "h3c", "ruijie"):
        raise ValueError(f"不支持的厂商：{vendor}")
    huawei_like = vendor in (_HUAWEI, "h3c")

    if key == "vlan_add":
        name = values["name"]
        if huawei_like:
            commands = [f"vlan {values['vlan_id']}"]
            if name:
                commands.append(f" name {name}")
            commands.append("quit")
        else:
            commands = [f"vlan {values['vlan_id']}"]
            if name:
                commands.append(f" name {name}")
            commands.append("exit")
        reverse = [f"undo vlan {values['vlan_id']}" if huawei_like
                   else f"no vlan {values['vlan_id']}"]
        return {"commands": commands, "reverse": reverse, "risk": entry.risk}

    if key == "port_desc":
        interface = values["interface"]
        desc = values["description"]
        commands = [f"interface {interface}", f" description {desc}",
                    "quit" if huawei_like else "exit"]
        # 描述旧值未知，回滚只能"清空描述"——这不算安全回滚，交给生命周期判 blocked
        reverse = []
        return {"commands": commands, "reverse": reverse, "risk": entry.risk}

    if key == "port_toggle":
        interface = values["interface"]
        if huawei_like:
            action = "shutdown" if values["state"] == "down" else "undo shutdown"
        else:
            action = "shutdown" if values["state"] == "down" else "no shutdown"
        commands = [f"interface {interface}", f" {action}",
                    "quit" if huawei_like else "exit"]
        back = "undo shutdown" if huawei_like else "no shutdown"
        reverse = [f"interface {interface}", f" {back}",
                   "quit" if huawei_like else "exit"]
        return {"commands": commands, "reverse": reverse, "risk": entry.risk}

    if key == "lacp":
        members = [m.strip() for m in values["interfaces"].split(",") if m.strip()]
        if not members:
            raise ValueError("链路聚合：成员接口不能为空")
        group = values["group"]
        commands = []
        for member in members:
            if huawei_like:
                commands += [f"interface {member}", f" eth-trunk {group}", "quit"]
            else:
                commands += [f"interface {member}", f" channel-group {group} mode active",
                             "exit"]
        reverse = []
        return {"commands": commands, "reverse": reverse, "risk": entry.risk}

    if key == "acl_allow":
        acl_id = values["acl_id"]
        src, dst = values["src"], values["dst"]
        if huawei_like:
            commands = [f"acl number {acl_id}", f" rule permit ip source {src} destination {dst}",
                        "quit"]
            reverse = [f"undo acl {acl_id}"]
        else:
            commands = [f"ip access-list extended {acl_id}",
                        f" permit ip {src} {dst}", "exit"]
            reverse = [f"no ip access-list extended {acl_id}"]
        return {"commands": commands, "reverse": reverse, "risk": entry.risk}

    raise ValueError(f"意图 {key} 未实现命令生成")      # 理论上不可达


def describe() -> list[dict]:
    return [entry.to_dict() for entry in CATALOG]
