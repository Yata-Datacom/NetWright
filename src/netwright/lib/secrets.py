"""secrets.py — 凭据保护：Windows DPAPI（当前用户）加密，其他平台降级标记明文。

token 格式：
  dpapi:<base64>   —— DPAPI 加密（仅本机当前用户可解）
  plain:<base64>   —— 无法使用 DPAPI 时的明文兜底（显式标记）
"""
from __future__ import annotations

import base64
import sys

PLAIN_PREFIX = "plain:"
DPAPI_PREFIX = "dpapi:"

_IS_WIN = sys.platform == "win32"

if _IS_WIN:
    import ctypes
    from ctypes import wintypes

    class _DATA_BLOB(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD),
                    ("pbData", ctypes.POINTER(ctypes.c_char))]

    _CRYPT32 = ctypes.windll.crypt32
    _KERNEL32 = ctypes.windll.kernel32


def _dpapi_call(data: bytes, protect: bool) -> bytes:
    buf = ctypes.create_string_buffer(data, len(data))
    blob_in = _DATA_BLOB(len(data), ctypes.cast(buf, ctypes.POINTER(ctypes.c_char)))
    blob_out = _DATA_BLOB()
    # CryptProtectData(pDataIn, szDataDescr, pOptionalEntropy, pvReserved, pPromptStruct, dwFlags, pDataOut)
    if protect:
        ok = _CRYPT32.CryptProtectData(ctypes.byref(blob_in), "NetWright", None, None, None, 0,
                                       ctypes.byref(blob_out))
    else:
        ok = _CRYPT32.CryptUnprotectData(ctypes.byref(blob_in), None, None, None, None, 0,
                                         ctypes.byref(blob_out))
    if not ok:
        raise OSError("DPAPI 调用失败")
    try:
        return ctypes.string_at(blob_out.pbData, blob_out.cbData)
    finally:
        _KERNEL32.LocalFree(blob_out.pbData)


def protect(value: str) -> str:
    """把明文加密成存储 token（Windows 用 DPAPI，其他平台明文标记）。"""
    if not value:
        return ""
    raw = value.encode("utf-8")
    if _IS_WIN:
        try:
            return DPAPI_PREFIX + base64.b64encode(_dpapi_call(raw, protect=True)).decode("ascii")
        except OSError:
            pass
    return PLAIN_PREFIX + base64.b64encode(raw).decode("ascii")


def unprotect(token: str) -> str:
    """把存储 token 还原成明文。空串/非 token 格式原样返回。"""
    if not token:
        return ""
    token = token.strip()
    if token.startswith(DPAPI_PREFIX):
        if not _IS_WIN:
            raise ValueError("DPAPI 凭据只能在 Windows 上解密")
        raw = base64.b64decode(token[len(DPAPI_PREFIX):])
        return _dpapi_call(raw, protect=False).decode("utf-8")
    if token.startswith(PLAIN_PREFIX):
        return base64.b64decode(token[len(PLAIN_PREFIX):]).decode("utf-8")
    return token  # 兼容直接存明文的旧数据


def protection_kind(token: str) -> str:
    if token.startswith(DPAPI_PREFIX):
        return "dpapi"
    if token.startswith(PLAIN_PREFIX):
        return "plain"
    return "plain"


def mask(value: str, keep: int = 0) -> str:
    """UI 展示用打码。"""
    if not value:
        return ""
    return "•" * max(4, len(value) - keep)
