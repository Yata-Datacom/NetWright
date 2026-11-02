# 架构与取舍（NetWright 控制器内核）

> 这份文档回答两个问题：**我们借鉴了谁**、**我们刻意不做什么**。
> 目标不是"再造一个 OpenDaylight"，而是把控制器里真正有用的那几层，
> 做成一个单机、可读、能跑在工程师笔记本上的工具。

---

## 1. 借鉴矩阵

| 来源 | 借了什么 | 没借 / 改造了什么 |
|---|---|---|
| **OpenDaylight** | 意图 → 策略的分层；南向插件化（我们做 `SouthboundAdapter` 注册表）；北向 REST 语义化 | 不引入 OSGi/Java 运行时；不做集群与 MD-SAL 数据树 |
| **ONOS** | 意图**状态机**（我们：compiled → planned → approved → deploying → deployed → verified → rolled_back）；"意图可撤销"的思路 | 不做分布式一致性；不做 intent 编译器多级（我们只有一层） |
| **OpenStack Neutron** | 资源模型带 **revision / 状态** 的意识；`dry-run` 先于 `apply` 的操作习惯 | 不做多租户与配额 |
| **NetBox** | **设备清单即唯一事实来源（SoT）**；台账链路入图 | 不做 IPAM/DCIM 全量建模 |
| **Cisco DNA Center** | **Assurance（保障）** 视角：巡检 + 事件 + 健康分，而不是只做配置下发 | 不接云端；健康分只用本地规则 |
| **Oxidized / RANCID** | 配置备份与差异的意识（当前用审计 + 策略快照代替） | 暂未做自动版本库 |
| **Ansible / NAPALM** | 多厂商命令映射 + 幂等下发 | 不引入 YAML playbook 体系 |

一句话：**ODL 的分层 + ONOS 的状态机 + NetBox 的 SoT + DNA 的 assurance**，
装进一个 Python 单文件程序里。

---

## 2. 分层

```
┌──────────────────────────── 北向 ────────────────────────────┐
│  Tkinter 页面（10 个工作区）      REST v1（兼容） + v2（带 token）│
└───────────────────────────────┬──────────────────────────────┘
                                │
┌───────────────────────────────▼──────────────────────────────┐
│ ControllerStore   状态唯一来源：图 / 策略 / 运行档案 / 事件     │
│ EventBus          订阅 + 环形历史 + 严重度                     │
│ IntentLifecycle   编译→预演→下发→校验→回滚（状态机）           │
│ PolicyCompiler + reverse  意图→命令；命令→反向命令             │
└───────────────────────────────┬──────────────────────────────┘
                                │
┌───────────────────────────────▼──────────────────────────────┐
│ SouthboundAdapter 注册表                                     │
│   CLI(SSH/Telnet) ✅   RESTCONF ✅   NETCONF ✅(需 ncclient)   │
│   OpenFlow 1.3 🧱（能力位已声明，flow-mod 未实装）             │
└───────────────────────────────┬──────────────────────────────┘
                                │
┌───────────────────────────────▼──────────────────────────────┐
│ 事件源：syslog(UDP 5140) / SNMPv2c trap(UDP 1162)             │
│   → EventBus → 拓扑增量高亮 + 事件页 + REST /events           │
└──────────────────────────────────────────────────────────────┘
```

---

## 3. 意图生命周期

```
compiled ──plan──▶ planned ──approve──▶ approved ──▶ deploying
                                                   │
                                      ┌────────────┴────────────┐
                                      ▼                         ▼
                                  deployed ──verify──▶ verified  failed
                                      │                         │
                                      ├──rollback──▶ rolled_back │
                                      └──无反向命令──▶ rollback_blocked
```

**两个刻意的设计**：

1. **预演不连设备**：`plan()` 只做静态检查（命令非空、风险、能否回滚）。
   为了"预演"去连生产设备，是把风险当仪式。
