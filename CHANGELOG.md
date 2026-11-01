# Changelog

本项目遵循 [语义化版本](https://semver.org/lang/zh-CN/) 与
[Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/) 格式。

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
