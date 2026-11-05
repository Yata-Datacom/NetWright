# 升级到 v4.0

## 会不会丢数据？

**不会。** 升级只需要替换程序文件，设置/设备清单/审计/备份都在程序同目录：

```
NetWright.exe
netwright_settings.json      ← 设置
netwright_devices.json       ← 设备台账
netwright_controller.json    ← 策略/运行档案
backups/                     ← 配置快照
```

onedir 版替换整个 `NetWright\` 目录即可；单文件版替换 `NetWright.exe` 即可。

## 首次启动做了什么

v4 引入 `schema_version`（当前 = 4）。老配置（v3 及更早）首次启动时：

1. 先把 `netwright_settings.json` 备份为
   `netwright_settings.json.v3.<时间戳>.bak`（同目录）
2. 补齐 v4 新键：`drift_daily`、`drift_hours`、`api_tokens`、`schema_version`
3. 历史键改名：`theme` → `theme_mode`
4. **不删除**任何不认识的键（未来版本写入的键会原样保留）
5. 落盘；迁移失败不会阻止程序启动

想确认迁移结果：`tools/diagnose.py` 或 `GET /api/v4/selfcheck`，
再打开设置页看各项是否正常。

## 行为变化（需要留意）

| 项 | v3 | v4 |
|---|---|---|
| REST 版本前缀 | `/api/v2/*` | `/api/v4/*`（v2 仍可用） |
| 配置结构 | 无版本号 | `schema_version: 4`，启动自动迁移 |
| 合规规则 | 内置 8 条 | 随包 `templates/compliance.json`，可直接改 |
| 启动速度 | 单文件 ~2.4 s / 目录版 0.6 s | 不变（v3.29 起） |

## 回退到 v3

1. 关掉程序
2. 用 v3 的 exe 覆盖
3. 用 `netwright_settings.json.v3.*.bak` 换回设置文件（v4 写入的新键对老版本无害，
   但换回更保险）
4. 备份目录与台账格式未变，不需要处理

## 需要新依赖吗？

不需要。运行时依赖仍只有 `paramiko`（可选 `ncclient` 用于 NETCONF、`os-ken` 用于
OpenFlow 实传输）。`tools/diagnose.py` 会告诉你缺什么、怎么装。

## 已知限制

- 截图仍为 v3.9 版本；新页面截图需要交互式桌面
- 无多用户/RBAC；REST 仅监听回环地址
- 发布流水线（tag → Release）尚未启用
