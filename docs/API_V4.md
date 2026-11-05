# NetWright REST API v4（契约冻结）

> **v4.0 起，本文件的路径/字段视为稳定契约**：删除或改名字段必须升主版本并在
> CHANGELOG 写迁移方式；只新增字段不升版本。
> `/api/v4/*` 与 `/api/v2/*` **完全等价**（v2 为兼容保留），新代码请用 v4。

## 通用约定

- 监听 `127.0.0.1:8899`（设置页可改），仅本机可访问
- 认证：`Authorization: Bearer <token>` 或 `X-API-Token: <token>`
  - 只读 token 只能 `GET`，写操作返回 `403`
  - 缺失/无效 token 返回 `401`
  - `/api/v4/health` 无需认证（探活）
- 返回体：成功 `{"ok": true, ...}`，失败 `{"ok": false, "message": "人话原因"}`
- 所有拒绝（含 401/403）都写一条审计：IP + token 标签

## 只读

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/v4/health` | 探活（公开） |
| GET | `/api/v4/selfcheck` | 环境自检：`healthy/summary/checks` |
| GET | `/api/v4/snapshot` | 控制器快照（图统计/策略/运行数） |
| GET | `/api/v4/topology` | 节点与边 |
| GET | `/api/v4/events?limit=` | 事件流 |
| GET | `/api/v4/policies` | 最近编译的策略 |
| GET | `/api/v4/intents` | 意图运行列表 |
| GET | `/api/v4/intents/runs` | 运行档案（含状态/反向命令） |
| GET | `/api/v4/southbound` | 南向能力矩阵 |
| GET | `/api/v4/timeline?limit=` | 事件+快照+意图 时间线 |
| GET | `/api/v4/sources` | 事件源状态（syslog/trap） |
| GET | `/api/v4/backups?device_hosts=` | 备份快照列表 |
| GET | `/api/v4/backups/diff?device_host=&old=&new=` | 两份快照 diff |
| GET | `/api/v4/backups/live-diff?device_host=` | 现网与最新快照 diff |
| GET | `/api/v4/catalog` | 意图目录定义 |
| GET | `/api/v4/tasks` | 异步任务列表（最近 50） |
| GET | `/api/v4/tasks/{id}` | 单个任务状态 |

## 写操作

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/api/v4/backups` | 触发备份（`device_hosts` 可限定） |
| POST | `/api/v4/compliance/scan` | 合规扫描（`configs` 或 `device_hosts`） |
| POST | `/api/v4/catalog/plan` | 目录意图生成命令（`key/vendor/params`） |
| POST | `/api/v4/topology/path` | 路径追踪（`src/dst/avoid`） |
| POST | `/api/v4/topology/sync` | 用清单刷新拓扑 |
| POST | `/api/v4/health/snmp` | SNMP 健康采样（`host/community/timeout`） |
| POST | `/api/v4/openflow/validate` | flow_mod 编译校验（不下发） |
| POST | `/api/v4/policies/compile` | 意图编译（dry-run） |
| POST | `/api/v4/intents/...` | 生命周期动作（plan/deploy/verify/rollback） |
| POST | `/api/v4/sources/start` | 启动 syslog/trap 监听 |
| POST | `/api/v4/sources/stop` | 停止监听 |

## 示例

```bash
TOKEN=$(python -c "import json;print(json.load(open('netwright_settings.json'))['api_token'])")
curl -s -H "X-API-Token: $TOKEN" http://127.0.0.1:8899/api/v4/selfcheck
curl -s -H "Authorization: Bearer $TOKEN" \
     -X POST http://127.0.0.1:8899/api/v4/compliance/scan \
     -d '{"device_hosts":["192.0.2.1"]}' -H "Content-Type: application/json"
```

## 兼容性政策

| 变更 | 是否需要升主版本 |
|---|---|
| 新增端点 / 新增返回字段 | 否 |
| 改字段名 / 删字段 / 改状态码含义 | **是**（v5） |
| 改认证方式 | 是 |
| 改默认端口 | 否（但需在 CHANGELOG 标注） |

v2 路径在 v4 周期内保持可用；计划在 v5 移除。
