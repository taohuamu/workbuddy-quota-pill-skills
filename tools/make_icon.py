#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""生成技能图标。

为什么单独写脚本而不是直接给一张 PNG：图标以后大概率要改（配色、比例），
留 PNG 等于留一个没人知道怎么改回来的黑盒。改完重跑一次即可。

为什么要 4 倍超采样：Pillow 的 rounded_rectangle 是硬边，直接画 512 会有
明显锯齿，缩到市场列表那种 40–64px 更糊。

运行：用一个装了 Pillow 的 python 执行本文件，例如
      "C:/Users/<你>/AppData/Local/Programs/Python/Python314/python.exe" tools/make_icon.py
      （WorkBuddy 自带的那份 python 里没有 Pillow，py 启动器在这台机器上也挑不到它）
"""
import os

from PIL import Image, ImageChops, ImageDraw

SIZES = [512, 256, 128]
K = 4                      # 超采样倍数
W = 512 * K

BG = (255, 255, 255, 255)     # 白底
EDGE = (236, 238, 241, 255)   # 白底在白页面里会看不出边界，靠这道极淡描边留形
CAP_REST = (209, 213, 219, 255)  # 剩余段，纯白底上白胶囊等于看不见，改用浅灰
FILL = (52, 194, 107, 255)    # 亮绿，呼应胶囊态里那个百分比
RADIUS = int(W * 0.22)        # 圆角方
STROKE = max(1, int(W * 0.006))

CAP_W_RATIO = 0.60         # 胶囊占画布宽度
CAP_H_RATIO = 0.24
USED_RATIO = 0.62          # 已用部分占胶囊长度

HERE = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.join(os.path.dirname(HERE), "assets")


def build():
    x0 = int((W - W * CAP_W_RATIO) / 2)
    y0 = int((W - W * CAP_H_RATIO) / 2)
    cw, ch = int(W * CAP_W_RATIO), int(W * CAP_H_RATIO)
    r = ch // 2

    img = Image.new("RGBA", (W, W), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([0, 0, W - 1, W - 1], radius=RADIUS, fill=BG)
    d.rounded_rectangle([0, 0, W - 1, W - 1], radius=RADIUS,
                        outline=EDGE, width=STROKE)
    d.rounded_rectangle([x0, y0, x0 + cw - 1, y0 + ch - 1], radius=r,
                        fill=CAP_REST)

    # 已用部分做成矩形后用胶囊形状裁切：手算圆角在右侧会和胶囊边界错开
    cap_mask = Image.new("L", (W, W), 0)
    ImageDraw.Draw(cap_mask).rounded_rectangle(
        [x0, y0, x0 + cw - 1, y0 + ch - 1], radius=r, fill=255)

    layer = Image.new("RGBA", (W, W), (0, 0, 0, 0))
    ImageDraw.Draw(layer).rectangle(
        [x0, y0, x0 + int(cw * USED_RATIO), y0 + ch - 1], fill=FILL)
    layer.putalpha(ImageChops.multiply(layer.split()[3], cap_mask))
    img = Image.alpha_composite(img, layer)

    return img


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    base = build()
    for s in SIZES:
        out = os.path.join(OUT_DIR, "icon-%d.png" % s)
        base.resize((s, s), Image.LANCZOS).save(out)
        print("已生成 %s" % out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
