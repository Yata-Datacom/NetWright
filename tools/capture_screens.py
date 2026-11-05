"""抓取 NetWright 窗口截图（指定页面）。\n\n需要**已解锁的交互式桌面**：锁屏或无人登录时，窗口不会被绘制，截到的是桌面/其他程序。\n脚本会临时把窗口置顶再抓取其矩形区域（只抓本程序窗口，不抓整屏）。\n用法：python tools/capture_screens.py\n"""\n

做法：改 settings.last_page → 启动源码版 → 用 Win32 找到窗口矩形 →
PIL.ImageGrab 只抓这个窗口区域（不抓整屏，避免碰到别的窗口内容）。
"""
import ctypes
import ctypes.wintypes
import json
import os
import subprocess
import sys
import time

from PIL import ImageGrab

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PY = os.path.join(ROOT, ".venv", "Scripts", "python.exe")
SETTINGS = os.path.join(ROOT, "netwright_settings.json")
OUT = os.path.join(ROOT, "docs", "screenshots")

user32 = ctypes.windll.user32


def window_rect(title_part: str):
    found = []

    @ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
    def callback(hwnd, _lparam):
        length = user32.GetWindowTextLengthW(hwnd)
        if length:
            buf = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(hwnd, buf, length + 1)
            if title_part in buf.value and user32.IsWindowVisible(hwnd):
                rect = ctypes.wintypes.RECT()
                user32.GetWindowRect(hwnd, ctypes.byref(rect))
                found.append((buf.value, hwnd, rect.left, rect.top, rect.right, rect.bottom))
        return True

    user32.EnumWindows(callback, 0)
    return found[0] if found else None


def set_last_page(page: str) -> None:
    data = {}
    if os.path.exists(SETTINGS):
        try:
            data = json.load(open(SETTINGS, encoding="utf-8"))
        except ValueError:
            data = {}
    data["last_page"] = page
    json.dump(data, open(SETTINGS, "w", encoding="utf-8"), ensure_ascii=False, indent=2)


def capture(page: str, name: str) -> str:
    set_last_page(page)
    proc = subprocess.Popen([PY, "main.py"], cwd=ROOT,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        rect = None
        deadline = time.time() + 20
        while time.time() < deadline:
            rect = window_rect("NetWright SDN Console")
            if rect:
                break
            time.sleep(0.2)
        if not rect:
            raise RuntimeError("窗口没出现（可能无显示环境）")
        time.sleep(1.8)                       # 等首屏渲染完成
        hwnd = rect[1]
        user32.ShowWindow(hwnd, 9)                 # SW_RESTORE
        user32.SetForegroundWindow(hwnd)
        # 后台进程改不了前台窗口，但可以强制置顶（HWND_TOPMOST=-1）
        user32.SetWindowPos(hwnd, -1, 0, 0, 0, 0, 0x0043)
        time.sleep(1.2)
        rect2 = ctypes.wintypes.RECT()
        user32.GetWindowRect(hwnd, ctypes.byref(rect2))
        left, top, right, bottom = rect2.left, rect2.top, rect2.right, rect2.bottom
        image = ImageGrab.grab(bbox=(left, top, right, bottom), all_screens=True)
        user32.SetWindowPos(hwnd, -2, 0, 0, 0, 0, 0x0043)   # 还原非置顶
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


if __name__ == "__main__":
    jobs = [("ops", "ops-center.png"), ("timeline", "timeline-light.png"),
            ("controller", "controller-intent.png")]
    for page, name in jobs:
        try:
            print("captured:", capture(page, name))
        except Exception as exc:      # noqa: BLE001
            print("FAIL", page, exc)
            sys.exit(1)
