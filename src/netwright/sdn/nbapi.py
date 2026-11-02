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


def _intent_action(store, body: dict, action: str) -> tuple[int, dict]:
    """意图生命周期的四个动作：plan / deploy / verify / rollback。"""
    if action == "plan":
        intent_key = str(body.get("intent_key") or "")
        params = body.get("params") or {}
        if not intent_key:
            return 400, {"ok": False, "message": "缺少 intent_key"}
        hosts = body.get("device_hosts")
        devices = store.inventory.devices
        if isinstance(hosts, list) and hosts:
            devices = [d for d in devices if d.host in hosts]
        try:
            runs = store.lifecycle.create(intent_key, params, devices)
            planned = [run for run in runs if store.lifecycle.plan(run)["ok"]]
        except Exception as exc:      # noqa: BLE001  生命周期错误统一 400
            return 400, {"ok": False, "message": str(exc)}
        return 200, {"ok": True, "runs": [run.to_dict() for run in planned],
                     "count": len(planned)}

    run_ids = body.get("run_ids")
    if not isinstance(run_ids, list) or not run_ids:
        return 400, {"ok": False, "message": "缺少 run_ids"}
    results = []
    for run_id in run_ids:
        run = store.lifecycle.get(str(run_id))
        if run is None:
            results.append({"run": run_id, "ok": False, "message": "找不到该运行记录"})
            continue
        try:
            if action == "deploy":
                outcome = store.lifecycle.deploy(run)
            elif action == "verify":
                outcome = store.lifecycle.verify(run)
            else:
                outcome = store.lifecycle.rollback(run)
        except Exception as exc:      # noqa: BLE001
            outcome = {"ok": False, "error": str(exc)}
        results.append({"run": run_id, "state": run.state, **outcome})
    ok = all(item.get("ok") for item in results)
    return (200 if ok else 422), {"ok": ok, "results": results}


def dispatch(store, method: str, path: str, body: dict | None = None,
             headers: dict | None = None) -> tuple[int, dict]:
    """执行一条 v2 请求；返回 (HTTP 状态码, JSON 载荷)。

    除 ``/api/v2/health`` 外都需要 API token（``Authorization: Bearer …``
    或 ``X-API-Token``）；控制器未配置 auth 时保持开放（便于单测与内嵌使用）。
    """
    parsed = urlparse(path)
    route = parsed.path.rstrip("/") or "/"
    query = parse_qs(parsed.query)
    body = body or {}
    headers = {str(k).lower(): v for k, v in (headers or {}).items()}
    method = (method or "GET").upper()

    if not route.startswith(API_PREFIX):
        return 404, {"ok": False, "message": "未知端点"}

    auth = getattr(store, "auth", None)
    if auth is not None and not auth.check(
            parsed.path,
            headers.get("authorization", ""),
            headers.get("x-api-token", "")):
        return 401, {"ok": False,
                     "message": "缺少或无效的 API token",
                     "hint": "请求头加 Authorization: Bearer <token>（GUI「REST API」页可查看）"}

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
        if route == "/intents/runs":
            limit = _int(query.get("limit"), 50, 1, 200)
            return 200, {"ok": True, "runs": store.lifecycle.snapshot(limit)}
        if route == "/sources":
            return 200, {"ok": True, **store.listener_status()}
        if route == "/backups":
            device = (query.get("device") or [""])[0]
            if not device:
                return 200, {"ok": True, **store.backup_summary()}
            if store.backups is None:
                return 503, {"ok": False, "message": "备份未启用"}
            entries = store.backups.history(device)
            return 200, {"ok": True, "device": device,
                         "entries": [e.to_dict() for e in entries]}
        if route == "/backups/diff":
            device = (query.get("device") or [""])[0]
            if not device or store.backups is None:
                return 400, {"ok": False, "message": "需要 device 参数且备份已启用"}
            try:
                text = store.backups.diff(device,
                                          (query.get("old") or [None])[0],
                                          (query.get("new") or [None])[0])
            except ValueError as exc:
                return 400, {"ok": False, "message": str(exc)}
            return 200, {"ok": True, "device": device, "diff": text}
        return 404, {"ok": False, "message": "未知端点"}

    if method == "POST":
        if route == "/backups":
            if store.backups is None:
                return 503, {"ok": False, "message": "备份未启用"}
            hosts = body.get("device_hosts")
            devices = list(store.inventory.devices)
            if isinstance(hosts, list) and hosts:
                devices = [d for d in devices if d.host in hosts]
            if not devices:
                return 404, {"ok": False, "message": "没有匹配的设备"}
            if len(devices) > 50:
                return 400, {"ok": False, "message": "单次最多备份 50 台（分批调用）"}
            results = []
            for device in devices:
                try:
                    entry = store.backup_device(device)
                    results.append({"device": device.display_name, "ok": True, **entry})
                except Exception as exc:      # noqa: BLE001  单台失败不影响其他设备
                    results.append({"device": device.display_name, "ok": False,
                                    "error": str(exc)})
            ok = all(item["ok"] for item in results)
            return (200 if ok else 207), {"ok": ok, "results": results}
        if route == "/sources/start":
            try:
                store.start_syslog(body.get("syslog_port"))
                store.start_snmp_trap(body.get("trap_port"))
            except OSError as exc:
                return 400, {"ok": False, "message": f"端口不可用：{exc}"}
            return 200, {"ok": True, **store.listener_status()}
        if route == "/sources/stop":
            return 200, {"ok": True, **store.stop_listeners()}
        if route == "/policies/compile":
            return _compile(store, body)
        if route.startswith("/intents/"):
            action = route[len("/intents/"):]
            if action in ("plan", "deploy", "verify", "rollback"):
                return _intent_action(store, body, action)
            return 404, {"ok": False, "message": "未知端点"}
        if route == "/topology/sync":
            graph = store.sync_inventory()
            return 200, {"ok": True, **graph.to_dict()}
        return 404, {"ok": False, "message": "未知端点"}

    return 405, {"ok": False, "message": "不支持的 HTTP 方法"}
