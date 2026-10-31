# -*- coding: utf-8 -*-
"""把 NetPilot（netconf-web）的 26 类 CLI 模板库移植到 NetForge templates/cli/。

用法：python tools/import_cli_templates.py
读取 ../netconf-web/config_templates.py，逐类逐厂商写出 .cfg（带场景头注释），
并把条目合并进 templates/library.json（按 file 路径去重）。
"""
from __future__ import annotations

import importlib.util
import json
import os
import sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(os.path.dirname(BASE), "netconf-web", "config_templates.py")

spec = importlib.util.spec_from_file_location("nwf_templates", SRC)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

sys.path.insert(0, BASE)
from netforge_lib.generator import template_variables  # noqa: E402

VENDOR_LABEL = {"huawei": "华为 VRP", "h3c": "新华三 Comware", "cisco": "思科 IOS-XE/NX-OS"}
STD_VARS_NOTE = "标准变量 hostname/mgmt_vlan/mgmt_ip/mask/gateway/access_vlan/vlan_batch 视模板使用情况填写"

out_dir = os.path.join(BASE, "templates", "cli")
os.makedirs(out_dir, exist_ok=True)

lib_path = os.path.join(BASE, "templates", "library.json")
with open(lib_path, encoding="utf-8") as f:
    library = json.load(f)

existing_files = {e["file"] for e in library["templates"]}
added = 0

for key, cat in mod.TEMPLATE_CATEGORIES.items():
    cat_dir = os.path.join(out_dir, key)
    os.makedirs(cat_dir, exist_ok=True)
    for vendor, content in cat["templates"].items():
        fname = f"{key}/{vendor}.cfg"
        rel = f"cli/{fname}"
        header = (
            f"# ============================================================\n"
            f"# NetForge 内置模板 — {cat['title']} · {VENDOR_LABEL.get(vendor, vendor)}\n"
            f"# 场景: {cat['desc']}\n"
            f"# 模板变量（除标准字段外）: {', '.join(template_variables(content)) or '（见模板内注释）'}\n"
            f"# {STD_VARS_NOTE}\n"
            f"# ============================================================\n")
        with open(os.path.join(out_dir, fname), "w", encoding="utf-8", newline="\n") as f:
            f.write(header + content.rstrip() + "\n")
        if rel not in existing_files:
            vars_ = template_variables(content)
            std = {"hostname", "mgmt_vlan", "mgmt_ip", "mask", "gateway",
                   "access_vlan", "vlan_batch", "sysname"}
            library["templates"].append({
                "file": rel,
                "vendor": vendor,
                "name": f"{cat['title']} · {VENDOR_LABEL.get(vendor, vendor)}",
                "desc": cat["desc"],
                "vars": [v for v in vars_ if v not in std],
            })
            existing_files.add(rel)
            added += 1

with open(lib_path, "w", encoding="utf-8") as f:
    json.dump(library, f, ensure_ascii=False, indent=2)
    f.write("\n")

print(f"已写出 {sum(len(c['templates']) for c in mod.TEMPLATE_CATEGORIES.values())} 个模板文件，"
      f"library.json 新增 {added} 条，总计 {len(library['templates'])} 条")
