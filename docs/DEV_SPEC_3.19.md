# NetWright v3.19+ 开发规格（交给代码模型执行）

> 这份文档的用途：把"还想要什么"翻译成**可执行、可验收**的任务。
> 每条需求都有：目标 / 接口契约 / 验收命令 / 涉及文件 / 禁止事项。
> 读完请先跑基线，再按里程碑顺序做，一次只做一个任务。

---

## 0. 执行约定（给 GLM 的硬规矩）

1. **先读三份文件**：`docs/ARCHITECTURE.md`（分层与取舍）、本文件、`CHANGELOG.md` 最近三个版本。
2. **先跑基线**：`pytest tests/ -q` 必须 225 passed；`ruff check src tests main.py` 必须干净。
   基线不绿就先修基线，不要开新功能。
3. **一次一个任务**，做完提交一次（`feat:` / `fix:`），并在 `CHANGELOG.md` 顶部加条目。
4. **先写失败测试，再写实现**（项目一直是这么做的，`tests/` 里有大量范例）。
5. **不许改公开契约**（改了必须单独开任务并在 CHANGELOG 写迁移方式）：
   - `sdn/southbound/base.py` 的 `SouthboundAdapter` 抽象
   - `sdn/nbapi.py` 已有路由的请求/响应字段
   - `pages/__init__.py` 的 `PAGE_REGISTRY` key（可以新增，不能改名）
   - `sdn/model.py` 的 `NetworkGraph` 公开方法
6. **不许"许愿式编程"**：任何"更智能/更强大"的描述都必须落成一条可断言的测试。
   写不出断言，就说明需求没想清楚，先回来问。
7. **依赖控制**：运行时依赖只允许 `paramiko` 一个；新增依赖必须进
   `pyproject.toml` 的 `[project.optional-dependencies]`，且**不装也不能崩**（用
   `importlib.util.find_spec` 探测，参考 `sdn/southbound/netconf.py`）。
8. **线程模型**：网络/IO 在后台线程；Tk 只在主线程碰。后台线程要更新 UI 一律
   `app.after(0, ...)`，且用 `try/except (RuntimeError, tk.TclError)` 包住。
   （事件页 `_on_event` 是非主线程只置脏标记的范例。）

---

## 1. 现状基线（v3.18.0）

```
src/netwright/
├─ app.py            外壳：顶栏/分组侧栏/主题/自动刷新/快捷键/API token
├─ theme.py          设计令牌（chrome* 外壳、topo* 画布、明暗+4 主色）
├─ widgets.py        PageHeader / SectionCard / StatTile / StatusDot / Tag / Toast / Drawer
├─ demo.py           一键演示数据
├─ lib/              纯逻辑：inventory / inspector / generator / netcalc / portscan /
│                    loopdetect / discovery / history / cheatsheet / errors / secrets /
│                    controller/{intents,deploy,topology,restapi}
├─ sdn/              控制器内核
│  ├─ events.py      事件总线（环形历史/订阅/严重度）
│  ├─ model.py       NetworkGraph（节点/边/统计）
│  ├─ policy.py      意图→策略（命令+风险）
│  ├─ reverse.py     策略→反向命令（能/不能都返回理由）
│  ├─ lifecycle.py   状态机：compiled→planned→approved→deploying→deployed→verified→rolled_back
│  ├─ backup.py      配置快照（去重/diff/prune/漂移）
│  ├─ timeline.py    事件+快照+意图 聚合
│  ├─ auth.py        Bearer token
│  ├─ store.py       ControllerStore（图/策略/运行档案/事件源/备份）
│  ├─ nbapi.py       REST v2 路由
│  ├─ sources/       syslog（RFC3164/5424）、SNMPv2c trap（自实现 BER）
│  └─ southbound/    cli ✅ / restconf ✅ / netconf ✅(ncclient) / openflow 🟡(编码+校验)
└─ pages/            12 个工作区页面
```

已知限制（不要假装它们不存在）：
- OpenFlow 只有编码，没有 TCP 通道（`program_flows` 抛 `UnsupportedOperation`）
- 存量页面（巡检/生成/盘点/工具）还是老布局，只有设备清单/拓扑/概览/事件/设置/时间线是新版
- 无多用户、无 RBAC；REST 只监听 127.0.0.1
- 截图缺失（`docs/screenshots/` 只有 5 张早期图）

