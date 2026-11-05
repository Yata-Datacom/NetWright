# NetWright 更新说明（v3.29 → v3.36）

> 给同事/客户看的版本摘要。详细逐条记录见 [CHANGELOG.md](../CHANGELOG.md)。

## 一句话

从"能跑的控制器原型"变成"日常能用的网络运维工作台"：
**意图闭环 + 合规/漂移/路径/健康 + 双形态打包（目录版 0.6 秒启动）+ 环境自检**。

## 新增能力

### 意图与控制器
| 能力 | 怎么用 | 版本 |
|---|---|---|
| 意图目录（5 个参数化意图） | 控制器 → 意图目录 → 填参 → 生成命令 / 提交到运行档案 | 3.30 / 3.32 |
| 目录 → 运行档案闭环 | 按每台设备各自厂商生成 Policy，进入 `compiled` 等预演 | 3.33 |
| 路径追踪 | 运维中心填源/目的 → 文字路径；「在拓扑上高亮」画到图上 | 3.30 / 3.32 |
| OpenFlow 传输层（可选） | 装 os-ken 后可下发；未装时能力闸门关闭，不假装成功 | 3.28 |

### 日常运维
| 能力 | 怎么用 | 版本 |
|---|---|---|
| 配置合规检查 | 运维中心 → 选设备/全部 → 得分 + 证据行号；规则可在 `templates/compliance.json` 改 | 3.30 / 3.33 |
| 配置漂移 | 「立即扫描」或勾选「每日自动检查」；有漂移发 `config.drift` 事件 | 3.30 / 3.32 |
| SNMP 健康 | 运维中心 → 选设备 + community → CPU / 内存 / uptime | 3.30 / 3.34 |
| 异步任务 | `GET /api/v2/tasks` 查进度（巡检/备份等长任务） | 3.30 |
| 环境自检 | `tools/diagnose.py` 或 `GET /api/v2/selfcheck` | 3.36 |

### 性能与交付
- **启动**：页面惰性构建（-87% 构建耗时）+ paramiko 按需加载（import 1173→584 ms）
- **打包**：目录版（onedir）暖启动 **0.6 秒**，单文件 19.3 MB（裁掉 7.7 MB AVIF 插件、关闭 UPX）
- **一键出包**：`tools/build_all.ps1` 同时产出两份并打印体积
- **启动基准**：`docs/STARTUP_BENCH.md` 有前后对照数字

## 升级须知

1. **数据位置不变**：设置/清单/审计/备份仍在 exe 同级目录，覆盖 exe 或替换目录即可升级。
2. **模板**：如果之前自己在 exe 旁放过 `templates/`，会优先使用你的那份（可自定义模板不用重新打包）。
3. **合规规则**：首次使用会加载随包的 `templates/compliance.json`；想自定义就改它，改完无需重启。
4. **REST 新接口**（都需 token）：
   `POST /compliance/scan`、`GET /catalog`、`POST /catalog/plan`、`POST /topology/path`、
   `GET /tasks`、`GET /tasks/{id}`、`POST /health/snmp`、`GET /selfcheck`。

## 已知限制

- 截图仍是 v3.9 的旧图（`docs/screenshots/`），新页面未截图
- OpenFlow 需要真实 OVS 才能跑 `-m openflow_live`，未安装环境自动 skip
- 无多用户/RBAC；REST 仅监听 127.0.0.1
- 发布流水线（tag → Release）暂缓，等主体稳定后再开

## 验证方式

```bash
.venv\Scripts\python.exe -m pytest -q      # 390 passed, 2 skipped
.venv\Scripts\python.exe tools\diagnose.py # 8 项环境自检
```
