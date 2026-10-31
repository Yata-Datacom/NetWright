"""restapi.py — 控制器北向 REST API（标准库 ThreadingHTTPServer）。

端点（默认 127.0.0.1:8899，只监听本机）：
  GET  /api/health                 健康检查
  GET  /api/devices                设备清单（密码打码）
  GET  /api/intents                意图目录（含表单字段定义）
  GET  /api/topology               LLDP 拓扑（异步触发发现后返回缓存）
  POST /api/dry-run                {intent_key, intent, device_hosts:[...]} → 渲染计划
  POST /api/apply                  同上 + {"confirm": true} 才会真实下发
"""
from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from ..inventory import Device
from . import deploy, intents as intents_mod


class ControllerState:
    """控制器共享状态：清单 + 拓扑缓存。"""

    def __init__(self, inventory):
        self.inventory = inventory
        self.topology = None  # 最近一次发现的 Topology

    def devices_by_hosts(self, hosts: list[str] | None) -> list[Device]:
        if not hosts:
            return list(self.inventory.devices)
        return [d for d in self.inventory.devices if d.host in hosts]


def make_handler(state: ControllerState) -> type:
    class Handler(BaseHTTPRequestHandler):
        server_version = "NetForgeController/1.0"

        def _json(self, obj, status=200):
            body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, fmt, *args):  # 静默
            pass

        def do_GET(self):
            path = self.path.split("?")[0]
            if path == "/api/health":
                return self._json({"ok": True, "service": "netforge-controller"})
            if path == "/api/devices":
                devs = [{"hostname": d.display_name, "host": d.host, "port": d.port,
                         "vendor": d.vendor, "username": d.username,
                         "password": "••••••" if d.password else ""}
                        for d in state.inventory.devices]
                return self._json({"ok": True, "devices": devs})
            if path == "/api/intents":
                return self._json({"ok": True, "intents": intents_mod.list_intents()})
            if path == "/api/topology":
                if state.topology is None:
                    return self._json({"ok": False, "message": "拓扑尚未发现，请先在界面或 /api/topology/discover 触发"},
                                      404)
                edges = state.topology.undirected_edges()
                return self._json({"ok": True,
                                   "nodes": sorted(state.topology.nodes),
                                   "links": [{"a": e[0], "a_intf": e[1],
                                              "b": e[2], "b_intf": e[3]} for e in edges]})
            return self._json({"ok": False, "message": "未知端点"}, 404)

        def do_POST(self):
            path = self.path.split("?")[0]
            try:
                length = int(self.headers.get("Content-Length") or 0)
                payload = json.loads(self.rfile.read(length) or b"{}")
            except ValueError:
                return self._json({"ok": False, "message": "JSON 解析失败"}, 400)

            if path == "/api/dry-run":
                try:
                    devices = state.devices_by_hosts(payload.get("device_hosts"))
                    plan = deploy.dry_run(payload.get("intent_key", ""),
                                          payload.get("intent", {}), devices)
                    return self._json({"ok": True, **plan})
                except ValueError as e:
                    return self._json({"ok": False, "message": str(e)}, 400)

            if path == "/api/apply":
                if payload.get("confirm") is not True:
                    return self._json({"ok": False, "message":
                                       "这是真实下发接口。请在请求体加 \"confirm\": true，"
                                       "或先调 /api/dry-run 预览"}, 400)
                try:
                    devices = state.devices_by_hosts(payload.get("device_hosts"))
                    result = deploy.apply(payload.get("intent_key", ""),
                                          payload.get("intent", {}), devices)
                    return self._json({"ok": True, **result})
                except ValueError as e:
                    return self._json({"ok": False, "message": str(e)}, 400)

            return self._json({"ok": False, "message": "未知端点"}, 404)

    return Handler


class ControllerAPI:
    """REST 服务封装（可启停，GUI 用）。"""

    def __init__(self, state: ControllerState, host: str = "127.0.0.1", port: int = 8899):
        self.state = state
        self.host, self.port = host, port
        self._server: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None

    def start(self):
        if self._server:
            return
        self._server = ThreadingHTTPServer((self.host, self.port), make_handler(self.state))
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()

    def stop(self):
        if self._server:
            self._server.shutdown()
            self._server.server_close()
            self._server = None

    @property
    def running(self) -> bool:
        return self._server is not None
