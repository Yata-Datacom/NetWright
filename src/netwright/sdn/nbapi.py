"""nbapi.py — 北向 REST v2（控制器语义接口）。

与 v1（``lib/controller/restapi.py`` 的 /api/devices、/api/dry-run…）并存：
v1 面向"把现有功能脚本化"，v2 面向"把控制器当平台用"。

路由表（全部挂在 127.0.0.1，鉴权留待 v3）：

  GET  /api/v2/health              健康与版本
  GET  /api/v2/snapshot            一次性拉全量（UI/脚本启动用）
  GET  /api/v2/topology            控制器图（节点/链路/统计）
  GET  /api/v2/events?limit=&severity=
  GET  /api/v2/policies            最近编译的策略
  GET  /api/v2/intents             意图目录
  GET  /api/v2/southbound          南向适配器与能力位
  POST /api/v2/policies/compile    {intent_key, params, device_hosts?}
  POST /api/v2/topology/sync       设备清单 → 图
"""
from __future__ import annotations

from urllib.parse import parse_qs, urlparse

API_PREFIX = "/api/v2"
VERSION = "2.0"


def _events(store, query: dict) -> dict:
    limit = _int(query.get("limit"), 50, 1, 500)
    severity = (query.get("severity") or [""])[0]
    items = store.bus.snapshot(limit=limit, min_severity=severity or None)
    return {"ok": True, "events": [e.to_dict() for e in items],
            "counts": store.bus.counts()}


def _compile(store, body: dict) -> tuple[int, dict]:
    intent_key = str(body.get("intent_key") or "")
    params = body.get("params") or {}
    if not intent_key:
        return 400, {"ok": False, "message": "缺少 intent_key"}
    if not isinstance(params, dict):
        return 400, {"ok": False, "message": "params 必须是对象"}
    hosts = body.get("device_hosts")
    devices = store.inventory.devices
    if isinstance(hosts, list) and hosts:
        devices = [d for d in devices if d.host in hosts]
        if not devices:
            return 404, {"ok": False, "message": "没有匹配的设备"}
    try:
        result = store.compile(intent_key, params, devices)
    except ValueError as exc:
        return 400, {"ok": False, "message": str(exc)}
    return (200 if result.ok else 422), {"ok": result.ok, **result.to_dict()}


def _int(raw, default: int, lo: int, hi: int) -> int:
    try:
        value = int(raw[0] if isinstance(raw, list) else raw)
    except (TypeError, ValueError):
        return default
    return max(lo, min(hi, value))


def dispatch(store, method: str, path: str, body: dict | None = None) -> tuple[int, dict]:
    """执行一条 v2 请求；返回 (HTTP 状态码, JSON 载荷)。"""
    parsed = urlparse(path)
    route = parsed.path.rstrip("/") or "/"
    query = parse_qs(parsed.query)
    body = body or {}
    method = (method or "GET").upper()

    if not route.startswith(API_PREFIX):
        return 404, {"ok": False, "message": "未知端点"}
    route = route[len(API_PREFIX):] or "/"

    if method == "GET":
        if route in ("/health", "/"):
            return 200, {"ok": True, "service": "netwright-controller",
                         "api": VERSION, **store.summary()}
        if route == "/snapshot":
            return 200, {"ok": True, **store.snapshot()}
        if route == "/topology":
            return 200, {"ok": True, **store.graph.to_dict()}
        if route == "/events":
            return 200, _events(store, query)
        if route == "/policies":
            limit = _int(query.get("limit"), 50, 1, 200)
            return 200, {"ok": True,
                         "policies": [p.to_dict() for p in store.recent_policies(limit)]}
        if route == "/intents":
            return 200, {"ok": True, "intents": store.compiler.catalog()}
        if route == "/southbound":
            return 200, {"ok": True, "adapters": store.registry.describe()}
        return 404, {"ok": False, "message": "未知端点"}

    if method == "POST":
        if route == "/policies/compile":
            return _compile(store, body)
        if route == "/topology/sync":
            graph = store.sync_inventory()
            return 200, {"ok": True, **graph.to_dict()}
        return 404, {"ok": False, "message": "未知端点"}

    return 405, {"ok": False, "message": "不支持的 HTTP 方法"}
