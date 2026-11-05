# Changelog

本项目遵循 [语义化版本](https://semver.org/lang/zh-CN/) 与
[Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/) 格式。

## [3.32.0] - 2026-11-05

### Added（把 v3.30 能力全部接到界面）
- **控制器 → 意图目录**标签页：选意图（5 个）→ 填参数（必填标 `*`）→ 选厂商 → 生成命令；
  结果显示「命令 / 反向命令（无则说明会被判 rollback_blocked）/ 风险等级」；参数错直接提示，不生成半截命令。
- **拓扑 → 路径高亮**：运维中心点「在拓扑上高亮」后，跳转拓扑页并把路径上的节点描边、边加粗。
- **运维中心 → 自动漂移检查**：勾选「每日自动检查」+ 周期（小时），持久化到设置；
  开启后 60 秒轮询一次、到期才真正扫描，页面销毁时自动停止。

### Fixed
- 漂移扫描后线程回调在窗口已销毁时会抛 Tcl 异常 → 回调与轮询都加了存在性保护。

### Tests
- `tests/test_ops_page.py` 扩到 9 项：拓扑高亮、意图目录生成/校验错误、漂移开关持久化。
- 全量 **376 passed, 2 skipped**；ruff 干净。

## [3.31.0] - 2026-11-05

### Added（运维中心界面入口）
- 新增「系统 / 运维中心」页（`pages/ops.py`），把 v3.30 的三个能力接到界面：
  - **合规检查**：选设备或「检查全部」，结果表列出 设备/得分/级别/规则/证据（含行号），
    汇总平均分与最低分；没有快照时明确提示先做备份。
  - **路径追踪**：填起点/终点（下拉来自拓扑），显示 `A → B（N 跳）` 或具体不可达原因。
  - **配置漂移**：后台线程扫描（不阻塞 UI），有漂移时汇总并逐台发 `config.drift` 事件。
- 页面注册表扩到 13 个；后台线程结果统一回主线程刷新（继续遵守"不跨线程碰 Tk"）。

### Tests
- 新增 `tests/test_ops_page.py`（5 项）：页面构建、合规命中、无快照提示、路径可达/不可达。
- 全量 **372 passed, 2 skipped**；ruff 干净。

## [3.30.0] - 2026-11-05

### Added（运维/控制器能力：A/B/C/D/F/G）
- **A 配置合规检查** `lib/compliance.py`：8 条规则（Telnet/默认团体名/明文口令/HTTP 明文/VTY 无超时/缺 NTP/缺远程日志/缺横幅），命中带行号与证据、100 分制扣分、按严重度排序；REST `POST /api/v2/compliance/scan`（内联配置或按备份扫描）。
- **B 定时漂移巡检** `sdn/schedule.py`：可注入时钟的 `IntervalJob`（到期才跑、失败不中断、记录 last_error）+ `drift_scan()` 只返回有漂移的设备与出错设备。
- **C SNMPv2c 主动采集** `sdn/sources/snmp_client.py`：自实现 BER 编解码的 `snmp_get`，不引入 pysnmp；community 不进日志。
- **D 意图目录** `sdn/catalog.py`：5 个参数化意图（加 VLAN/改描述/开关端口/聚合/ACL 放行），华为/H3C 与 Cisco 命令差异、缺参数/未知厂商直接报错、能安全回滚才给 reverse；REST `GET /api/v2/catalog`、`POST /api/v2/catalog/plan`。
- **F 路径追踪** `sdn/pathtrace.py`：BFS 最短路 + 排除节点 + 人话描述；REST `POST /api/v2/topology/path`。
- **G 异步任务** `sdn/tasks.py`：线程池 + 最近 200 条任务表（不持久化，审计另有日志），`ControllerStore.tasks`；REST `GET /api/v2/tasks`、`GET /api/v2/tasks/{id}`。

### Tests
- 新增 6 个测试文件（合规/目录/漂移/路径/任务/接口）：全量 **367 passed, 2 skipped**；ruff 干净。

### Known
- 这 6 项目前只有后端 + REST，**界面入口尚未接**（下一步：设备清单加「合规检查」、控制器页加「意图目录」、拓扑页加「路径追踪」）。

## [3.29.3] - 2026-11-05

### Added（打包说明与脚本）
- `tools/build_all.ps1`：一条命令出「单文件 + 目录版」两份产物并报告体积/文件数；
  `-NoBuild` 只报告已有产物。兼容 Windows PowerShell 5.1（脚本存为 UTF-8 BOM）。
- README 新增「打包」章节：两产物对照（19.3 MB / 2.4–2.9 s 与 45.7 MB / **0.6 s**）、
  资源与数据目录规则、UPX 关闭原因、AVIF 裁剪说明。

### Tests
- 无代码路径变化；全量 **330 passed, 2 skipped**；ruff 干净。

## [3.29.2] - 2026-11-05

### Changed（体积与绘制）
- **打包裁剪 PIL AVIF 插件**：onefile **24.5 MB → 19.3 MB（-21%）**；界面只需 PNG/ICO 预览，
  AVIF 的 `_avif.pyd` 单文件就占 7.7 MB（未压缩）。
- **拓扑视口裁剪**：放大/平移后画布外的边与节点不再生成 Canvas 元素（此前只按搜索/纳管过滤）。
  100+ 节点时缩放与悬停更顺；边界留 60px 余量避免元素闪断。

### Verified（不属于本次改动，复核结论）
- 巡检已是并发：`inspector.run_batch(workers=20)` 用 ThreadPoolExecutor，且 R7 已支持取消。
- 备份导出 zip 用 `zf.write(entry.path)` 流式写盘，不把整包读进内存。
- onedir 实测：冷启动首轮 2.46 s，**暖启动 0.47–0.59 s**（onefile 2.4–3.2 s）。

### Tests
- 新增 `tests/test_topology_culling.py`（4 项）；全量 **330 passed, 2 skipped**；ruff 干净。

## [3.29.1] - 2026-11-04

### Changed（冷启动）
- **paramiko 改为按需加载**：`lib/__init__` 原来在导入期 `import paramiko`，连带 invoke/cryptography 约 **0.9 s**；改用 `importlib.util.find_spec` 探测，SSH 真正连接时才由 `ssh_client.run_commands` 内部导入。
- 实测：`import netwright.app` **1173 ms → 584 ms（-50%）**；`tools/bench_startup.py` App 构造 368–461 ms。
- onefile exe 双击到窗口 2.6–3.2 s（提取/Tk 初始化占大头），收益主要在源码启动与首屏。

### Tests
- 全量 **326 passed, 2 skipped**；ruff 干净。

## [3.29.0] - 2026-11-02

### Added（R15 从现网反生成基线——必须脱敏）
- **`lib/reverse_template.py`**：`read_config` 的配置文本 → 脱敏候选模板。
  - 所有 IPv4 → `{{ip_N}}`（同址复用同变量）；密码行 → `{{password_N}}`；
    SNMP 团体名 → `{{snmp_community_N}}`；
  - 网掩码与 0.0.0.0 是配置结构不是凭据，保留原样（文档写明）；
  - `find_leaks(template, original)` 自检残留——**leaks 非空即拒绝入库**；
  - 变量名是机械编号，注释明确"人工裁剪改名后再入库"，不做魔法推断。
- 与 R13 闭环兼容：反生成产物可直接喂 `to_policies` 编译下发。

### Tests
- 新增 `tests/test_reverse_template.py`（6 项）：IP/密码/团体名零泄漏
  （含 `%^%#…` 密文格式）、网掩码/0.0.0.0 保留、同 IP 共享占位、
  `find_leaks` 能抓原文、render 往返零残留、to_policies 直通。
- 全量 **326 passed, 2 skipped**（+6）。

## [3.28.0] - 2026-11-02

### Added（R5 OpenFlow 传输层：os-ken 可选依赖）
- **`sdn/southbound/openflow_transport.py`**：OF1.3 TCP 通道——
  `OsKenTransport.connect()`（HELLO 握手）/ `send_flow_mod()`（发送 +
  Barrier Reply 确认落表，交换机回 ERROR 直接抛错不重试）/
  `receive_port_status()`（端口变化摘要）。通道本体用标准库 socket 实现，
  os-ken 作为**能力闸门**（与 `OpenFlowAdapter.available()` 同口径）。
- **`program_flows` 两段行为**：未装 os-ken → 保持既有契约
  （`UnsupportedOperation`，报错含"已校验并编码 N 条"+ 安装提示）；
  装了 → 真实下发（需要 OVS/mininet 对端）。os-ken 进
  `[project.optional-dependencies].openflow`，**不在必装依赖**，不装不崩。

### Tests
- 新增 `tests/test_openflow_transport.py`（6 过 2 跳过）：未装路径断言、
  HELLO/Barrier 逐字节、PORT_STATUS 解析、OF 端口推断（22 不当 OF 口）、
  未连接即发送报错、对本地假交换机的"握手→下发 1 条 flow→barrier"通路、
  `pytest -m openflow_live`（需真实 OVS，默认跳过，marker 已登记）。
- 既有 11 项 openflow 编码测试全绿（行为不变）。
- 全量 **320 passed, 2 skipped**（+6）。

## [3.27.0] - 2026-11-02

### Added（R9 设置页扩展）
- **备份目录设置项**：填写新目录 →「迁移…」→ 二次确认后立即切换
  （`set_backup_dir(move=False)`：**旧文件原地不动**，新快照进新目录），
  设置键 `backup_dir` 即时持久化，重启后按它构造备份器。
- **日志级别设置项**：DEBUG/INFO/WARNING/ERROR 下拉，保存后即时应用到
  `netwright.*` 命名空间（`lib.settings.apply_log_level`，非法值回退 WARNING）。
- **REST API token 管理区**：列表（label · scope · 掩码）＋发放只读 token
  （起名对话框，发放后弹完整 token 供复制）、吊销选中（主 token 引导走轮换）、
  轮换主 token——全部即时生效并持久化（R6 的 GUI 落地）。
- 事件源默认端口设置项 v3.18 起已有，保持不动。

### Tests
- GUI 冒烟新增 1 项（R9 三合一）：备份目录切换后旧文件在原位、新快照进新目录、
  设置即时落盘；DEBUG/WARNING 日志级别即时生效并持久化；发放→列表→吊销
  token 全链路（弹窗全部 mock，避免测试挂起等点击）。
- 全量 **314 项 pytest 通过**（+1）。

## [3.26.0] - 2026-11-02

### Added（R8 备份治理：保留份数 / 导出 zip / 目录迁移）
- **按设备设保留份数**：`ConfigBackup.device_keep`（settings 键
  `backup_keep_device`）+ `set_device_keep(device, n)` 立即对现有历史生效；
  未登记的设备用全局 `backup_keep`。
- **导出 zip**：`ConfigBackup.export_zip(path, devices=None)` / 
  `ControllerStore.export_backups_zip()`——zip 内含 `manifest.json`
  （每份快照的设备 / 时间 / 大小 / **sha256**，与 `BackupEntry` 一致）。
- **目录迁移**：`ConfigBackup.migrate_root(new_base)` /
  `ControllerStore.set_backup_dir()`——目标 `backups/` 空闲时整个目录
  同盘原子重命名（历史完整保留、旧路径消失）；被占用时旧目录保留只读、
  新目录从空开始；迁移后写入只进新目录（事件 `backup.migrated`）。
- app 启动时从设置读取 `backup_keep` / `backup_keep_device` 构造备份器。

### Tests
- 新增 `tests/test_backup_govern.py`（6 项）：按设备保留份数覆盖全局并立即
  prune、zip manifest 的 sha256 一致性、按设备过滤导出、迁移搬移分支、
  迁移保留分支、store 集成（旧目录不再被写入）。
- 全量 **313 项 pytest 通过**（+6）。

## [3.25.0] - 2026-11-02

### Added（R7 巡检治理：可取消 / 并发可配 / 超时可控）
- **`inspector.run_batch` 支持取消**（`cancel=探针`）：取消后 **2 秒内收尾**——
  未开始的任务 `cancel_futures` 撤销，已在执行的留给线程池自然结束（不强杀），
  已完成的结果照常返回；跳过列表注明"已取消：剩余 N 台未巡检"。
  执行器从 `with` 改为显式 `shutdown(wait=False, cancel_futures=True)`
  （`with` 退出会等慢设备跑完，取消就失去意义）。
- **巡检页新增「取消」按钮**：巡检中「开始」变灰、「取消」可用；点取消立即变灰
  并提示收尾中；收尾后「开始」恢复可再次开始。并发数本就可配（5/10/20/50 下拉），
  命令超时沿用 inspector 参数（15s）。
- **线程模型修正**：巡检 worker 不再从后台线程调 `app.after`（红线）——
  worker 只置数据 + 脏标记，页面 150ms 轮询刷新（与 events 页同一约定）。

### Tests
- 新增 `tests/test_inspection_govern.py`（4 项）：20 台 × 5 命令 mock 场景取消
  < 2s 收尾、开局即取消立即返回、不取消全量完成回归、进度停在取消时完成数。
- GUI 冒烟新增 1 项：取消按钮状态机（灰→可用→取消→恢复可再次开始）。
- 全量 **307 项 pytest 通过**（+5）。

## [3.24.0] - 2026-11-02

### Added（R6 多 token 与审计）
- **`TokenAuth` 多 token 化**：`tokens: dict[token, {"scope": "read"|"write", "label"}]`；
  主 token（write）`rotate()` 一键轮换（旧 token 立即 401，子 token 不受影响）；
  `issue(scope, label)` 发只读/可写子 token，`revoke()` 单独吊销；
  `rotation_log` 记录发放/吊销/轮换。`from_settings` 从 settings 的 `api_tokens`
  键恢复（主 token 仍走 `api_token` 键，向后兼容）。
- **REST 鉴权区分 401/403**：`nbapi.dispatch` 改走 `auth.authorize()`——
  无效 token 401、只读 token 调写路由 403；v1 写接口（/api/apply）同样按
  POST 校验 scope，只读 token 无法借旧接口绕过。
- **调用来源审计**：每次 REST 调用（含被拒的）写一条审计——
  `api.request` / `api.auth_denied`，带 method、path、**IP + token label**。
- app 层新增 `issue_api_token()` / `revoke_api_token()`（持久化到设置）。

### Tests
- 新增 `tests/test_auth_multi.py`（8 项）：只读 GET 放行/POST 403、无效 401、
  轮换旧 401 新可用、吊销子 token、审计含 IP+label（成功/拒访/无效 token 三类）、
  settings 往返、旧单 token 用法兼容、健康检查公开。
- 全量 **302 项 pytest 通过**（+8）。

## [3.23.0] - 2026-11-02

### Added（R14 模板引擎增强：条件 / 循环 / 精确报错）
- **`render_template` 支持两个最小块指令**（零第三方依赖，AST 解析）：
  - `{{#if var}} … {{/if}}`：var 为空/0/false/none/no/缺省时整段不输出，
    假分支里的变量不参与缺失检查（"有 vlan 200 才生成 DHCP 中继"不用再复制模板）；
  - `{{#each list}} … {{/each}}`：列表按逗号/空白分隔（也接受真列表值），
    块内 `{{item}}` 为当前元素，可与外部变量混用；支持任意嵌套。
- **报错带行号**：`第 12 行：{{#if}} 缺少 {{/if}}`、`第 N 行：{{/each}} 与
  第 M 行的 {{#if}} 不匹配`、多余闭合同样定位到行。
- **`template_variables` 块语义**：`#each` 的列表名算必填（驱动循环），
  `#if` 的条件名是可选开关不算，`item` 由引擎注入不算——生成页/策略编译
  的必填列自动跟随。

### Tests
- 新增 `tests/test_template_engine.py`（17 项）：if 真/假/缺省分支、各假值、
  each 空/列表/嵌套变量/真列表值、块嵌套、四类行号报错、旧占位符语义不回归、
  template_variables 块语义、DHCP 中继端到端场景。
- **存量 116 个模板全部仍能渲染、零残留**（引擎换 AST 后逐个重跑）。
- 全量 **294 项 pytest 通过**（+17）。

## [3.22.0] - 2026-11-02

### Added（R4 意图 → 流表）
- **`sdn/openflow_plan.flows_for(intent_key, params, vendor)`**：意图 → OpenFlow
  flow 计划。`vlan_deploy` 每个 VLAN 生成两条 flow——`ingress_tag`（access 口
  push_vlan 后转发）与 `egress_untag`（带标签流量送回 access 口）。
  `in_port`/`out_port` 是流表计划的事实参数：缺失/非法/相同 → 空列表
  （与 reverse.py 的"不猜命令"同一原则）；不支持的意图一律 `[]` 不报错。
- **`Policy.flows: tuple = ()`**：策略携带流表计划，`to_dict()` 带出；
  `PolicyCompiler` 编译时自动附加（无流表语义的意图为空元组）。
- **REST `POST /api/v2/intents/plan`**：返回新增顶层 `flows` 字段
  （聚合全部 planned 策略的流表计划）；既有字段不变。
  plan 产出的 flows 可直接喂 `/api/v2/openflow/validate` 全部编码通过（闭环）。

### Tests
- 新增 `tests/test_openflow_plan.py`（7 项）：ingress/egress 断言、FlowEntry
  全量校验、缺端口空计划、未知意图空计划、编译附加 flows、REST plan 带 flows、
  plan → validate 编码闭环。
- 全量 **277 项 pytest 通过**（+7）。

## [3.21.0] - 2026-11-02

### Added（R13 模板 → 策略闭环）
- **`lib/generator.to_policies(template, devices, inventory)`**：模板 × 设备表 →
  每台设备一条 `Policy`（intent_key=`template_deploy`），只渲染不连设备；
  `Policy.params["template"]` 记录 `{file, sha256, name}`，运行档案与审计可追溯
  到模板文件。设备行对不回清单时用行内信息合成只读替身（不强制先入清单）。
- **`IntentLifecycle.adopt(policies)`**：外部编译好的策略走与意图完全相同的
  状态机（compiled → planned → approve → deploying → …）；`template_deploy`
  无登记反向命令 → 与现有一致地落 `rollback_blocked`，不猜命令。
- **生成页新增「编译为策略 →」**：设备表 × 模板编译成策略并完成静态预演，
  跳到「意图与策略 → 运行档案」确认下发——模板下发从"生成 .cfg 靠人工"
  变成走审计闭环。

### Fixed
- **运行档案 id 冲突**：`lifecycle.create` 每次新建 `PolicyCompiler`，实例级
  计数器从 `pol-0001` 重新开始，第二批档案会覆盖第一批（`runs[policy.id]`）。
  改为模块级全局计数器（`policy.next_policy_id`），同批内 `tpl-`/`pol-` 前缀区分。

### Tests
- 新增 `tests/test_template_policy.py`（7 项）：N 条命令断言、模板 sha256 溯源、
  缺变量报错带序号、清单外设备替身、完整生命周期（含审计）、回滚 blocked、
  内置模板零残留回归。
- GUI 冒烟新增 1 项：生成页编译 → 运行档案出现 template_deploy 且已预演。
- 全量 **270 项 pytest 通过**（+8）。

## [3.20.1] - 2026-11-02

### Added（R3 配置回滚——危险操作）
- **`ControllerStore.restore_backup(device, filename, timeout=30.0)`**：
  返回 `{"ok", "pre_backup", "commands", "error"}`。顺序固定——读现网配置
  （读不到**不发任何命令**）→ 恢复前自动 `backup_device()` → 解析快照
  （跳过空行与 `!`/`#` 注释）→ 一次性下发；**失败绝不重试第二次**。
  成败都写 `config.restore` 审计并发事件。
- **备份历史对话框新增「↩ 恢复到设备」**：二次确认弹窗写明"将覆盖 N 行配置"+
  快照名 + 自动备份提示；恢复在后台线程执行，线程模型遵守红线（worker 不碰 Tk，
  对话框 after 轮询收尾）；完成弹窗显示"已自动备份为 <文件名>"。

### Tests
- 新增 `tests/test_restore.py`（6 项）：恢复前自动备份且 pre_backup 真实落盘、
  读现网失败零下发、下发失败不重试（sent 只有一次）、成败审计、未知快照/纯注释快照拒绝。
- GUI 冒烟新增 2 项：确认文案含影响行数、完成弹窗含备份文件名；未选中快照不进确认。
- 全量 **262 项 pytest 通过**（+8）。

## [3.20.0] - 2026-11-02

### Added（R2 时间线联动）
- **时间线点行可跳转定位**：`TimelinePage._open(item)`——事件 → 事件页并高亮该事件、
  配置快照 → 直接打开该设备的备份历史对话框、意图运行 → 控制器运行档案并选中该档案。
  单击仍看详情，双击跳转；页头说明同步更新。
- **跨页定位传参**：`app.pending_focus = {key, payload}` 约定，目标页在 `on_show`
  消费（事件页按 event_id 选中、控制器页按 run_id 选中）；消费后置 None。
- `TimelineItem` 增加可选 `payload` 字段（事件 id / 快照设备+文件名 / 运行档案 id），
  `build_timeline` 聚合时填充；`to_dict()` 带出，REST 侧可直接消费。

### Tests
- GUI 冒烟新增 4 项：事件行 → `_active_key == "events"` 且行被选中；快照行 →
  打开 BackupHistoryDialog；意图行 → 运行档案被选中；无 payload / 未知类型
  落回对应页面首页不崩。
- 全量 **254 项 pytest 通过**（+4）。

## [3.19.1] - 2026-11-02

### Added（R11 页面惰性构建——冷启动最大的一笔）
- **页面在第一次被 show 时才构建**：`app.LazyPages`（dict 子类，`__missing__`
  按需构建，保持 `app.pages[key]` 既有写法）+ `NetWrightApp._ensure_page`（幂等）。
  已构建页面同一会话内复用；`apply_theme` 只重建当前页，未访问页面下次 show
  时带新主题按需重建。
- **`tools/bench_startup.py`**：输出 `construct_ms` / `first_show_ms` / `total_ms` /
  `pages_built`；`--exe <path>` 模式测打包产物"进程启动→窗口可见"毫秒数（R12 用）。

### Performance（本机实测，5 次取中位）
- 页面构建：**257 ms（12 页）→ 34 ms（1 页），-87%**（规格要求 ≥40%）；
  App 构造总耗时 814 ms → 337 ms（-59%）。
- 双击 exe 到出窗口的剩余大头是 Python 解释器与依赖导入（onefile 解压），
  页面构建已不再是瓶颈。

### Tests
- `tests/test_lazy_pages.py`（R11 契约 5 项）从整文件 skip 变为 **5 passed**（未改断言）。
- conftest 把 `app.BASE_DIR` 一并重定向到 tmp：设置文件（last_page 等）不落仓库，
  用例行为不随本机设置漂移。
- 全量 **250 项 pytest 通过、0 skipped**（+5，两个 TDD 骨架文件全部转正）。

## [3.19.0] - 2026-11-02

### Added（R1 列表页统一组件化）
- **`widgets.DataTable`**：列表页统一组件（外框 + 表头 + 斑马纹 + 选中保持）。
  - `set_rows(rows, tags_by_row=None)` 整表批量重建，行 iid 固定为字符串行号；
  - `preserve_selection()` 上下文管理器：刷新前后按行下标保持选中，越界自动丢弃；
  - `selected_indices()` 选中行下标；`table.tree` 仍暴露底层 Treeview 供高级用法；
  - 内置 `_CompatTreeview`：Python 3.14 起 `cget("show")` 返回元组，统一归一回字符串，
    跨版本行为一致。
- **7 个页面 / 9 张表全部换用 DataTable**：设备清单、批量巡检、资产盘点（结果 + 环路）、
  时间线、命令速查、事件流、工具箱（端口扫描 + 在线检测）。controller 运行档案表
  以 run.id 为行身份（跨刷新选中稳定），暂保留 make_table。
- **tests/conftest.py 环境加固**：实测本机杀软实时扫描对 uv 版 Python 的 tcl/tk
  库目录有读竞态（"couldn't read …/tk8.6/xxx.tcl"），在 `Tk.__init__` 层加带退避重试，
  消除 GUI 测试随机 skip（此前 10 轮累计 14 次误跳过）。

### Fixed
- 资产盘点「检测环路/漂移」回调崩溃：worker 给 `_loop_done` 传 3 个参数但签名只收 2 个
  （TypeError 被事件循环吞掉，表格永不更新）。

### Tests
- `tests/test_widgets.py`（R1 契约 10 项）从整文件 skip 变为 **10 passed**（未改断言）。
- 全量 **245 项 pytest 通过**（+10）。

## [3.18.5] - 2026-11-02

### Fixed（基线体检：ruff 新版抓到的真 bug）
- **概览「清除演示数据」点击即崩**：`pages/dashboard.py` 用了 `toast()` 但从未导入
  （v3.18.4 引入），无演示数据时点按钮抛 `NameError`。已补导入，并新增点击路径
  回归测试（此前只测了按钮存在，没真实调用）。
- `tests/test_widgets.py` 去掉未使用的 `ttk` 导入（TDD 骨架文件，未动断言）。

### Tests
- 全量 **235 项 pytest 通过**（+1 回归测试）。

## [3.18.4] - 2026-11-02

### Added
- **清除演示数据的显式入口**（之前只藏在「? 引导」里）：
  - 概览「快捷入口」新增「🧹 清除演示数据」；
  - 设备清单工具栏新增「🧹 清除演示」（带二次确认）；
  - 三者统一走 `NetWrightApp.clear_demo_data()`：删设备 + 删演示链路 + 清图 + 刷新页面 + 发事件。

### Tests
- GUI 新增：载入 → 清除后演示设备/链路/图节点都不残留，且两个入口存在。
- 全量 **234 项 pytest 通过**。

## [3.18.3] - 2026-11-02

### Fixed（exe 图标/资源优先级）
- `resource_dir()` 增加 `prefer_local`：**模板**优先 exe 旁（允许自带模板），
  **图标/图片**优先打包内置（防止 exe 旁的旧 `assets/` 盖住新 logo）。
- 实测确认：`dist/NetWright.exe` 内嵌 7 档尺寸的新 logo（16…256），
  `ExtractAssociatedIcon` 取出的 32×32 即控制器枢纽图标。

### Tests
- `tests/test_paths.py` 增加"资源 vs 模板优先级"断言（6 项）。
- 全量 **233 项 pytest 通过**。

## [3.18.2] - 2026-11-02

### Fixed（打包后模板丢失）
- **exe 里看不到配置模板**：onefile 把 `datas` 解压到 `sys._MEIPASS`，但代码按"exe 同级目录"
  找 `templates/`，于是模板数变成 0。新增 `netwright/paths.py` 区分两类路径：
  - `data_dir()`：可写数据（清单/设置/审计/备份）→ **exe 同级**，升级不丢数据；
  - `resource_dir(name)`：只读资源（templates/assets）→ 优先 exe 同级（允许用户自带模板），
    其次 `_MEIPASS`（打包内置），最后源码树。
- 生成器与图标统一走 `resource_dir()`；`list_builtin_templates()` 在打包环境能读到 116 个模板。

### Tests
- 新增 `tests/test_paths.py`（5 项）：data_dir 指向 exe 同级、exe 旁自定义模板优先、
  `_MEIPASS` 回退、打包环境模板可加载、源码环境仍 116 个。
- **打包实测（本机，2026-11-02）**：onefile（UPX 关闭）双击到窗口 **4.4 s**，
  onedir **3.5 s**，exe 内确认含 **116 个模板 + library.json + assets**（CArchive TOC 校验）。
  两个版本都慢在"启动即构建全部 12 个页面"，对应规格 R11 惰性构建。
- 全量 **232 项 pytest 通过**（+5）。

## [3.18.1] - 2026-11-02

### Fixed（"exe 卡卡"的三处主要来源）
- **拓扑悬停重绘无节流**：鼠标移动一秒上百个事件，每次都重画边/节点；现在 40ms 合并一次，
  且只在悬停节点变化时重绘。
- **大拓扑力导向耗时**：算法 O(n²·iter)，100 台设备跑 240 轮要数秒；迭代次数改为按节点数
  自适应（总预算约 6000 节点·轮），小图保质量、大图先保响应。
- **10 秒刷新无脑重建表格**：事件页 / 概览最近事件 / 时间线在数据未变时直接跳过重建。

### Added
- **`NetWright-onedir.spec`**：onedir 打包，启动通常 < 1 秒（onefile 每次要解压 24 MB 到 %TEMP%，
  再叠加 UPX 与杀软扫描，是"双击后等两秒"的根因）。CI 仍用单文件 spec，这个给自用/内部分发。

### Tests
- 新增 `tests/test_perf.py`（2 项）：200 节点布局 < 5s、小图布局结果确定性。
- 全量 **227 项 pytest 通过**（+2）。

## [3.18.0] - 2026-11-02

### Added（OpenFlow 1.3：先做能离线验证的那一半）
- **流表模型与校验**（`FlowEntry`）：table / priority / idle_timeout / hard_timeout 值域，
  match 字段白名单（in_port、eth_type、eth_src/dst、vlan_vid、ip_proto、ipv4_src/dst），
  动作白名单（output / drop / push_vlan），`drop` 不可与其他动作混用。
- **`flow_mod` 编码**：按 OF1.3 线格式输出完整报文（8 字节头 + match OXM + apply_actions），
  8 字节对齐；`vlan_vid` 自动带 `OFPVID_PRESENT` 标志。
- **REST**：`POST /api/v2/openflow/validate`，返回每条 flow 的字节数与 hex（dry-run）。
- **适配器诚实边界**：`program_flows()` 先校验+编码，再抛 `UnsupportedOperation`
  并说明"已编译 N 条但通道未实装"——不假装下发成功。

### Tests
- 新增 `tests/test_openflow.py`（11 项）：报文头/长度/对齐、VLAN 标志位、6 类非法输入、
  适配器编码与拒绝传输、REST 鉴权与 400 分支。
- 全量 **225 项 pytest 通过**。

## [3.17.0] - 2026-11-02

### Added（排障时间线）
- **「时间线」工作区**（系统 / 时间线）：把三类信息合成一条按时间倒序的轴——
  - 事件流（链路/认证/漂移等，带严重度着色）；
  - 配置快照（每台设备最多取最近 10 份，避免刷屏）；
  - 意图运行档案（下发/校验/回滚结果）。
- **`sdn/timeline.py`**：纯聚合函数 `build_timeline(store, limit=120)`，限流可配。
- **REST**：`GET /api/v2/timeline?limit=`（需 token）。

### Changed
- 页面注册表扩到 **12 个页面**，「系统」分组下是「时间线 / 设置」。

### Tests
- 新增 `tests/test_timeline.py`（4 项）：三源合并、倒序、limit、REST 鉴权。
- 全量 **225 项 pytest 通过**。

## [3.16.0] - 2026-11-02

### Changed（性能与代码质量）
- **`ConfigBackup.latest()` 不再遍历整个历史**：只 stat 最新文件（按文件名排序），
  以前每次 save 都要读+哈希全部快照（keep=30 时 30 次 IO）。
- **摘要缓存**：`_digest()` 按 `(路径, mtime_ns, size)` 缓存 sha256，重复查询接近零 IO。
- **设备清单自动刷新加签名判断**：设备/状态没变时直接跳过 Treeview 重建，
  10 秒自动刷新在几百台设备下不再整表刷新。
- **拓扑画布分层绘制**：网格独立成 `grid` 层，只在尺寸变化时重建；
  悬停/缩放只重画边与节点，并把屏幕坐标一次算好复用（之前每次悬停重画几十条网格线）。
- 代码注释补齐：备份排序/摘要缓存/刷新跳过/网格分层都写清"为什么"，
  尤其是踩过的坑（见下）。

### Fixed
- **快照可能被自己删掉**：文件名原先用秒级时间戳，上一份被 prune 删掉后，
  下一次 save 会复用同名；配合"同秒多份"的排序缺陷，新快照会被当成最旧删除。
  现在文件名 = 秒级时间戳 + **同秒自增序号**，且 `_prune(protect=…)` 绝不删刚写入的那份。
- 同一秒内多份快照的顺序改由文件名序号决定（不再依赖 `st_mtime_ns`），
  规避 Windows 下快速连续写入时时钟抖动导致的乱序。

### Tests
- 备份 +2（latest 只读最新一份、history 完整性），GUI +2（刷新跳过、网格层复用）。
- 全量 **225 项 pytest 通过**。

## [3.15.0] - 2026-11-02

### Added（配置漂移检测）
- **`ConfigBackup.diff_against()`**：把最近一次快照和一段现读配置直接对比（不落盘）。
- **`ControllerStore.compare_live()`**：读设备当前配置 → 与最近快照 diff →
  有差异时发 `config.drift` 事件（severity=warning），事件流里能看到。
- **备份历史对话框新增「与现网对比」**：不用先备份，直接看设备有没有被手改过；
  一致时明确提示"没有漂移"，读取失败走统一的人话错误提示。
- **REST**：`GET /api/v2/backups/live-diff?device=<显示名>`。

### Fixed
- **同一秒内多份快照排序不稳定**：改为按 `(mtime_ns, 文件名序号)` 排序，
  避免 prune 删错快照（此前 `test_prune_keeps_latest` 偶发失败）。

### Tests
- 备份测试新增 4 项（diff_against、无快照报错、compare_live 漂移事件、live-diff 路由）。
- 全量 **225 项 pytest 通过**。

## [3.14.0] - 2026-11-02

### Added（设置页 + 备份差异 GUI）
- **「设置」工作区**（系统 / 设置）：
  - REST 端口、Syslog 端口、SNMP Trap 端口、备份保留份数、自动刷新开关；
  - 端口做 1-65535 校验、保留份数 2-500 校验，**失败会指出具体哪一项**；
  - 事件源端口保存后**立即按新端口重启监听**；REST 端口提示需重启程序；
  - 自动刷新开关与顶栏勾选双向同步。
- **备份历史对话框**（设备清单 →「🗂 备份历史」）：
  - 左侧列出该设备全部快照（时间 + 大小），支持 Ctrl 多选两份对比；
  - 右侧 diff 面板按 `+/-/@@` 着色，默认展示"最近两次"；
  - 只有一份快照时明确提示"再备份一次即可对比"，不给空面板。
- 侧栏新增「系统 / 设置」分组，`PAGE_REGISTRY` 扩到 11 个页面（明暗主题重建仍不崩）。

### Tests
- GUI 冒烟 +3：设置页保存落盘、备份历史对话框 diff、页面循环覆盖新页面。
- 全量 **225 项 pytest 通过**。

## [3.13.0] - 2026-11-02

### Added（错误提示打磨）
- **`lib/errors.py`：技术异常 → 人话 + 下一步**。覆盖认证失败、连接超时、端口拒绝、
  权限、文件缺失、`UnsupportedOperation`、`RestconfError`（按 401/403/404/409 给建议）、
  `NetconfError`、`LifecycleError`；未知异常保留 `类型: 消息`，并**始终附带原始信息**便于排障。
- **`friendly_text()`**：把上游已经字符串化的错误（巡检结果、命令回显）按关键字翻译。
- 接入点：设备清单（连接测试、配置备份）、运行档案（下发/校验/回滚）、巡检详情。
- 预留 `paramiko` 为可选：按类名识别，未安装也能用。

### Changed
- 事件页空状态：没有事件时表格显示一行引导（"可启动事件源监听，或在拓扑页做一次发现"），
  不再是一张空白表。

### Tests
- 新增 `tests/test_errors.py`（9 项）：认证/超时/拒绝/校验/南向/生命周期/未知异常与关键字翻译。
- 全量 **225 项 pytest 通过**。

## [3.12.0] - 2026-11-02

### Added（意图生命周期 GUI + 配置备份）
- **「运行档案」页**（意图与策略 → 运行档案）：列出每条策略的状态、命令数、风险、
  能否回滚、更新时间；选中后看命令、反向命令、检查项、状态历史；按钮直接 **下发 / 校验 / 回滚**。
- **Dry-Run 即建档**：在「意图下发」点 Dry-Run 时同时生成运行档案（状态 `planned`），
  不需要先跑一遍再手工建任务。
- **配置备份与差异**（`sdn/backup.py`，Oxidized 式）：
  - 按设备目录存快照 `backups/<设备>/<YYYYmmdd-HHMMSS>.cfg`；
  - 与上一份 sha256 相同则不落盘（标"无变化"），默认保留最近 30 份；
  - `diff()` 输出 unified diff（可贴进工单）；
  - 设备名自动清洗；空配置拒绝写入（避免空文件覆盖历史）。
- **备份入口**：设备清单工具栏「🗄 备份配置」（选中优先，否则全部），后台线程执行，
  结果显示"已更新 / 无变化 / 失败"。
- **REST**：`GET /api/v2/backups`、`GET /api/v2/backups/diff`、
  `POST /api/v2/backups`（批量，单次上限 50 台，部分失败返回 207）。

### Tests
- 新增 `tests/test_backup.py`（12 项）+ GUI「运行档案」冒烟 1 项。
- 全量 **225 项 pytest 通过**。

## [3.11.0] - 2026-11-02

### Added（控制器能力：从"能下发"到"可回滚、可观测"）
- **意图生命周期状态机**（`sdn/lifecycle.py`）：
  `compiled → planned → approved → deploying → deployed → verified → rolled_back`，
  非法迁移抛 `LifecycleError`；每次迁移进历史并发事件。
- **反向命令生成**（`sdn/reverse.py`）：VLAN 部署 / 端口 shutdown 生成确定安全的
  反向命令；端口模式互转、BGP 邻居、管理面基线等**明确返回"不可回滚"及人工处置建议**，
  回滚时状态停在 `rollback_blocked`，绝不猜命令。
- **下发后校验**：`verify()` 回读 `display vlan` / `show vlan brief` 检查意图是否真的生效；
  没有回读命令的厂商诚实降级为"仅确认下发"。
- **REST v2 意图路由**：`POST /api/v2/intents/{plan,deploy,verify,rollback}` +
  `GET /api/v2/intents/runs`。
- **RESTCONF 完整实装**：GET/PATCH/POST/DELETE、Basic Auth、TLS 可配、错误带状态码。
- **NETCONF 实装**：get-config / edit-config / commit / discard；`session_factory`
  可注入假会话，没装 ncclient 也能单测。
- **事件源**：Syslog 监听（UDP 5140，RFC3164/5424/裸消息）+ SNMPv2c Trap 监听
  （UDP 1162，自实现 BER，不依赖 pysnmp），归类 link down/up、BGP/OSPF、配置变更、
  登录失败、硬件告警。
- **拓扑增量高亮**：事件命中的节点画琥珀脉冲圈（90 秒），自动刷新自然消退。
- **事件页"事件源"卡片**：一键启停监听，显示端口与收包数。
- **REST v2 鉴权**：除 `/api/v2/health` 外都要 Bearer token（或 `X-API-Token`）；
  token 首次启动生成并落盘，GUI 可查看/复制/轮换，v1 写接口同样受保护。
- **`docs/ARCHITECTURE.md`**：对 ODL / ONOS / Neutron / NetBox / DNA Center /
  Oxidized / NAPALM 的借鉴矩阵与"刻意不做"清单。

### Tests
- 新增 `tests/test_lifecycle.py`（16 项）与 `tests/test_southbound.py`（18 项）。
- 全量 **225 项 pytest 通过**。

## [3.10.0] - 2026-11-02

### Added（小白易用性）
- **一键演示数据**（`netwright.demo`）：7 台 192.0.2.x 假设备 + 6 条台账链路，
  不覆盖现有数据、按备注识别可一键清除；引导面板、设备清单空状态、帮助入口都能触发。
- **新手引导面板**（`? 引导` / `Ctrl+H`）：4 步直达（演示数据 → 拓扑 → Dry-Run → 巡检）
  + 快捷键说明 + 打开用户指南。
- **设备清单空状态改为三选一**：载入演示数据 / 手动添加 / 导入 CSV，不再只给一句提示。
- **连接测试**（`🔌 测试连接`）：对选中（或全部）设备做 TCP 端口探测，几秒出结果，
  区分"网络不通"与"账号问题"。
- **拓扑搜索 + 仅纳管过滤**：按节点名/厂商过滤，布局不变只影响绘制。
- **自动刷新 10s**：顶栏勾选框（默认开，设置持久化），并与 `F5` 手动刷新共用同一入口；
  顶栏显示上次刷新时间；发现/巡检进行中自动暂停。
- 快捷键：`F5` 刷新、`Ctrl+H` 引导、`Ctrl+1…9` 切换工作区。

### Changed
- **图标重做**（`tools/make_icon.py`）：控制器枢纽 + 三节点拓扑标记，深海军蓝底、
  16px 仍可辨；侧栏品牌标记同步为同一造型。
- **README 重写**（原文件自 v3.2 起损坏：597 KB 重复短句污染，正文只剩 5 KB）：
  现在是可读的普通 Markdown，含截图、功能地图、内核架构图、REST v2、路线图。
- 用户指南：新增"方式零：一键演示数据"、2.4 小白友好设计、连接测试、导出 CSV 说明、
  自动刷新手势与 4 条新 FAQ；示例台账扩到 7 行含 6 条链路。
- `settings.DEFAULTS` 清理陈旧键 `theme`，改为 `theme_mode/theme_hue/auto_refresh/nav_collapsed`；
  旧键会在加载时迁移成 `theme_mode`。

### Fixed
- **Telnet 协议重启后丢失**：`Device.from_storage` 漏读 `protocol` 字段（回归测试已补）。
- **CSV 导出明文密码**：默认不再导出密码（`export_csv(include_secrets=False)`）。
- **`netforge_*.json` 无迁移路径**：首次启动自动读取旧文件名并写入新格式（清单与设置都支持）。
- **CSV 同一设备多行**（每行一条链路）会被当成重复而丢弃链路：现在带链路信息的重复行静默用于建拓扑。
- `NetworkGraph` 新增 `clear()`，演示数据切换与重新盘点不再手工清私有字段。
- **CSV 只补链路时不落盘**：设备都已存在、只新增链路时，导入结果会丢失（现在按"设备或链路有变化"落盘）。

### CI / 工程化
- `pyproject.toml`：补 `[project.optional-dependencies].dev`（pytest/ruff/pillow/pyinstaller）、
  classifiers、keywords、Documentation/Issue Tracker 链接、`ruff` 排除构建产物。
- CI 改为 **Windows + Ubuntu × Python 3.10/3.12** 矩阵，加"文档体检"作业
  （README 体积/单行长度、版本号三处一致、CHANGELOG 有对应条目）。
- Build 工作流：tag 与包版本号一致性校验、SHA256SUMS、自动发布 Release。
- 新增 `pull_request_template.md`、Issue 模板 `config.yml`、`dependabot.yml`。

### Tests
- 新增 `tests/test_ux.py`（演示数据 / 清单迁移 / CSV 脱敏 / 多行链路 / 协议持久化 / 设置迁移）。
- 全量 **142 项 pytest 通过**。

## [3.9.0] - 2026-11-02

### Changed（UI 重做为 DLUX 控制台）
- **外壳换成控制器控制台三点式布局**：52px 深色顶栏（品牌 / 页面标题 / 状态 / 时钟 / 主色 /
  明暗切换）+ 224px 深色分组侧栏（控制器・资源・运维，可折叠为 64px 图标条）+
  浅色内容区（白卡片 + 8px 网格留白）。顶栏与侧栏在明暗模式下都保持深色，
  主色只用于交互与状态。
- **`theme.py` 重写为控制台令牌**：新增 `chrome*`（外壳）与 `topo_bg/topo_grid`（画布）令牌；
  保留 `bg/panel/fg/muted/accent/nav1/nav2/header1…` 全部旧名，8 个既有业务页零改动换肤。
- **页面头统一**：面包屑 + 标题 + 说明 + 右侧动作槽（`widgets.PageHeader`），
  8 个既有页面的标题区补上面包屑。

### Added（控制器内核 `netwright.sdn`）
- **事件总线**（`sdn/events.py`）：线程安全发布/订阅、topic 前缀过滤、500 条环形历史、
  严重度分级、坏订阅者隔离。
- **图模型**（`sdn/model.py`）：Node/Edge/NetworkGraph，接口名归一化、
  同链路去重、LLDP 自动「升级」台账链路（虚线→实线）、邻居/度数/孤立点统计、JSON 往返。
- **策略编译**（`sdn/policy.py`）：意图 → 每设备策略（命令 + 风险等级），
  区分「厂商不支持（跳过）」与「参数错误（报错）」，编译不发包、不连设备。
- **状态仓库**（`sdn/store.py`）：拓扑图 + 策略 + 统计的唯一事实来源，可持久化到
  `netwright_controller.json`（重启保留拓扑上下文）。
- **南向适配层**（`sdn/southbound/`）：`SouthboundAdapter` 契约 + 能力位
  （config_read / config_write / state_read / event_stream / flow_program）+ 注册表。
  CLI（SSH/Telnet）为完整实装；NETCONF / OpenFlow 1.3 / RESTCONF 为可插拔骨架
  （声明能力、缺依赖时如实标记，调用即抛 `UnsupportedOperation`，绝不假装成功）。
- **北向 REST v2**（`sdn/nbapi.py`）：`/api/v2/{health,snapshot,topology,events,policies,intents,southbound}` +
  `POST /api/v2/policies/compile`、`POST /api/v2/topology/sync`；与 v1 并存。
- **拓扑工作区**（新）：DLUX 式画布 —— 力导向/环形/分层三种布局、滚轮缩放、拖拽平移、
  节点点选 + 检查器（厂商/纳管/度数/邻居端口）、画布下沿图例、LLDP 实线 vs 台账虚线。
- **事件工作区**（新）：事件流表格（级别过滤/着色）+ 南向通道就绪状态 + 下发审计。
- **概览工作区重写**：5 个 KPI 磁贴、最近事件、控制器状态（REST/南向/运行时长/拓扑来源）、
  厂商分布条、快捷入口。
- 组件库新增 `PageHeader / SectionCard / StatTile / StatusDot / KeyValue`。

### Fixed
- `ControllerStore` 传入空 `EventBus` 时会被 `bus or EventBus()` 换成另一条总线，
  导致页面与内核看不到彼此的事件（已改为显式 `is None` 判断）。
- 顶栏时钟此前定义了 `_tick_clock` 但从未启动，界面永远空白。

### Tests
- 新增 `tests/test_sdn.py`（24 项）：事件总线、图模型、策略编译、南向注册表、
  状态仓库、REST v2 路由。
- 全量 **127 项 pytest 通过**（原 103 项 + 新增 24 项）。

## [3.8.0 – 3.8.4] - 2026-11-01

### Added
- 3.8.0：按钮按压/hover 反馈、批量模板导出（116 个 .cfg 按目录结构落盘）。
- 3.8.2：代码评审修复 + 使用文档 + 注释补全。
- 3.8.3：GitHub 就绪（CONTRIBUTING / SECURITY / Issue 模板 / CI 修正 / 数据文件出库）。

### Fixed
- 3.8.2：侧栏选中态不跟随切换（`show` 丢失 `_active_key`）。
- 3.8.2：页头白底白字不可读（扁平带 + 主色竖条 + 深色文字）。
- 3.8.4：版本号对齐。

## [3.7.0] - 2026-11-01

### Changed（UI 换肤第 2 步：全局 Token + 壳层）
- **theme.py 重写为云控制台规范令牌**：色彩语义化
  （primary #2570F2 / success #10B981 / warning #F59E0B / danger #EF4444 /
  text #1F2329 / text-secondary #646A73 / border #DEE0E3 / bg #F5F7FA /
  surface #FFFFFF），明/暗双模式 + 4 主色可选（蓝/绿/紫/橙）；
  间距常量 SPACE（8px 网格）；字阶（12/14/16/20/24px→pt 映射）。
- **壳层扁平化**：56px 顶栏（☰ 折叠 + 品牌 + 页面标题 + 状态/时钟 + 主题/壁纸菜单，
  纯 surface 底）；侧栏 240px 可折叠至 64px（图标模式），选中态 = soft 底 +
  3px 主色指示条 + 主色文字，hover = panel_alt；装饰性渐变全部退役
  （GradientFrame 组件保留不再使用）。
- **表格行高 40px**（规范 40-44px）；主题菜单改为 ☀/🌙 模式切换 + 主色选择。

### Added
- widgets 新组件：Tag（状态标签，soft 底 + 强色字 + 文字标签）、Skeleton（骨架屏）、
  Toast（右下角应用内通知）、Drawer（右侧抽屉 480/560px）、ScrollFrame（内部滚动）。
- WButton 升级：primary/ghost 语义自动配色（accent_deep 底白字，WCAG AA 达标）。

### Tests
- 100 项 pytest（主题冒烟改为明暗×4主色遍历；对比度回归改为扁平顶栏
  fg/header 与 white/accent_deep ≥4.5:1）。

## [3.6.0] - 2026-11-01

### Added
- **盘点联动环路告警**：MAC 表采集（华为/思科/H3C/MikroTik）→ 同机多口同一 MAC =
  🔴 高危环路；跨设备同 MAC = 🟠 环路/漂移；拓扑画布环路设备红圈 ⚠ 高亮，
  点击告警看处置建议（逐口拔线观察广播速率）。
- **MAC 漂移可视化**：每轮检测自动保存快照，与上一轮 diff——同设备换口 /
  跨设备迁移均告警。
- **巡检趋势图**：每轮批量巡检自动落盘摘要（netwright_history_inspection.jsonl），
  巡检页底部 📈 趋势折线图（Canvas 纯实现）：告警总数/失败台数/警告台数/平均耗时。

### Added
- **WButton 交互反馈**：hover 提亮 / press 压暗 / Leave 恢复（强色与 ghost 双样式），
  `set_loading()` 提交 loading 态。
- **批量模板导出**：配置生成页「📦 导出全部模板」——116 个模板按目录结构
  写入用户选择目录（含 library.json，NADT 兼容）。

### Tests
- 103 项 pytest（按压反馈逻辑/ghost 反馈/批量导出冒烟）。

## [3.5.0] - 2026-11-01

### Added
- **一键内网资产盘点**（资产盘点工作区）：种子设备 → LLDP/CDP 邻居 + ARP/MAC 表 →
  内网 IP 汇总 → 管理协议探测（SSH/Telnet/NETCONF）→ 与清单关联（已知/新增/厂商分布）；
  支持按跳数递归（凭据沿用种子设备）；进度条 + 结果表（来源标签）+ 拓扑图
  （新发现黄色/已知绿色）+ 原始输出页 + 新增资产一键入清单。
- **Telnet 接入**：轻量 Telnet 客户端（标准库实现，IAC 剥离/登录/静默窗口读），
  Device 增加 protocol 字段（ssh/telnet），run_commands 按协议分发。
- **台账自动建拓扑**：CSV 新增 协议/本端接口/对端设备/对端接口 列，导入自动生成
  台账链路并持久化；控制器拓扑合并 LLDP（实线）∪ 台账（虚线）。

### Tests
- 88 项 pytest（ARP 三厂商解析/关联分析/盘点流程 mock/Telnet IAC 剥离/
  协议分发/台账建拓扑）。

## [3.4.0] - 2026-11-01

### Changed
- **项目更名：NetForge → NetWright（网络工匠）**。
  wright 意为工匠（shipwright/wheelwright 同源），贴合"工作台手工搓网络"的定位；
  经查证 NetWright 在网络工具领域无占用（NetLoom 已被一款 Windows 监控工具使用）。
- 包/文件/资产全量更名：src/netwright、netwright_settings.json、
  netwright_audit.log、netwright_devices.json、NetWright.exe。
- 图标重绘：经纬交织的"织网"图案（wright 意象），配色对齐薄荷清晨主题。

## [3.3.2] - 2026-11-01

### Fixed
- **主题切换页面下沉**：apply_theme 未销毁旧的外层 main 框架与顶栏分隔条，
  每次切换残留空框架挤压布局（新增回归测试：切换 3 次根级框架数量恒定）。
- **双击 exe 弹出 cmd 窗口**：spec 的 console 改为 False；
  在线检测的 ping 子进程加 CREATE_NO_WINDOW（GUI 模式不再闪黑框）。
- **顶部蓝白竖线可读性差**：移除顶栏左侧 3px 强调条，改为顶栏下方 1px 细分隔线。

## [3.3.1] - 2026-11-01

### Performance
- **子网计算内存修复**：calc_subnet 不再物化地址列表——/8 网段从 OOM 级
  （1600 万地址对象）降至 ~3KB / 0.3ms；整数运算直接推导可用范围。
- **渐变绘制**：GradientFrame 按 4px 分块（对象数 -75%）+ 16ms resize 防抖 +
  同尺寸跳过重绘。
- **侧栏分层重绘**：渐变/壁纸背景只在尺寸或壁纸变化时重绘，hover 仅重绘
  轻量条目层（背景 tag 常驻底层）。
- **模板库缓存**：list_builtin_templates 按 library.json mtime 缓存——总览刷新
  不再每次读 116 个模板文件。
- **壁纸缓存上限**：resize 时只保留最近 3 个尺寸的 PhotoImage，防内存膨胀。
- **IO 削减**：切换工作区不再每次写 settings（last_page 改为退出时保存）；
  在线检测线程回调加 TclError 防护（关窗后静默放弃）。

### Results
- 全量测试耗时 41s → **8s**（模板缓存消除 116 文件重复 IO）；
  75 项 pytest 全过；ruff 全绿。

## [3.3.0] - 2026-11-01

### Added
- **清新配色重制**：薄荷清晨/晴空/樱粉/蜜橙（亮）+ 深空蓝/曜石（暗），低饱和高留白，
  默认主题改为「薄荷清晨 · 亮」。
- **壁纸功能**：顶栏 🖼 菜单上传用户图片（PIL 裁剪铺满 + 缓存）作为**侧栏背景**，
  可一键清除恢复渐变；PIL 缺失时优雅降级。
- 侧栏导航改为 **Canvas 自绘**：渐变/壁纸背景 + hover 高亮 + 选中强调，随窗口重绘。

### Fixed
- 主题切换改为「先建后销」，消除窗口期悬挂引用导致的 TclError。
- 补回重构中丢失的 _highlight_nav/_active_key 初始化。

### Tests
- 75 项 pytest（新增清新配色断言/壁纸设置回读）。

## [3.2.0] - 2026-11-01

### Added
- **主题系统**：6 套配色方案（深空蓝/极光绿/暮光紫 · 暗，晨曦蓝/蜜橙/玫瑰 · 亮），
  顶栏 🎨 菜单一键切换；**渐变色为主视觉**——顶栏品牌横向渐变、侧栏导航纵向渐变、
  每页页头 accent 渐变带（widgets.GradientFrame，随窗口尺寸重绘）。
- **设置持久化**：netforge_settings.json 记忆主题/REST 端口/最近工作区（lib/settings.py）。
- 设备清单**一键在线检测**：并发 ping 清单设备，状态徽章（在线/离线）回填表格。
- 控制器页新增**下发审计查看**（netforge_audit.log 最近 30 条）。

### Changed
- 页面颜色引用全部迁移到 `theme.*` 动态访问（支持主题热切换整体重建）。
- 工具箱表格复用 `widgets.make_table`（斑马纹统一）。

### Fixed
- 生成页启动崩溃、意图 IP 校验、CDP/H3C 拓扑解析、alive 显示 None 等多处（见 3.1.0 后续修复）。

### Tests
- 75 项 pytest（新增主题切换×6/亮色令牌/设置持久化/在线检测 mock/审计查看冒烟）。

## [3.1.0] - 2026-11-01

### Added
- **工程化重构**：迁移到 src 布局（`src/netforge/`），页面拆分为
  `netforge/pages/*` 模块（注册表驱动导航），`main.py` 薄入口；
  pyproject 按 src 打包，GitHub Actions CI（ruff + pytest，Win/Ubuntu 矩阵）
  与 Build EXE 工作流。
- **UI 云控制台风格重设计**：`theme.py` 设计令牌（暗/亮两套，状态色语义化）
  与 `widgets.py` 组件库（Card / StatCard / page_header / DataTable 斑马纹 /
  EmptyState）；侧栏 hover 反馈 + 选中强调色 + 加粗，顶栏品牌强调线与
  时间显示，底部状态就绪提示。
- **多轮 GUI 冒烟测试**：全页循环 ×2、厂商过滤联动、巡检 9 方案切换、
  子网计算/密码生成真实执行、意图 Dry-Run、REST 生命周期（启动→health→停止）。
- 巡检方案扩至 9 套（含 VXLAN+EVPN / MPLS·SR / 堆叠M-LAG / RoCEv2 / IPv6）。
- 模板库扩至 105 个（IPv6 全家桶：SLAAC/无状态与有状态 DHCPv6/隧道/NAT64/SRv6）。
- 控制器中心：意图编排（5 类 × 4 厂商）+ Dry-Run 防呆 + 审计 + REST 北向。

### Fixed
- 生成页启动崩溃（厂商过滤早于模板预览框创建）。
- 意图邻居地址/IP 校验仅查形状不查数值范围（改用 ipaddress）。
- 拓扑解析器：华为 GE 接口归一化、CDP 列切分（Capability 含空格导致漏配对）、
  H3C "Interface" 前缀行匹配。

### Tests
- 68 项 pytest（单元 + GUI 冒烟 + REST 端到端）；ruff 全绿。

## [3.0.0] - 2026-10-31

### Added
- 控制器中心（ODL 思路极简实现）：意图编排 / Dry-Run / 审计 / REST 北向 / 拓扑发现。
- 模板库 92 个（移植 NetPilot 26 类场景 × 3 厂商 + SR-MPLS/DC 基线）。
- 巡检方案 8 套（VXLAN+EVPN / MPLS·SR / 堆叠M-LAG / RoCEv2）。

## [2.0.0] - 2026-10-31

### Added
- 独立完整平台：设备清单中心（DPAPI）、SSH 批量巡检、配置生成、工具箱。
- 移除外部模块启动器思路。

## [1.0.0] - 2026-10-31

### Added
- 首个版本：平台壳 + 子网计算/端口扫描/在线检测/命令速查。
