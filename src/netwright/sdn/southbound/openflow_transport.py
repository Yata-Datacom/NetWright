"""openflow_transport.py — OpenFlow 1.3 TCP 传输层（R5，os-ken 可选依赖）。

分工（延续 openflow.py 的"编码离线可测"思路）：
  * **openflow.py**：flow_mod 的校验与字节编码（零依赖，永远可用）；
  * **本模块**：TCP 通道——HELLO 握手、发送 flow_mod + barrier 确认、
    收取 PORT_STATUS。**os-ken 没装时不可用**（``available() is False``），
    不影响其它任何功能；装了才启用真实下发（需要 OVS / mininet 做对端）。

为什么通道本体用标准库 socket：flow_mod 字节已经由 openflow.py 编好，
传输层只做"发字节 + 等 Barrier Reply + 读包头"——这一层引入 os-ken 的
Datapath/Eventlet 反而把单机工具拖进事件循环。os-ken 在这里作为**能力闸门**
（与 OpenFlowAdapter.available() 的口径一致），不装就不能下发、但绝不崩。
"""
from __future__ import annotations

import importlib.util
import socket
import struct

OFP_VERSION_13 = 4
OFPT_HELLO = 0
OFPT_ERROR = 1
OFPT_BARRIER_REQUEST = 20
OFPT_BARRIER_REPLY = 21
OFPT_PORT_STATUS = 12

_OF_PORTS = (6633, 6653)          # 常用 OpenFlow 监听端口
_HEADER = struct.Struct("!BBHI")


class TransportError(RuntimeError):
    """传输层失败（连接 / 握手 / 交换机错误回复）。"""


def encode_hello(xid: int = 1) -> bytes:
    """OF1.3 HELLO（8 字节头，无 body）。"""
    return _HEADER.pack(OFP_VERSION_13, OFPT_HELLO, 8, xid)


def encode_barrier_request(xid: int) -> bytes:
    return _HEADER.pack(OFP_VERSION_13, OFPT_BARRIER_REQUEST, 8, xid)


def parse_port_status(payload: bytes) -> dict:
    """PORT_STATUS body → 摘要（reason + port_no），标准库即可解析。

    OF1.3 body：reason(1) + pad(7) + ofp_port(port_no u32 @ 8 …)。
    """
    reason = payload[0] if payload else None
    port_no = struct.unpack_from("!I", payload, 8)[0] if len(payload) >= 12 else None
    return {"reason": reason, "port_no": port_no, "size": len(payload)}


class OsKenTransport:
    """OF1.3 TCP 通道（同步、阻塞、单交换机单连接）。

    生命周期：``connect()`` → N × ``send_flow_mod()`` → ``close()``。
    线程模型：调用方自行放后台线程（与 CLI 适配器一致），本类不做内部锁。
    """

    protocol = "openflow"
    display_name = "OpenFlow 1.3 (os-ken)"

    def __init__(self, host: str = "127.0.0.1", port: int = 6653, timeout: float = 5.0):
        self.host = host
        self.port = int(port) if port else 6653
        self.timeout = float(timeout)
        self._sock: socket.socket | None = None
        self._xid = 0
        self._pending: list[dict] = []       # 非目标消息（PORT_STATUS 等）暂存

    # ── 能力闸门 ──
    @classmethod
    def available(cls) -> bool:
        """os-ken 是否安装（与 OpenFlowAdapter.available() 同口径）。"""
        return importlib.util.find_spec("os_ken") is not None

    @classmethod
    def install_hint(cls) -> str:
        return "pip install os-ken 后重启程序即可启用 OpenFlow 真实下发（可选依赖，不装不影响其它功能）"

    # ── 连接 ──
    def connect(self) -> dict:
        """TCP + HELLO 握手。失败抛 TransportError（绝不假装连上）。"""
        if not self.available():
            raise TransportError(f"未安装 os-ken：{self.install_hint()}")
        try:
            self._sock = socket.create_connection(
                (self.host, self.port), timeout=self.timeout)
            self._sock.settimeout(self.timeout)
            self._xid += 1
            self._sock.sendall(encode_hello(self._xid))
            reply = self._recv_message()
            if reply["type"] == OFPT_ERROR:
                raise TransportError(
                    f"交换机拒绝握手：{reply['payload'][:64].hex()}")
            return {"peer": f"{self.host}:{self.port}",
                    "reply_type": reply["type"], "version": reply["version"]}
        except TransportError:
            self.close()
            raise
        except OSError as exc:
            self.close()
            raise TransportError(
                f"连接 {self.host}:{self.port} 失败：{exc}") from exc

    # ── 发送 ──
    def send_flow_mod(self, flow_bytes: bytes, wait_barrier: bool = True) -> dict:
        """发送一条已编码的 flow_mod；等 Barrier Reply 确认交换机已落表。

        交换机回 ERROR → 抛 TransportError（不重试——半途状态比失败更危险）。
        """
        self._ensure_connected()
        self._sock.sendall(flow_bytes)
        if not wait_barrier:
            return {"sent": len(flow_bytes), "barrier": False}
        self._xid += 1
        barrier_xid = self._xid
        self._sock.sendall(encode_barrier_request(barrier_xid))
        while True:
            msg = self._recv_message()
            if msg["type"] == OFPT_BARRIER_REPLY and msg["xid"] == barrier_xid:
                return {"sent": len(flow_bytes), "barrier": True}
            if msg["type"] == OFPT_ERROR:
                raise TransportError(
                    f"交换机返回错误：{msg['payload'][:64].hex()}")
            self._pending.append(msg)          # PORT_STATUS 等异步消息暂存

    def receive_port_status(self) -> list[dict]:
        """取出已收到的 PORT_STATUS（连接期间交换机异步推送的端口变化）。"""
        drained = self._pending
        self._pending = []
        out = []
        for msg in drained:
            if msg["type"] == OFPT_PORT_STATUS:
                out.append(parse_port_status(msg["payload"]))
        return out

    def close(self):
        if self._sock is not None:
            try:
                self._sock.close()
            except OSError:
                pass
            self._sock = None

    # ── 内部 ──
    def _ensure_connected(self):
        if self._sock is None:
            raise TransportError("尚未连接：先调用 connect()")

    def _recv_exact(self, n: int) -> bytes:
        chunks = b""
        while len(chunks) < n:
            chunk = self._sock.recv(n - len(chunks))
            if not chunk:
                raise TransportError("对端断开连接")
            chunks += chunk
        return chunks

    def _recv_message(self) -> dict:
        version, msg_type, length, xid = _HEADER.unpack(self._recv_exact(8))
        if length < 8:
            raise TransportError(f"非法报文长度：{length}")
        payload = self._recv_exact(length - 8)
        return {"version": version, "type": msg_type, "xid": xid,
                "payload": payload}


def of_port_for(device) -> int:
    """从清单设备推断 OpenFlow 监听端口：6633/6653 才认，否则默认 6653。

    （device.port 通常是管理口 22，不能拿来当 OF 端口用。）
    """
    port = int(getattr(device, "port", 0) or 0)
    return port if port in _OF_PORTS else 6653
