"""冷启动基准（R11 / R12）：页面构建与首次显示各花多少毫秒。

用法：
    .venv\\Scripts\\python.exe tools\\bench_startup.py [--runs 5]
    python tools\\bench_startup.py --exe dist\\NetWright.exe   # 打包产物（进程启动→窗口可见）

源码模式下输出：
    construct_ms   累计花在 PAGE_REGISTRY 页面构造函数里的毫秒数
    first_show_ms  应用启动后第一次 show(...) 的毫秒数（含按需构建当前页）
    total_ms       NetWrightApp() 构造总耗时
    pages_built    启动过程中实际构建的页面数（R11 前 = 12，R11 后应 <= 2）
"""
from __future__ import annotations

import argparse
import os
import statistics
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)


def bench_once() -> dict:
    """构建一次 NetWrightApp，返回分项耗时（毫秒）。"""
    import tkinter as tk

    from netwright import app as app_mod
    from netwright.pages import PAGE_REGISTRY

    timings = {"construct_ms": 0.0, "first_show_ms": 0.0, "pages_built": 0}
    real_show = app_mod.NetWrightApp.show
    real_inits = {key: cls.__init__ for key, (_l, _i, cls) in PAGE_REGISTRY.items()}
    state = {"shown": False}

    def timed_show(self, key):
        t0 = time.perf_counter()
        real_show(self, key)
        cost = (time.perf_counter() - t0) * 1000
        if not state["shown"]:
            timings["first_show_ms"] = cost
            state["shown"] = True

    app_mod.NetWrightApp.show = timed_show
    for key, (_l, _i, cls) in PAGE_REGISTRY.items():
        def timed_init(self, master, app, _init=real_inits[key]):
            t0 = time.perf_counter()
            _init(self, master, app)
            timings["construct_ms"] += (time.perf_counter() - t0) * 1000
            timings["pages_built"] += 1

        cls.__init__ = timed_init

    try:
        t0 = time.perf_counter()
        app = app_mod.NetWrightApp()
        timings["total_ms"] = (time.perf_counter() - t0) * 1000
        app.withdraw()
    finally:
        app_mod.NetWrightApp.show = real_show
        for key, (_l, _i, cls) in PAGE_REGISTRY.items():
            cls.__init__ = real_inits[key]
    try:
        app.destroy()
    except tk.TclError:
        pass
    return timings


def bench_exe(exe_path: str) -> None:
    """打包产物模式：进程启动 → 主窗口可见的毫秒数（轮询窗口句柄）。

    方法：启动 exe 后用 Win32 FindWindowW 每 20ms 轮询一次标题，
    窗口出现即视为"可见"（与人工秒表的"看到窗口"同口径）。
    """
    import ctypes
    import subprocess

    exe_path = os.path.abspath(exe_path)
    if not os.path.isfile(exe_path):
        sys.exit(f"找不到 exe：{exe_path}")
    t0 = time.perf_counter()
    proc = subprocess.Popen([exe_path])
    try:
        while time.perf_counter() - t0 < 60:
            if ctypes.windll.user32.FindWindowW(None, "NetWright SDN Console"):
                elapsed = (time.perf_counter() - t0) * 1000
                print(f"exe cold start → window visible: {elapsed:.0f} ms")
                return
            if proc.poll() is not None:
                sys.exit(f"exe 提前退出，code={proc.returncode}")
            time.sleep(0.02)
        sys.exit("60 秒内未等到主窗口")
    finally:
        time.sleep(0.3)
        proc.terminate()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--runs", type=int, default=5,
                        help="源码模式重复次数（取中位数），默认 5")
    parser.add_argument("--exe", help="打包产物路径：测进程启动到窗口可见")
    args = parser.parse_args()

    if args.exe:
        bench_exe(args.exe)
        return

    rows = [bench_once() for _ in range(max(1, args.runs))]
    med = {k: statistics.median(r[k] for r in rows) for k in rows[0]}
    print(f"runs={len(rows)}")
    print(f"construct_ms={med['construct_ms']:.0f}  "
          f"first_show_ms={med['first_show_ms']:.0f}  "
          f"total_ms={med['total_ms']:.0f}  "
          f"pages_built={med['pages_built']:.0f}")
    print("（每轮明细）")
    for r in rows:
        print(f"  construct_ms={r['construct_ms']:.0f}  "
              f"first_show_ms={r['first_show_ms']:.0f}  "
              f"total_ms={r['total_ms']:.0f}  pages_built={r['pages_built']}")


if __name__ == "__main__":
    main()