2. **回滚要诚实**：反向命令由 `reverse.py` 按意图生成；生成不了就返回
   `rollback_blocked` + 人工处置建议，**绝不猜一条命令**。
   - VLAN 部署 → `undo vlan X`（确定安全）
   - 端口 shutdown → `undo shutdown`（确定安全）
   - 端口 access/trunk 互转、BGP 邻居、管理面基线 → **不可回滚**（原状态未知/影响收敛/可能失联）

---

## 4. 南向矩阵

| 通道 | 状态 | 能做什么 | 依赖 |
|---|---|---|---|
| CLI (SSH/Telnet) | ✅ | 命令下发、配置回读、巡检、发现 | paramiko（Telnet 用标准库） |
| RESTCONF | ✅ | GET/PATCH/POST/DELETE，OpenConfig 接口表 | 标准库 urllib |
| NETCONF | ✅ | get-config / edit-config / commit / discard | `ncclient`（可注入会话，故可离线测试） |
| OpenFlow 1.3 | 🧱 | 能力位、flow 结构约定已定，flow-mod 未实装 | os-ken / ryu |

**约定**：能力没实装就抛 `UnsupportedOperation`，不返回空结果。
控制器最危险的 bug 不是"报错"，而是"以为发下去了"。

---

## 5. 事件源

| 来源 | 端口 | 解析 | 归类 |
|---|---|---|---|
| Syslog | UDP 5140（可改） | RFC3164 / RFC5424 / 裸消息 | link down/up、BGP/OSPF 邻居、配置变更、登录失败、硬件告警 |
| SNMPv2c Trap | UDP 1162（可改） | 自实现 BER（不依赖 pysnmp） | linkDown/linkUp、coldStart/warmStart、认证失败 |

事件 → `EventBus` → 三个消费方：
1. **拓扑页**：节点画琥珀色脉冲圈（最近 90 秒），自动刷新时自然消退；
2. **事件页**：分级着色 + 过滤；
3. **REST `/api/v2/events`**：给外部告警平台拉取。

---

## 6. 安全边界

| 面 | 措施 | 边界（坦白说） |
|---|---|---|
| 凭据 | Windows DPAPI 加密落盘 | 非 Windows 退化为 `plain:` 标记 |
| REST | 仅 127.0.0.1 + Bearer token（`/health` 公开） | 不是公网防护；token 存本地设置文件 |
| 下发 | 必须显式 confirm / approve + 审计 | 不做 RBAC（单机工具定位） |
| SSH hostkey | 默认 AutoAddPolicy | 内网取舍，严格校验请改 `ssh_client.py` |
| 回滚 | 只生成确定安全的反向命令 | 不确定就 blocked，人工接管 |

---

## 7. 明确不做的事

- **不做分布式控制器**（无集群、无一致性协议）——单机工具的价值是"随手可用"；
- **不做完整 YANG 建模**——RESTCONF 走路径透传，够用即可；
- **不做多租户/配额**——面向一个运维团队，不是云平台；
- **不做 OpenFlow 全栈**——等有白盒设备需求再做，避免半成品误导。

---

## 8. 代码地图

| 路径 | 职责 |
|---|---|
| `sdn/events.py` | 事件总线（环形历史/订阅/严重度） |
| `sdn/model.py` | 图模型（节点/端口/链路/统计） |
| `sdn/policy.py` | 意图 → 策略（命令 + 风险） |
| `sdn/reverse.py` | 策略 → 反向命令（能/不能回滚都返回理由） |
| `sdn/lifecycle.py` | 状态机 + 下发/校验/回滚 |
| `sdn/store.py` | 状态仓库 + 事件源生命周期 + 节点闪烁 |
| `sdn/southbound/` | CLI / RESTCONF / NETCONF / OpenFlow 适配器 |
| `sdn/sources/` | syslog / SNMP trap 解析与监听 |
| `sdn/auth.py` | Bearer token |
| `sdn/nbapi.py` | REST v2 路由 |
