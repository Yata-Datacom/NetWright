# 贡献指南（Contributing to NetWright）

感谢关注 NetWright！欢迎 Issue 与 PR。

## 开发环境

```bash
git clone https://github.com/Yata-Datacom/NetWright.git
cd NetWright
python -m venv .venv
.venv/Scripts/pip install -e ".[dev]"     # Windows；Linux/macOS 用 .venv/bin/pip
```

`[dev]` 附加依赖：pytest / ruff / pillow / pyinstaller（定义在 `pyproject.toml` 的
`[project.optional-dependencies]`）。

## 常用命令

```bash
python main.py                 # 启动
pytest tests/ -q               # 全量测试（GUI 冒烟在无显示环境自动跳过）
ruff check src tests main.py   # 核心规则 lint
pyinstaller NetWright.spec --noconfirm   # 打包 exe
python tools/make_icon.py      # 重新生成图标（改了设计才需要跑）
```

## 提交规范

- 提交信息：`feat: ...` / `fix: ...` / `docs: ...` / `perf: ...` / `refactor: ...`
- 破坏性改动加 `!`（如 `feat!:`）并在 CHANGELOG 里写清迁移方式
- 每个 PR 保持单一主题；UI 改动请附前后截图

## 代码约定

- **业务与 UI 分层**：业务逻辑放 `src/netwright/lib/` 与 `src/netwright/sdn/`
  （纯函数优先，可单测）；页面只做装配与展示（`src/netwright/pages/`）
- **控制器内核**（`sdn/`）只通过 `SouthboundAdapter` 契约碰设备；
  新增协议 = 新增一个适配器 + 在 `southbound/__init__.py` 注册一行
- **南向骨架必须先声明能力再实现**：没实现的路径要抛 `UnsupportedOperation`，
  绝不能静默返回空结果（上层会误判"下发成功"）
- **颜色/间距/字号必须来自 `theme.py` 令牌**，组件内禁止硬编码
  `#hex` 与 8px 网格外的间距
- **状态色语义**：success=稳定/完成，warning=降级/待复核，danger=阻断/失败；
  状态必须同时有文字标签，不能只靠颜色
- 每个公开函数写 docstring（参数/返回/异常）；易错逻辑加行内注释说明"为什么"
- 新功能必须带测试；修复 bug 先写复现测试再修

## 测试约定

- 测试**绝不写仓库真实数据目录**（`conftest.isolated_data` 会把数据目录重定向到 tmp）
- 凭据一律使用虚构数据（192.0.2.x 文档网段 / `Demo@123`）
- GUI 冒烟用例通过 `conftest.app` 共享单实例，无显示环境自动跳过
- 需要"看起来有东西"的界面测试，用 `netwright.demo.seed()` 载入演示数据，别连真机

## 模板库贡献

在 `templates/cli/<场景>/<厂商>.cfg` 添加模板，并在 `templates/library.json`
登记（name/desc/vars）。要求：用占位值渲染**零残留**（CI 会校验）。

## 发布流程

1. 更新 `src/netwright/__init__.py` 与 `pyproject.toml` 的版本号（CI 会比对）
2. 在 `CHANGELOG.md` 顶部加与版本号一致的条目（CI 会检查）
3. 打 tag：`git tag v3.10.0 && git push origin v3.10.0`
4. `Build EXE` 工作流会自动构建、算 SHA256、发布 Release
