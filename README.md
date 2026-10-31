# NetForge — 网络工程师工作台

<div align="center">
<img src="assets/logo.png" width="96" alt="NetForge" />

**一个独立、完整的网络工程师平台**：设备清单、SSH 批量巡检、配置生成、日常工具，全部长在同一个程序里。

`设备清单中心` · `SSH 批量巡检 + 报告` · `配置生成` · `子网计算/VLSM` · `端口扫描` · `在线检测` · `命令速查`
</div>

---

## 定位

NetForge **不是启动器，也不依赖任何外部工具**——它是一个自包含的单机平台：

- 一份**设备清单**（集中管理地址/厂商/凭据，密码经 Windows DPAPI 加密落盘）是所有模块的共同底座；
- **巡检**、**配置生成** 直接读这份清单；
- 常用小工具（子网计算、端口扫描、在线检测、命令速查、密码生成）随手可用；
- 单文件 exe，双击即用，配置数据落在 exe 同目录。

## 功能

### 🗂 设备清单中心
集中维护主机 / 端口 / 厂商 / 账号密码 / 备注。密码用 **Windows DPAPI**（当前用户）加密存储，
界面打码显示，导出 CSV 时也经同一通道还原。支持 CSV 批量导入（列自动映射、重复跳过）。

### 🔎 SSH 批量巡检
- 内置 **8 套巡检方案**，覆盖与模板库同级的无 SDN 控制器高级场景：
  - **标准巡检** / **硬件健康**（光功率·电源·风扇·温度）/ **链路与拓扑**（STP·邻居·MAC）/ **安全基线**（SSH·ACL·SNMP）
  - **VXLAN+EVPN**（VNI/隧道/NVE/EVPN 邻居/MAC 路由）· **MPLS/SR 骨干**（LDP/LSP/VPNv4/SR 转发表）
    · **堆叠与M-LAG**（CSS/IRF/StackWise、M-LAG/DRNI/vPC/VSU）· **RoCEv2 无损**（PFC/ECN/WRED/ETS）
  - 方案没有某厂商命令集时自动跳过该设备并在状态栏提示；
- 网络设备走交互 shell 自动关分页，Linux 走 exec 通道；每台设备独立会话、跑完即断；
- **异常自动标记**：CPU/内存过高、接口错包、电源风扇故障、光功率 < -20dBm、温度超标、Linux 失败服务等；
- 结果分级（OK / WARNING / FAILED / UNREACHABLE），一键导出**HTML 报告**（含逐命令原始输出，已做转义）。

### 🛠 配置生成
- 内置 **92 个多厂商 CLI 模板**（华为 VRP / 新华三 Comware / 思科 IOS-XE·NX-OS），覆盖无 SDN 控制器环境下的高级网络手工部署：
  - **数据中心**：VXLAN+BGP EVPN 分布式网关（手工 VTEP）、M-LAG/DRNI/vPC 双活网关、CloudEngine 数据中心基线（星河 AI Fabric 准备层）、**RoCEv2 无损**（PFC+ECN+DSCP 映射）、SR-MPLS 骨干（IS-IS SRGB+Prefix-SID）
  - **园区**：MSTP 多实例、VRRP/HSRP、堆叠（CSS/IRF/StackWise）、DHCP、ACL、MQC/QoS
  - **广域与骨干**：MPLS L3VPN（PE-CE）、BGP、IS-IS、BFD 联动、GRE over IPsec、NAT、静态路由+浮动备份
  - **基础与治理**：IPv6 双栈/OSPFv3、组播 PIM-SM、二层安全（端口安全/DHCP Snooping/802.1X）、路由策略、流量采集 NetFlow、端口镜像、管理面加固
- 设备参数表（CSV，首行即变量名）× 模板 → 批量 .cfg；
- **零残留校验**：变量缺失或占位符渲染不出就直接报错，绝不生成含 `{{占位符}}` 的坏配置；
- 可从设备清单一键生成参数表骨架。

### 🧰 工具箱
| 工具 | 能力 |
|---|---|
| 子网计算 | CIDR / 点分掩码、网络/广播/可用范围、二进制掩码、**VLSM 按主机数划分** |
| 端口扫描 | TCP connect 并发（≤500 线程）、端口段混合描述、常用端口服务对照 |
| 在线检测 | ping 扫描（单 IP / 区间 / 末八位简写 `x.x.x.10-12` / CIDR）、延迟统计 |
| 密码生成 | 长度与字符集可调，SystemRandom 强随机 |

### 📖 命令速查
场景 × 厂商 CLI 备忘（接口/VLAN、链路故障、路由协议、安全、DHCP、常用端口），即时过滤、双击复制。

## 运行 / 打包

```bash
pip install paramiko            # 唯一依赖（SSH 巡检）；不装也能用其余模块
python netforge.py              # Python 3.10+

pip install pyinstaller pillow
pyinstaller --onefile --name NetForge --icon assets/icon.ico --add-data "assets;assets" --add-data "templates;templates" netforge.py
```

## 测试

```bash
python -m pytest tests/ -v      # 29 项：凭据加密 / 清单 / 生成引擎 / 巡检规则 / 网络计算
```

## 数据与安全

- 设备数据：`netforge_devices.json`（exe 同目录），密码 DPAPI 加密——**换电脑/换用户无法解密**，属预期行为；
- 巡检报告与生成的配置保存在你选择的目录，可能包含敏感信息，请妥善保管；
- SSH 巡检与端口扫描请只用于**自己管理或获得授权的网络**。

---

MIT License · NetForge 与 [NADT](https://github.com/Yata-Datacom/NADT-Network-Automation-Deployment-Tool)、
[Network Inspection Studio](https://github.com/Yata-Datacom/Network-Device-Server-Inspection-Tool-GUI-Edition)、
[Traffic Studio](https://github.com/Yata-Datacom/Traffic-Load-Tester---Gateway-Stress-Tool)
同属 [Yata-Datacom](https://github.com/Yata-Datacom) 网络工具家族（配置模板库格式互通）。