---

## 2. 任务清单

### M1（先做，收益最大）

#### R1 列表页统一组件化
**目标**：把存量页面的"表格 + 工具栏 + 空状态"抽成可复用组件，8 个页面视觉/行为一致。
**接口**：
```python
# widgets.py 新增
class DataTable(tk.Frame):
    def __init__(self, master, columns, headings, widths, height=15, selectmode="browse")
    @property tree -> ttk.Treeview
    def set_rows(self, rows: list[tuple], tags_by_row: list[tuple] | None = None) -> None
    def selected_indices(self) -> list[int]
    def preserve_selection(self) -> contextmanager   # 刷新前后保持选中
```
**验收**：
- **TDD 骨架已就绪**：`tests/test_widgets.py`（10 项）当前整文件 skip（基线 225 passed / 1 skipped）。
  实现 `widgets.DataTable` 后必须 `pytest tests/test_widgets.py -q` → **10 passed**，且不得修改断言
- `pytest tests/test_gui_smoke.py -q` 全绿；8 个存量页至少 4 个改用 `DataTable`
- 手动验收：设备清单/巡检/盘点三页在明暗 × 4 主色切换后布局不塌、行高一致

#### R2 时间线联动
**目标**：时间线点一行 → 跳到对应页面并定位（事件→事件页、快照→备份历史、意图→运行档案）。
**接口**：`TimelinePage._open(item)`；`app.show(key)` 已支持；跨页传参用 `app.pending_focus = {key, payload}`。
**验收**：
- `tests/test_gui_smoke.py` 新增：点事件行 → `_active_key == "events"`；点快照行 → 打开 `BackupHistoryDialog`
- 无 payload 时不崩（空/未知类型落回页面首页）

#### R3 配置回滚（危险操作）
**目标**：备份历史里选一份快照 →「恢复到设备」。必须二次确认 + 审计 + 恢复前自动备份当前配置。
**接口**：
```python
# sdn/store.py
def restore_backup(self, device, filename: str, timeout: float = 30.0) -> dict
# 返回 {"ok": bool, "pre_backup": str, "commands": int, "error": str}
```
**验收**：
- 单测：恢复前自动 `backup_device()`；`get_config` 失败时不发任何命令；审计里出现 `config.restore`
- GUI：弹窗必须显示"将覆盖 N 行配置，已自动备份为 <文件名>"
- **禁止**在恢复失败时重试第二次（半途状态更危险），只报告

### M2（控制器能力）

#### R4 意图 → 流表（复用现有意图层）
**目标**：`vlan_deploy` / ACL 类意图除了 CLI 命令，还能编译成 OpenFlow flow 列表。
**接口**：
```python
# sdn/policy.py: Policy 增加 flows: tuple = ()
# sdn/openflow_plan.py: flows_for(intent_key, params, vendor) -> list[dict]
```
**验收**：
- 单测：`vlan_deploy` 生成 ≥2 条 flow（ingress 打 VLAN、egress 去 VLAN），能通过 `FlowEntry` 校验
- REST：`POST /api/v2/intents/plan` 的返回里带 `flows`；不支持的意图返回 `flows=[]` 且不报错

#### R5 os-ken 集成（可选依赖）
**目标**：装了 os-ken 时能做真实 OpenFlow 通道；没装时保持现状。
**接口**：`sdn/southbound/openflow_transport.py`：`class OsKenTransport`，实现 `connect/send_flow_mod/receive_port_status`
**验收**：
- 未装 os-ken：`OpenFlowAdapter.available() is False`，其余行为不变（现有 11 项测试全绿）
- 装了：`pytest -m openflow_live`（需要 OVS 或 mininet，默认 skip）能跑通 1 条 flow 下发
- **禁止**把 os-ken 加进必装依赖

#### R6 多 token 与审计
**目标**：支持"只读 token"（只能 GET）与"轮换记录"。
**接口**：`TokenAuth` 增加 `tokens: dict[token, {"scope": "read"|"write", "label": str}]`；`nbapi` 写路由校验 scope。
**验收**：只读 token 访问 `POST /api/v2/intents/deploy` → 403；轮换后旧 token 401；审计里能看到每次调用来源（IP + token label）

