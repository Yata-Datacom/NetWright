"""generator.py — 配置生成引擎：{{变量}} 模板 + 设备行 → 批量 .cfg。

独立于 NADT 的轻量实现：
  * render_template：{{var}} 替换 + 残留占位符检测（宁报错不下发坏配置）
  * parse_device_table：CSV 文本 → 设备行（首行表头 = 变量名）
  * generate：模板 × 设备表 → [(文件名, 内容)]
"""
from __future__ import annotations

import csv
import io
import os
import re
import sys

PLACEHOLDER_RE = re.compile(r"\{\{\s*([A-Za-z_]\w*)\s*\}\}")
LEFTOVER_RE = re.compile(r"\{\{[^}]*\}\}")

def _base_dir() -> str:
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))


TEMPLATE_DIR = os.path.join(_base_dir(), "templates")


def render_template(template_text: str, variables: dict[str, str]) -> str:
    """渲染模板；未提供的变量 → 抛 ValueError（列出缺失名），绝不输出字面占位符。"""
    def rep(m):
        key = m.group(1)
        if key not in variables:
            missing.append(key)
        return str(variables.get(key, ""))
    missing: list[str] = []
    out = PLACEHOLDER_RE.sub(rep, template_text)
    if missing:
        names = ", ".join(sorted(set(missing)))
        raise ValueError(f"缺少变量: {names}")
    leftovers = LEFTOVER_RE.findall(out)
    if leftovers:
        raise ValueError(f"模板存在无法识别的占位符: {leftovers[:5]}")
    return out


def template_variables(template_text: str) -> list[str]:
    """提取模板里的变量名（按出现顺序去重）。"""
    seen: list[str] = []
    for m in PLACEHOLDER_RE.finditer(template_text):
        if m.group(1) not in seen:
            seen.append(m.group(1))
    return seen


def parse_device_table(text: str) -> tuple[list[str], list[dict[str, str]]]:
    """解析 CSV 设备表：首行表头即变量名。返回 (变量列表, 设备字典列表)。"""
    rows = list(csv.reader(io.StringIO(text or "")))
    rows = [r for r in rows if any(str(c).strip() for c in r)]
    if not rows:
        raise ValueError("设备表为空（首行为表头，第二行起为设备）")
    header = [c.strip() for c in rows[0]]
    if not all(header):
        raise ValueError("表头存在空列名")
    devices = []
    for n, row in enumerate(rows[1:], start=2):
        dev = {}
        for i, key in enumerate(header):
            dev[key] = str(row[i]).strip() if i < len(row) else ""
        if any(dev.values()):
            devices.append(dev)
    return header, devices


def generate(template_text: str, devices: list[dict[str, str]],
             filename_rule: str = "hostname", extension: str = "cfg") -> list[tuple[str, str]]:
    """渲染全部设备 → [(文件名, 内容)]；文件名冲突/变量缺失立即报错。"""
    if not devices:
        raise ValueError("设备表没有数据行")
    variables_all = template_variables(template_text)
    results: list[tuple[str, str]] = []
    used: set[str] = set()
    for n, dev in enumerate(devices, start=1):
        missing = [v for v in variables_all if not str(dev.get(v, "")).strip()]
        if missing:
            raise ValueError(f"第 {n} 台设备缺少变量: {', '.join(missing)}")
        content = render_template(template_text, dev)
        base = str(dev.get(filename_rule, "")).strip() or f"device{n}"
        base = re.sub(r'[\\/:*?"<>|]+', "_", base)
        fname = f"{base}.{extension.lstrip('.')}"
        if fname.lower() in used:
            raise ValueError(f"文件名冲突: {fname}（请调整 filename_rule 或设备名）")
        used.add(fname.lower())
        results.append((fname, content))
    return results


def write_outputs(out_dir: str, files: list[tuple[str, str]], eol: str = "\r\n") -> int:
    os.makedirs(out_dir, exist_ok=True)
    n = 0
    for fname, content in files:
        if not content.endswith("\n"):
            content += "\n"
        with open(os.path.join(out_dir, fname), "w", encoding="utf-8", newline="") as f:
            f.write(content.replace("\r\n", "\n").replace("\n", eol))
        n += 1
    return n


_TPL_CACHE: dict[str, tuple[float, list[dict]]] = {}


def list_builtin_templates(base_dir: str | None = None) -> list[dict]:
    """内置模板库：templates/ 目录 + library.json（沿用 NADT 模板库格式）。

    按清单文件 mtime 缓存——116 个模板反复读取只在首次/变更后有 IO。
    """
    base = base_dir or _base_dir()
    manifest_path = os.path.join(base, "templates", "library.json")
    try:
        stamp = os.path.getmtime(manifest_path)
    except OSError:
        stamp = 0
    cached = _TPL_CACHE.get(base)
    if cached and cached[0] == stamp:
        return cached[1]
    tdir = os.path.join(base, "templates")
    manifest_path = os.path.join(tdir, "library.json")
    out: list[dict] = []
    try:
        import json
        with open(manifest_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        data = {}
    for entry in data.get("templates", []):
        rel = str(entry.get("file", "")).replace("\\", "/")
        if not rel or ".." in rel.split("/"):
            continue
        full = os.path.join(tdir, rel)
        if not os.path.isfile(full):
            continue
        try:
            with open(full, "r", encoding="utf-8") as f:
                text = f.read()
        except OSError:
            continue
        out.append({"file": rel, "vendor": entry.get("vendor", "generic"),
                    "name": entry.get("name", rel), "desc": entry.get("desc", ""),
                    "vars": template_variables(text), "text": text})
    _TPL_CACHE[base] = (stamp, out)
    return out
