# 贡献指南（Contributing to NetWright）

感谢关注 NetWright！欢迎 Issue 与 PR。

## 开发环境

```bash
git clone <你的 fork>
cd NetWright
python -m venv .venv
.venv/Scripts/pip install -e ".[dev]"    # Windows；Linux/macOS 用 .venv/bin/pip
```

`[dev]` 附加依赖：pytest / ruff / openpyxl。

## 常用命令

```bash
python main.py                 # 启动
pytest tests/ -v               # 全量测试（含 GUI 冒烟）
ruff check --select E4,E7,E9,F src tests main.py   # 核心规则 lint
pyinstaller NetWright.spec --noconfirm            # 打包 exe
```

## 提交规范

- 提交信息：`feat: ...` / `fix: ...` / `docs: ...` / `perf: ...` / `refactor: ...`
- 每个 PR 保持单一主题；UI 改动请附前后截图

## 代码约定

- **业务与 UI 分层**：业务逻辑放 `src/netwright/lib/`（纯函数优先，可单测）；
  页面只做装配与展示（`src/netwright/pages/`）
- **颜色/间距/字号必须来自 `theme.py` 令牌**，组件内禁止硬编码
  `#hex` 与 8px 网格外的间距
- **状态色语义**：success=稳定/完成，warning=降级/待复核，danger=阻断/失败；
  状态必须同时有文字标签，不能只靠颜色
- 每个公开函数写 docstring（参数/返回/异常）；易错逻辑加行内注释说明"为什么"
- 新功能必须带测试；修复 bug 先写复现测试再修

## 测试约定

- 测试**绝不写仓库真实数据目录**（conftest 会自动比对前后快照）
- 凭据一律使用虚构数据（192.0.2.x 文档网段 / Demo 密码）
- GUI 冒烟用例通过 `conftest.app` 共享单实例，无显示环境自动跳过
- 修 bug 流程：先写复现测试 → 修复 → 确认全量通过

## 模板库贡献

在 `templates/cli/<场景>/<厂商>.cfg` 添加模板，并在 `templates/library.json`
登记（name/desc/vars）。要求：用占位值渲染**零残留**（CI 会校验）。
