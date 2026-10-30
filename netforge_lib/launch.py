"""launch.py — 外部模块发现与启动（NetPilot / NADT / Inspection / Traffic）。

发现规则：在 NetForge 所在目录及其兄弟目录里按候选清单找 exe / py 入口，
找到的第一个可执行方式生效；用户可用 netforge_modules.json 扩展自定义模块。
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import webbrowser
from dataclasses import dataclass, field


@dataclass
class ModuleCandidate:
    kind: str             # exe | python | python_web
    path: str             # exe 或 py 文件绝对路径
    args: list[str] = field(default_factory=list)
    note: str = ""


@dataclass
class ExternalModule:
    key: str              # netpilot / nadt / inspection / traffic
    name: str
    desc: str
    candidates: list[ModuleCandidate] = field(default_factory=list)

    @property
    def available(self) -> bool:
        return bool(self.candidates)


# 内置模块定义：candidates 顺序即优先级（exe 优先于源码）
KNOWN_MODULES = [
    {
        "key": "netpilot",
        "name": "NetPilot · NETCONF 控制台",
        "desc": "多厂商 NETCONF 图形化管理：读写下发配置、候选库、模板库、批量操作",
        "rel_paths": ["netconf-web"],
        "exe_names": ["NetPilot.exe"],
        "py_entry": "app.py",
        "web": True,
    },
    {
        "key": "nadt",
        "name": "NADT · 零配置开局",
        "desc": "ZTP 批量开局：模板渲染生成 .cfg、TFTP 服务器、DHCP option 66/67、U 盘包",
        "rel_paths": ["NADT"],
        "exe_names": ["NADT 2.0.exe", "NADT.exe"],
        "py_entry": "nadt2.py",
    },
    {
        "key": "inspection",
        "name": "Inspection Studio · 网络巡检",
        "desc": "SSH 批量巡检：异常标记、配置备份、环路/光功率/温度告警、报告中心",
        "rel_paths": ["network_A"],
        "exe_names": ["NetworkInspection.exe", "NetworkInspectionV6.exe"],
        "py_entry": "net_inspect_v6.py",
    },
    {
        "key": "traffic",
        "name": "Traffic Studio · 网关压测",
        "desc": "网关压力测试与诊断：TCP/UDP/SYN 负载、PPS/Mbps 实时曲线、ICMP/DNS 诊断",
        "rel_paths": ["test_A"],
        "exe_names": ["Traffic Studio 2.0.exe", "TrafficTest.exe"],
        "py_entry": None,       # 源码入口在子目录，通常直接用 exe
    },
]

CUSTOM_FILE = "netforge_modules.json"


def _first_existing(base: str, sub: str, names: list[str]) -> str | None:
    for name in names:
        for cand in (os.path.join(base, sub, name),
                     os.path.join(base, sub, "dist", name),
                     os.path.join(base, name)):
            if os.path.isfile(cand):
                return os.path.abspath(cand)
    return None


def discover_modules(base_dir: str | None = None) -> list[ExternalModule]:
    """扫描 NetForge 同级目录，返回全部内置模块及其可用启动方式。"""
    base = base_dir or (os.path.dirname(os.path.abspath(sys.argv[0]))
                        if getattr(sys, "frozen", False)
                        else os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    modules: list[ExternalModule] = []
    for spec in KNOWN_MODULES:
        mod = ExternalModule(key=spec["key"], name=spec["name"], desc=spec["desc"])
        for rel in spec["rel_paths"]:
            exe = _first_existing(base, rel, spec["exe_names"])
            if exe:
                mod.candidates.append(ModuleCandidate("exe", exe, note="打包版"))
                break
        if not mod.candidates:
            for rel in spec["rel_paths"]:
                entry = spec.get("py_entry")
                if entry:
                    py = os.path.join(base, rel, entry)
                    if os.path.isfile(py):
                        mod.candidates.append(
                            ModuleCandidate("python_web" if spec.get("web") else "python", py))
                        break
        modules.append(mod)
    return modules


def load_custom_modules(base_dir: str | None = None) -> list[ExternalModule]:
    """读取 netforge_modules.json 里的自定义模块。

    格式：{"modules": [{"name": "...", "desc": "...", "path": "exe或py路径",
                        "web": false, "args": []}]}
    路径支持相对（相对 NetForge 目录）。
    """
    base = base_dir or (os.path.dirname(os.path.abspath(sys.argv[0]))
                        if getattr(sys, "frozen", False)
                        else os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    path = os.path.join(base, CUSTOM_FILE)
    out: list[ExternalModule] = []
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return out
    for m in data.get("modules", []):
        rel = str(m.get("path", ""))
        full = rel if os.path.isabs(rel) else os.path.join(base, rel)
        if not os.path.isfile(full):
            continue
        kind = "python_web" if m.get("web") else ("exe" if full.lower().endswith(".exe") else "python")
        out.append(ExternalModule(
            key="custom:" + os.path.basename(full),
            name=str(m.get("name") or os.path.basename(full)),
            desc=str(m.get("desc", "")),
            candidates=[ModuleCandidate(kind, full,
                                        args=[str(a) for a in (m.get("args") or [])])],
        ))
    return out


def launch(candidate: ModuleCandidate) -> str:
    """启动一个模块，返回面向用户的描述。

    * exe       → subprocess.Popen 独立进程
    * python    → sys.executable（开发模式）或 pythonw 启动 .py
    * python_web→ 启动后延迟打开浏览器（由调用方轮询 health，或直接开浏览器）
    """
    if candidate.kind == "exe":
        subprocess.Popen([candidate.path, *candidate.args], cwd=os.path.dirname(candidate.path),
                         creationflags=getattr(subprocess, "DETACHED_PROCESS", 0))
        return f"已启动: {os.path.basename(candidate.path)}"
    launcher = sys.executable if not getattr(sys, "frozen", False) else \
        os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
    subprocess.Popen([launcher, *candidate.args, candidate.path],
                     cwd=os.path.dirname(candidate.path),
                     creationflags=getattr(subprocess, "CREATE_NEW_CONSOLE", 0))
    if candidate.kind == "python_web":
        webbrowser.open("http://127.0.0.1:8000")
        return f"已启动: {os.path.basename(candidate.path)}（浏览器将打开 http://127.0.0.1:8000）"
    return f"已启动: {os.path.basename(candidate.path)}"
