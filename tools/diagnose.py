"""环境自检 CLI：打包后出问题先跑这个。

用法：
    NetWright.exe 打不开时，先看窗口是否出现；
    源码运行：.venv\\Scripts\\python.exe tools\\diagnose.py
"""
from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from netwright.lib.selfcheck import run_checks, summarize  # noqa: E402


def main() -> int:
    checks = run_checks()
    ok, line = summarize(checks)
    width = max(len(c["name"]) for c in checks) + 2
    print("NetWright 环境自检")
    print("=" * 60)
    for check in checks:
        mark = "OK  " if check["ok"] else "FAIL"
        print(f"[{mark}] {check['name']:<{width}} {check['detail']}")
        if not check["ok"] and check["hint"]:
            print(" " * 8 + "→ " + check["hint"])
    print("=" * 60)
    print(line)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
