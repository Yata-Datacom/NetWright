# -*- coding: utf-8 -*-
"""生成 NetWright 应用图标：深蓝底 + 经纬交织的"织网"图案（wright 意象）。"""
import os

from PIL import Image, ImageDraw

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ASSETS = os.path.join(BASE, "assets")
os.makedirs(ASSETS, exist_ok=True)
S = 512


def rounded_bg(size):
    top, bottom = (13, 58, 74), (6, 26, 38)   # 薄荷清晨的深色底
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
    teal = (45, 212, 191, 255)     # #2dd4bf 经线
    sky = (56, 189, 248, 255)      # #38bdf8 纬线
    white = (240, 253, 250, 255)
    lw = int(16 * k)

    # ---- 经纬交织（各 3 条，交错成网）----
    xs = [150, 256, 362]
    ys = [150, 256, 362]
    for x in xs:
        d.line([(x * k, 92 * k), (x * k, 420 * k)], fill=teal, width=lw)
    for y in ys:
        d.line([(92 * k, y * k), (420 * k, y * k)], fill=sky, width=lw)

    # ---- 交点织结（白点在最上层）----
    for x in xs:
        for y in ys:
            r = 13 * k
            cx, cy = x * k, y * k
            d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=white)

    # ---- 中心强调：最大织结（薄荷绿）----
    cx, cy = 256 * k, 256 * k
    r = 40 * k
    d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(16, 185, 129, 255),
              outline=white, width=int(6 * k))

    img.resize((256, 256), Image.LANCZOS).save(os.path.join(ASSETS, "logo.png"))
    ico_sizes = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
    img.resize((256, 256), Image.LANCZOS).save(os.path.join(ASSETS, "icon.ico"), sizes=ico_sizes)
    print("OK:", ASSETS)


if __name__ == "__main__":
    main()
