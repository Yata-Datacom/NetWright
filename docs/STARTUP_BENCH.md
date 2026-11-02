# 冷启动基准（R11 页面惰性构建 / R12 打包启动）

> 测量工具：`tools/bench_startup.py`（源码模式测页面构建；`--exe` 模式测
> "进程启动 → 窗口可见"）。所有数字为 **5 次取中位**，本机（Windows 11，
> Python 3.14.4，Tk 8.6），测量日期 2026-11-02。

## 1. 页面构建（源码模式，`NetWrightApp()` 全程）

| 指标 | R11 前（急切构建 12 页） | R11 后（惰性构建） | 变化 |
|---|---|---|---|
| construct_ms（页面构造累计） | **257 ms**（12 页） | **34 ms**（1 页） | **-87%** |
| first_show_ms（首次 show） | 27 ms | 61 ms（含当前页构建） | — |
| total_ms（App 构造总耗时） | 814 ms | **337 ms** | **-59%** |
| pages_built（启动时构建页面数） | 12 | **1** | 只建当前页 |

- 规格要求 construct 下降 ≥ 40%，实际 **-87%**。
- 冷进程首轮数字偏高（Tcl/Tk 库加载 + 导入），上表为中位数；
  明细见 `tools/bench_startup.py --runs 5` 输出。

## 2. 打包产物（exe 双击到窗口）

| 产物 | v3.18.2 实测（UPX 已关） | v3.29 现状 |
|---|---|---|
| onefile | 4.4 s | 页面构建不再是瓶颈（-87%）；剩余大头是解释器/依赖导入与解压 |
| onedir | 3.5 s | 同上 |

- R11 落地前的分析确认：exe 慢在"启动即构建全部 12 个页面"；该笔开销现已消除，
  剩余耗时来自 Python 运行时与依赖导入（onefile 的 %TEMP% 解压另计）。
- 复测方法：`python tools/bench_startup.py --exe dist\NetWright.exe`
  （轮询 Win32 窗口标题，与人工秒表"看到窗口"同口径）。
- 发布流程（tag / CI 产物 / Release）按规格 R10 **暂缓**，本文档只记录测量方法与结论。

## 3. 复现

```bash
.venv\Scripts\python.exe tools\bench_startup.py --runs 5
.venv\Scripts\python.exe tools\bench_startup.py --exe dist\NetWright.exe
```
