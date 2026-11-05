"""README 体积守卫：防止再次出现超大文件/超长行（历史事故：597KB 重复内容）。

用法：python tools/check_readme.py
"""
from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MAX_CHARS = 60_000
MAX_LINE = 300


def main() -> int:
    path = os.path.join(ROOT, "README.md")
    text = open(path, encoding="utf-8").read()
    longest = max((len(line) for line in text.splitlines()), default=0)
    problems = []
    if len(text) >= MAX_CHARS:
        problems.append(f"字符数 {len(text)} 超过 {MAX_CHARS}")
    if longest >= MAX_LINE:
        problems.append(f"最长行 {longest} 超过 {MAX_LINE}")
    if problems:
        print("README 守卫失败：" + "；".join(problems))
        return 1
    print(f"README OK：{len(text)} 字符，最长行 {longest}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
