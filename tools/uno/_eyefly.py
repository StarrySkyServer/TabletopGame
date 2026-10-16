# -*- coding: utf-8 -*-
"""临时脚本：真实眼位下的出牌飞行 + 倒计时文字模拟（交付核对图）。"""
import os
import sys

from PIL import Image, ImageDraw

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import render_base as R
import render_uno as U
import build_model as M
import uno_assets as A

HERE = os.path.dirname(os.path.abspath(__file__))


def eye_frames(seat, dseat, mode, ts, W=620, H=430, fov=72):
    out = []
    for t in ts:
        kw = dict(hands=[9, 9, 9, 9], discard=14, pile=5, controls=U.PLAY_BTN,
                  dealer=dseat, actor=dseat, acolor=2, direction=0, dseat=dseat, fly=(mode, t))
        faces = U.scene(seat, **kw)
        ox, oz = M.OUT_X[seat], M.OUT_Z[seat]
        eye = (ox * 48.0, 10.92, -oz * 48.0)
        img = R.render_textured(faces, eye, (0, 3, 0), W=W, H=H, fov=fov)
        d = ImageDraw.Draw(img)
        d.text((10, 8), 'viewer P%d  dseat P%d  mode %d  t=%.2f' % (seat + 1, dseat, mode, t),
               fill=(255, 235, 140))
        out.append(img)
    return out


def strip(tiles, cols):
    W, H = tiles[0].size
    rows = (len(tiles) + cols - 1) // cols
    sheet = Image.new('RGB', (W * cols, H * rows), (12, 14, 18))
    for i, im in enumerate(tiles):
        sheet.paste(im, ((i % cols) * W, (i // cols) * H))
    return sheet


def countdown_mock(W=980):
    """模拟 action bar（sendTip）在三种剩余秒数下的观感。"""
    f = A.font(30)
    f2 = A.font(24)
    lines = [
        ('§a', '轮到你出牌 · 剩余 38 秒', (150, 235, 150), '你的回合（充裕，绿色）'),
        ('§e', '轮到你出牌 · 剩余 12 秒', (245, 215, 90), '你的回合（过半，黄色）'),
        ('§c', '轮到你出牌 · 剩余 4 秒', (255, 110, 100), '你的回合（最后 5 秒，红色加粗）'),
        ('§7', 'P2 出牌中 · 剩余 27 秒', (200, 200, 200), '别人的回合（全桌可见）'),
    ]
    img = Image.new('RGB', (W, 46 * len(lines) + 16), (14, 16, 20))
    d = ImageDraw.Draw(img)
    for i, (code, text, col, note) in enumerate(lines):
        y = 8 + i * 46
        d.rectangle([10, y, W - 10, y + 38], fill=(28, 30, 34))
        tag = text.replace('§a', '').replace('§e', '').replace('§c', '').replace('§7', '')
        d.text((22, y + 4), tag, font=f, fill=col)
        d.text((W - 372, y + 10), note, font=f2, fill=(150, 155, 165))
    return img


def main():
    tiles = []
    # 1) 自己出牌（mode 0）：从自己的手牌飞到自己的出牌区
    tiles += eye_frames(1, 2, 0, (0.0, 0.35, 0.7, 1.0))
    # 2) 对家出牌（mode 0）：牌从对面飞过来
    tiles += eye_frames(1, 3, 0, (0.0, 0.35, 0.7, 1.0))
    # 3) 从牌堆翻起始牌（mode 1）
    tiles += eye_frames(1, 2, 1, (0.0, 0.5, 1.0))
    strip(tiles, 4).save(os.path.join(HERE, '_eye_fly.png'))
    countdown_mock().save(os.path.join(HERE, '_cd_mock.png'))
    print('saved _eye_fly.png / _cd_mock.png')


if __name__ == '__main__':
    main()
