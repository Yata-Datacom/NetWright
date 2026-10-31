# -*- coding: utf-8 -*-
"""生成 NetForge 应用图标（深蓝底 + 2x2 模块网格 + 中心锻造点）。"""
import os

from PIL import Image, ImageDraw

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ASSETS = os.path.join(BASE, "assets")
os.makedirs(ASSETS, exist_ok=True)
S = 512


def rounded_bg(size):
    top, bottom = (25, 42, 78), (11, 18, 36)
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    grad = Image.new("RGBA", (size, size))
    gd = ImageDraw.Draw(grad)
    for y in range(size):
        t = y / (size - 1)
        gd.line([(0, y), (size, y)],
                fill=tuple(int(top[i] + (bottom[i] - top[i]) * t) for i in range(3)) + (255,))
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, size - 1, size - 1],
                                           radius=int(size * 0.22), fill=255)
    img.paste(grad, (0, 0), mask)
    return img


def main():
    k = S / 512.0
    img = rounded_bg(S)
    d = ImageDraw.Draw(img)
    accent = (59, 130, 246, 255)
    white = (232, 238, 247, 255)
    green = (34, 197, 94, 255)

    # ---- 中心节点 ----
    cx, cy = 256 * k, 256 * k
    d.ellipse([cx - 62 * k, cy - 62 * k, cx + 62 * k, cy + 62 * k], fill=accent)
    d.ellipse([cx - 78 * k, cy - 78 * k, cx + 78 * k, cy + 78 * k],
              outline=white, width=int(5 * k))
    # 锻造火花斜杠
    d.line([(238 * k, 278 * k), (280 * k, 232 * k)], fill=white, width=int(12 * k))

    # ---- 四角模块块（2x2 圆角小方）----
    def block(x, y, s, fill, alpha=255):
        x, y, s = x * k, y * k, s * k
        d.rounded_rectangle([x, y, x + s, y + s], radius=int(s * 0.28), fill=fill)

    block(96, 96, 84, (70, 105, 165, 255))
    block(332, 96, 84, (70, 105, 165, 255))
    block(96, 332, 84, (70, 105, 165, 255))
    block(332, 332, 84, green)                      # 右下：已就绪的绿色模块

    # ---- 连接线：中心 -> 各模块 ----
    lw = int(10 * k)
    for tx, ty in ((150, 150), (362, 150), (150, 362), (362, 362)):
        d.line([(cx, cy), (tx * k, ty * k)], fill=(95, 125, 180, 220), width=lw)

    img.resize((256, 256), Image.LANCZOS).save(os.path.join(ASSETS, "logo.png"))
    ico_sizes = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
    img.resize((256, 256), Image.LANCZOS).save(os.path.join(ASSETS, "icon.ico"), sizes=ico_sizes)
    print("OK:", ASSETS)


if __name__ == "__main__":
    main()
