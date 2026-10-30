# NetForge — 网络工程师工作台

<div align="center">
<img src="assets/logo.png" width="96" alt="NetForge" />

**一个轻量的网络工程师平台壳**：把你手头的工具收进一个窗口，再补上日常最高频的小工具。

`子网计算` · `端口扫描` · `在线检测` · `命令速查` · `模块启动器`
</div>

---

## 它解决什么

网络工程师的桌面上往往同时有四五个工具——NETCONF 管理、ZTP 开局、批量巡检、网关压测——
每个都要单独找图标、单独记入口。NetForge 做两件事：

1. **收纳**：自动发现同级目录的 NetPilot / NADT / Inspection Studio / Traffic Studio（exe 或源码入口），一键启动；
2. **补缺**：内置一批开箱即用的小工具，覆盖日常最高频的"随手一查"场景。

## 内置工具

| 模块 | 能力 |
|---|---|
| **子网计算** | CIDR / 点分掩码换算、网络/广播/可用范围、二进制掩码、地址类别与私网公网判定、**VLSM 按主机数划分** |
| **端口扫描** | TCP connect 并发探测（最高 500 线程）、端口段/混合描述解析、常用端口服务对照 |
| **在线检测** | 网段 ping 扫描（单 IP / 区间 / 末八位简写 `192.0.2.10-12` / CIDR）、存活主机、延迟、主机名反查 |
| **命令速查** | 场景 × 厂商 CLI 备忘（接口/VLAN、链路故障、路由协议、安全、DHCP、常用端口），即时过滤、双击复制 |

## 外部模块发现

把 `NetForge.exe` 放在如下同级目录结构中即可自动发现（也支持源码运行）：

```
coding/
├── NetForge/            ← 本工具
├── netconf-web/         ← NetPilot（NETCONF 控制台，app.py）
├── NADT/                ← ZTP 开局（nadt2.py / NADT 2.0.exe）
├── network_A/           ← 巡检（net_inspect_v6.py）
└── test_A/              ← 网关压测（TrafficTest.exe）
```

想加自己的工具？在 NetForge 同目录放 `netforge_modules.json`：

```json
{
  "modules": [
    {"name": "SecureCRT", "path": "C:/Program Files/VanDyke/SecureCRT.exe", "desc": "终端"}
  ]
}
```

## 运行 / 打包

```bash
python netforge.py                     # 需要 Python 3.10+（纯标准库）

pip install pyinstaller pillow
python tools/make_icon.py              # 重新生成图标（已预生成可跳过）
pyinstaller --onefile --name NetForge --icon assets/icon.ico --add-data "assets;assets" netforge.py
```

## 测试

```bash
python -m pytest tests/ -v             # 17 项：子网计算 / 端口与目标解析 / 模块发现
```

## 安全提示

端口扫描与在线检测请只用于**自己管理或获得授权的网络**。

---

MIT License · NetForge 是 [Yata-Datacom](https://github.com/Yata-Datacom) 网络工具家族的一员：
[NetPilot](https://github.com/) · [NADT](https://github.com/Yata-Datacom/NADT-Network-Automation-Deployment-Tool) ·
[Network Inspection Studio](https://github.com/Yata-Datacom/Network-Device-Server-Inspection-Tool-GUI-Edition) ·
[Traffic Studio](https://github.com/Yata-Datacom/Traffic-Load-Tester---Gateway-Stress-Tool)
