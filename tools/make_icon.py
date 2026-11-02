# -*- coding: utf-8 -*-
"""生成 NetWright 应用图标（v2）：深海军蓝底 + 控制器拓扑标记。

设计意图：
  * 一眼看出这是"控制网络的东西"——中心节点 + 三个环绕节点 + 连线；
  * 16px 仍然可辨：只保留 4 个圆点与 3 条粗线，不画细节；
  * 与新版深色外壳同色系（#0B1624 → #16273B 底，主色 #5B8DEF、青色 #22D3EE）。
"""
import os

from PIL import Image, ImageDraw

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ASSETS = os.path.join(BASE, "assets")
os.makedirs(ASSETS, exist_ok=True)

S = 1024          # 超采样画布
OUT = 256         # 输出尺寸（ICO 内含多档）

TOP = (22, 39, 59)        # #16273B
BOTTOM = (11, 22, 36)     # #0B1624
ACCENT = (91, 141, 239)   # #5B8DEF
CYAN = (34, 211, 238)     # #22D3EE
WHITE = (240, 248, 255)


def rounded_bg(size: int) -> Image.Image:
    """圆角方形 + 纵向渐变 + 顶部柔光。"""
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    grad = Image.new("RGBA", (size, size))
    gd = ImageDraw.Draw(grad)
    for y in range(size):
        t = y / (size - 1)
        gd.line([(0, y), (size, y)],
                fill=tuple(int(TOP[i] + (BOTTOM[i] - TOP[i]) * t) for i in range(3)) + (255,))
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, size - 1, size - 1],
                                          radius=int(size * 0.24), fill=255)
    img.paste(grad, (0, 0), mask)
    return img


def main():
    size = S
    img = rounded_bg(size)
    d = ImageDraw.Draw(img)

    cx = cy = size / 2
    orbit = size * 0.235          # 卫星节点半径距离
    r_center = size * 0.098
    r_node = size * 0.058
    line_w = int(size * 0.036)

    nodes = [
        (cx, cy - orbit),                       # 上
        (cx - orbit * 0.94, cy + orbit * 0.72),  # 左下
        (cx + orbit * 0.94, cy + orbit * 0.72),  # 右下
    ]

    # 连线（先画线，节点盖住线头，视觉更干净）
    for nx, ny in nodes:
        d.line([(cx, cy), (nx, ny)], fill=(70, 110, 175, 255), width=line_w)
    # 卫星之间的细环线，暗示"三层互联"
    for i in range(3):
        a = nodes[i]
        b = nodes[(i + 1) % 3]
        d.line([a, b], fill=(48, 82, 133, 255), width=int(line_w * 0.55))

    # 卫星节点
    for nx, ny in nodes:
        d.ellipse([nx - r_node, ny - r_node, nx + r_node, ny + r_node],
                  fill=CYAN + (255,), outline=None)
        d.ellipse([nx - r_node * 0.42, ny - r_node * 0.42,
                   nx + r_node * 0.42, ny + r_node * 0.42],
                  fill=(11, 22, 36, 255))

    # 中心控制器：主色圆 + 白色内环 + 中心点（比"靶心"更像一个枢纽）
    d.ellipse([cx - r_center, cy - r_center, cx + r_center, cy + r_center],
              fill=ACCENT + (255,))
    ring = int(r_center * 0.62)
    d.ellipse([cx - ring, cy - ring, cx + ring, cy + ring],
              outline=WHITE + (255,), width=max(2, int(r_center * 0.17)))
    dot = r_center * 0.2
    d.ellipse([cx - dot, cy - dot, cx + dot, cy + dot], fill=WHITE + (255,))

    logo = img.resize((OUT, OUT), Image.LANCZOS)
    logo.save(os.path.join(ASSETS, "logo.png"))
    ico_sizes = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
    logo.save(os.path.join(ASSETS, "icon.ico"), sizes=ico_sizes)
    # 给 README 用的浅色底版本（GitHub 深色主题下也看得清）
    print("OK:", ASSETS)


if __name__ == "__main__":
    main()
