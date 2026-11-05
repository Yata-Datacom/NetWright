"""检查版本一致性：__init__.py / pyproject.toml / CHANGELOG 顶部。"""
from __future__ import annotations

import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def init_version() -> str:
    text = open(os.path.join(ROOT, "src", "netwright", "__init__.py"),
                encoding="utf-8").read()
    match = re.search(r'__version__\s*=\s*"([^"]+)"', text)
    return match.group(1) if match else "?"


def pyproject_version() -> str:
    text = open(os.path.join(ROOT, "pyproject.toml"), encoding="utf-8").read()
    match = re.search(r'^version\s*=\s*"([^"]+)"', text, re.MULTILINE)
    return match.group(1) if match else "?"


def changelog_top() -> str:
    text = open(os.path.join(ROOT, "CHANGELOG.md"), encoding="utf-8").read()
    match = re.search(r'^## \[([^\]]+)\]', text, re.MULTILINE)
    return match.group(1) if match else "?"


def main() -> int:
    versions = {"__init__.py": init_version(), "pyproject.toml": pyproject_version(),
                "CHANGELOG.md": changelog_top()}
    unique = set(versions.values())
    if len(unique) == 1 and "?" not in unique:
        print(f"版本一致：{unique.pop()}")
        return 0
    print("版本不一致：")
    for name, version in versions.items():
        print(f"  {name}: {version}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
