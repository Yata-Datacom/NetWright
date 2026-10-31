# Changelog

本项目遵循 [语义化版本](https://semver.org/lang/zh-CN/) 与
[Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/) 格式。

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
