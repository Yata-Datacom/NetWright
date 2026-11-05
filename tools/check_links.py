"""检查 Markdown 里的相对链接是否都存在（发布前跑一次，避免文档死链）。"""
from __future__ import annotations

import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LINK_RE = re.compile(r"\[[^\]]*\]\(([^)]+)\)")
SKIP_PREFIX = ("http://", "https://", "mailto:", "#")


def markdown_files() -> list[str]:
    files = []
    for base, _dirs, names in os.walk(ROOT):
        if ".git" in base or ".venv" in base or "__pycache__" in base:
            continue
        for name in names:
            if name.endswith(".md"):
                files.append(os.path.join(base, name))
    return files


def check(path: str) -> list[tuple[str, str]]:
    broken = []
    with open(path, encoding="utf-8") as handle:
        text = handle.read()
    for target in LINK_RE.findall(text):
        target = target.strip().split(" ")[0]
        if not target or target.startswith(SKIP_PREFIX):
            continue
        anchor = target.split("#")[0]
        if not anchor:
            continue
        resolved = os.path.normpath(os.path.join(os.path.dirname(path), anchor))
        if not os.path.exists(resolved):
            broken.append((target, os.path.relpath(path, ROOT)))
    return broken


def main() -> int:
    files = markdown_files()
    problems = []
    for path in files:
        problems.extend(check(path))
    if not problems:
        print(f"OK：{len(files)} 个 Markdown 文件，没有死链")
        return 0
    print(f"发现 {len(problems)} 个死链：")
    for target, source in problems:
        print(f"  {source} → {target}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
