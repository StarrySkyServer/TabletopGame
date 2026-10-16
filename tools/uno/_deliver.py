# -*- coding: utf-8 -*-
"""本轮改动交付图：① 牌面恢复长方形白底 + 侧面留白 ② 定庄四张各摆各家出牌区。"""
import os
import sys

from PIL import Image, ImageChops, ImageDraw

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import uno_assets as A

HERE = os.path.dirname(os.path.abspath(__file__))
BG = (10, 12, 16)


def load(name):
    return Image.open(os.path.join(HERE, name)).convert('RGB')


def trim(img, pad=4):
    diff = ImageChops.difference(img, Image.new('RGB', img.size, BG)).convert('L')
    box = diff.point(lambda v: 255 if v > 10 else 0).getbbox()
    if not box:
        return img
    x0, y0, x1, y1 = box
    return img.crop((max(0, x0 - pad), max(0, y0 - pad),
                     min(img.width, x1 + pad), min(img.height, y1 + pad)))


def scaled(tile, h):
    return tile.resize((max(1, int(tile.width * h / tile.height)), h), Image.LANCZOS)


def main():
    f = A.font(20)
    show = scaled(trim(load('_top_show.png')), 430)
    cards = scaled(trim(load('_view_bot.png')), 430)

    W = max(show.width, cards.width) + 40
    H = 34 + show.height + 46 + 34 + cards.height + 24
    img = Image.new('RGB', (W, H), (18, 20, 26))
    d = ImageDraw.Draw(img)

    y = 10
    d.text((20, y), '① 定庄比大小：四家同时抽，谁的牌摆谁的出牌区，展示 2 秒后消失再发牌',
           font=f, fill=(255, 220, 120))
    y += 34
    img.paste(show, (20, y))
    y += show.height + 46
    d.text((20, y), '② 牌面恢复成长方形白底，四边（含侧面）留白、不再透明',
           font=f, fill=(255, 220, 120))
    y += 34
    img.paste(cards, (20, y))
    img.save(os.path.join(HERE, '_deliver_fix.png'))
    print('saved _deliver_fix.png', img.size)


if __name__ == '__main__':
    main()
