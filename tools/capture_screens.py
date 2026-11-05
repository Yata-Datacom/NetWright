"""抓取 NetWright 窗口截图（指定页面）。

需要**已解锁的交互式桌面**：锁屏或无人登录时窗口不会被绘制，截到的是桌面/其他程序。
脚本会临时把窗口置顶，再只抓该窗口矩形区域（不抓整屏）。

用法：
    .venv\\Scripts\\python.exe tools\\capture_screens.py
"""
from __future__ import annotations

import ctypes
import ctypes.wintypes
import json
import os
import subprocess
import sys
import time

from PIL import ImageGrab

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PYTHON = os.path.join(ROOT, ".venv", "Scripts", "python.exe")
SETTINGS = os.path.join(ROOT, "netwright_settings.json")
OUT = os.path.join(ROOT, "docs", "screenshots")

user32 = ctypes.windll.user32
WINFUNCTYPE = ctypes.WINFUNCTYPE
SW_RESTORE = 9
HWND_TOPMOST = -1
HWND_NOTOPMOST = -2
SWP_FLAGS = 0x0043


def window_rect(title_part: str):
    found = []

    @WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
    def callback(hwnd, _lparam):
        length = user32.GetWindowTextLengthW(hwnd)
        if not length:
            return True
        buffer = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buffer, length + 1)
        if title_part in buffer.value and user32.IsWindowVisible(hwnd):
            rect = ctypes.wintypes.RECT()
            user32.GetWindowRect(hwnd, ctypes.byref(rect))
            found.append((buffer.value, hwnd, rect.left, rect.top, rect.right, rect.bottom))
        return True

    user32.EnumWindows(callback, 0)
    return found[0] if found else None


def set_last_page(page: str) -> None:
    data = {}
    if os.path.exists(SETTINGS):
        try:
            with open(SETTINGS, encoding="utf-8") as handle:
                data = json.load(handle)
        except ValueError:
            data = {}
    data["last_page"] = page
    with open(SETTINGS, "w", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=2)


def capture(page: str, name: str) -> str:
    set_last_page(page)
    proc = subprocess.Popen([PYTHON, "main.py"], cwd=ROOT,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        found = None
        deadline = time.time() + 20
        while time.time() < deadline:
            found = window_rect("NetWright SDN Console")
            if found:
                break
            time.sleep(0.2)
        if not found:
            raise RuntimeError("窗口没出现（可能没有交互式桌面）")
        hwnd = found[1]
        user32.ShowWindow(hwnd, SW_RESTORE)
        user32.SetWindowPos(hwnd, HWND_TOPMOST, 0, 0, 0, 0, SWP_FLAGS)
        time.sleep(1.8)                      # 等首屏渲染
        rect = ctypes.wintypes.RECT()
        user32.GetWindowRect(hwnd, ctypes.byref(rect))
        image = ImageGrab.grab(bbox=(rect.left, rect.top, rect.right, rect.bottom),
                               all_screens=True)
        user32.SetWindowPos(hwnd, HWND_NOTOPMOST, 0, 0, 0, 0, SWP_FLAGS)
        os.makedirs(OUT, exist_ok=True)
        path = os.path.join(OUT, name)
        image.save(path)
        return path
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()


def main() -> int:
    jobs = [("ops", "ops-center.png"), ("timeline", "timeline-light.png"),
            ("controller", "controller-intent.png")]
    for page, name in jobs:
        try:
            print("captured:", capture(page, name))
        except Exception as exc:      # noqa: BLE001
            print("FAIL", page, exc)
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
