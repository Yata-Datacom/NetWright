# 发布清单（v4.0 起）

> 每次给出可交付版本（或正式发版）前按顺序过一遍，全部打勾才算完。

## 1. 代码

- [ ] `pytest -q` 全绿（当前基线：396 passed / 2 skipped）
- [ ] `ruff check src tests main.py tools` 无输出
- [ ] 版本三处一致：`src/netwright/__init__.py` / `pyproject.toml` / `CHANGELOG.md` 顶部
- [ ] `CHANGELOG.md` 有本次条目，未做的能力不写"已完成"

## 2. 打包

```powershell
powershell -ExecutionPolicy Bypass -File tools\build_all.ps1
```

- [ ] `dist\NetWright.exe`（单文件）与 `dist\NetWright\NetWright.exe`（目录版）都存在
- [ ] `dist\SHA256SUMS.txt` 已生成，内容与文件一致
- [ ] 双击目录版：**1 秒内**出窗口，标题版本号正确
- [ ] 双击单文件：2–3 秒出窗口（解压 + 杀软扫描，属预期）
- [ ] 程序能读到模板：配置生成页厂商下拉有内容（或跑自检看模板数）

## 3. 自检与接口

- [ ] `python tools\diagnose.py` → 8 项全过
- [ ] `GET /api/v4/health` 返回 ok（无需 token）
- [ ] `GET /api/v4/selfcheck` 带 token 能通
- [ ] 只读 token 访问写接口 → 403；无 token → 401

## 4. 数据与升级

- [ ] 用一份 v3 的 `netwright_settings.json` 启动 → 生成 `.bak`，设置项不丢
- [ ] 未知键（人为加一个 `future_key`）在启动后仍存在
- [ ] 备份目录可写、快照能 diff

## 5. 文档

- [ ] `python tools\check_links.py` → 无死链
- [ ] README 测试徽章与版本号同步
- [ ] `docs/RELEASE_NOTES.md` 补本次新增
- [ ] 用户指南对应章节已更新（新页面/新按钮）

## 6. 交付

- [ ] 给使用者的文件：`NetWright.exe` 或 `NetWright\` 目录 + `SHA256SUMS.txt`
- [ ] 说明升级方式（替换文件即可，数据不动）
- [ ] 说明回退方式（旧 exe + 设置 `.bak`）
- [ ] 截图（新页面）已更新 —— **当前仍缺，需交互式桌面**

## 已知缺口（v4.0.0）

- 截图未更新（`docs/screenshots/` 为 v3.9）
- 发布流水线（tag → GitHub Release）暂缓
- OpenFlow 实传输需自行安装 os-ken + 有 OVS 环境