### M3（体验与交付）

#### R7 巡检治理
**目标**：长任务可取消、并发可配、超时可控。
**验收**：并发 20 台 × 5 条命令的 mock 场景，取消后 2 秒内线程池收尾；UI 上"取消"按钮变灰并可再次开始

#### R8 备份治理
**目标**：按设备设保留份数、导出 zip、目录迁移（设置项）。
**验收**：导出 zip 含 `manifest.json`（设备/时间/sha256）；迁移后旧目录不再写入

#### R9 设置页扩展
**目标**：事件源默认端口、备份目录、日志级别、REST 多 token 管理。
**验收**：改动即时持久化；改备份目录后新快照写入新目录（旧文件不动）

#### R10 发布工程（⏸ 暂缓，用户明确"先不发版"）

> 这一条**现在不要做**。等主体功能补齐、用户明确要发版时再开。
> 届时目标：`git tag` → CI 出 exe + SHA256 + Release；版本号三处一致（CI 已有检查）。
> 验收（届时再启用）：`pyinstaller NetWright.spec --noconfirm` 产物可启动、能读到
> `templates/`（onedir 更稳）；Release 附件含 `NetWright.exe` 与 `SHA256SUMS.txt`。

**当前不要碰**：不要创建 tag、不要改 CI 发布步骤、不要写 Release notes。

---

## 3. 已知的坑（都是这个项目真踩过的，别重踩）

| 坑 | 症状 | 正确做法 |
|---|---|---|
| `bus or EventBus()` | 空总线是 falsy，被悄悄换成新总线，页面收不到事件 | 显式 `bus if bus is not None else EventBus()` |
| 后台线程直接 `widget.after` | 主循环未运行时 `RuntimeError: main thread is not in main loop`，极端情况挂死 | 非主线程只置脏标记，交给自动刷新 |
| `demo.clear()` 只删设备 | 演示链路残留在台账，污染真实拓扑 | 设备 + 相关链路一起清 |
| 事件源字段名不统一 | syslog 用 `device_host`、trap 用 `trap_source`，拓扑不闪 | 匹配时把候选 key 列全 |
| 快照文件名用秒级时间戳 | 上一份被 prune 后复用同名 → 新快照被自己删掉（真丢数据） | 秒 + 同秒自增序号 + `_prune(protect=刚写入的路径)` |
| 依赖 `st_mtime_ns` 排序 | Windows 快速写入时钟抖动，同秒顺序不稳 | 按文件名里的序号排序 |
| Tk 文本控件里塞超大文本 | 巡检详情 3000 行时卡顿 | 截断到 3000 字符并提示"已截断" |
| 直接 `str(exc)` 给用户看 | 用户看到 `AuthenticationException` 一脸懵 | 走 `lib/errors.friendly_error()` |

---

## 4. 每次提交的 Definition of Done

1. `pytest tests/ -q` 全绿（数量只增不减，除非删了重复测试并说明）
2. `ruff check src tests main.py` 无告警
3. 新逻辑有测试；修 bug 有复现测试
4. `CHANGELOG.md` 有本次条目；用户可见变化同步到 `docs/USER_GUIDE.zh-CN.md`
5. 版本号三处一致（`__init__.py` / `pyproject.toml` / CHANGELOG 顶部）
6. 提交信息符合 `feat:` / `fix:` / `docs:` / `perf:` / `refactor:`

## 5. 怎么给 GLM 提需求（避免"许愿"）

❌ 许愿式：
> "把界面做得更现代化，像 ODL 那样，加上流表管理"

✅ 可执行：
> "实现 R4：新增 `sdn/openflow_plan.py: flows_for(intent_key, params, vendor)`，
> vlan_deploy 生成 ingress/egress 两条 flow；`Policy` 增加 `flows` 字段；
> 单测 `tests/test_openflow_plan.py` 断言 2 条 flow 通过 `FlowEntry` 校验且
> `POST /api/v2/intents/plan` 返回带 `flows`；不改现有 REST 字段。"

每条需求至少给三样：**改哪个文件 / 什么接口 / 怎么断言**。
