# -*- coding: utf-8 -*-
"""最终核对图：真机视角 / 俯视布局 / 逐张发牌 / 白边放大。"""
import os, sys, math
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import render_base as R, render_uno as U, build_model as M, uno_assets as A
from PIL import Image, ImageDraw

EYE_OUT, EYE_Y = 41.6, 10.92

def label(im, text):
    d = ImageDraw.Draw(im)
    d.rectangle([0, 0, im.width, 26], fill=(12, 14, 18))
    d.text((8, 8), text, fill=(255, 235, 120))
    return im

def player_view():
    faces = U.scene(1, hands=[9, 24, 9, 9], discard=27, pile=5, controls=U.PLAY_BTN,
                    dealer=1, actor=1, acolor=2, sel=29, dseat=3)
    im = R.render_textured(faces, (0, EYE_Y, EYE_OUT), (0, 3, 0), W=900, H=600, fov=70)
    return label(im, 'A. 玩家视角（眼高 1.62 格 / 距桌心 2.6 格）：两行手牌 + 出牌区 + 按钮')

def top_view():
    faces = U.scene(1, hands=[7, 9, 7, 7], discard=27, pile=5, controls=0,
                    dealer=2, actor=3, acolor=3, direction=1, dseat=2)
    im = R.render_textured(faces, (0.5, 130, -0.5), (0, 0, 0), W=900, H=900, fov=26)
    im = im.crop((0, 150, 900, 750))
    return label(im, 'B. 桌面布局：牌堆居中横放 / 颜色圆盘在自己正前 / 方向箭头右手边 / 弃牌在出牌者一侧')

def deal():
    tiles = []
    for i, dn in enumerate((1, 3, 5, 7)):
        faces = U.scene(1, hands=[7,7,7,7], discard=27, pile=0, controls=0,
                        dealer=1, actor=1, acolor=0, dseat=3, deal_n=dn)
        im = R.render_textured(faces, (0, EYE_Y, EYE_OUT), (0, 3, 0), W=450, H=300, fov=70)
        tiles.append(label(im, 'C%d. 发牌 uno_deal=%d' % (i + 1, dn)))
    out = Image.new('RGB', (900, 600), (12, 14, 18))
    for i, t in enumerate(tiles):
        out.paste(t, ((i % 2) * 450, (i // 2) * 300))
    return out

def edges():
    tiles = []
    atlas = Image.open(A.OUT_ATLAS).convert('RGBA')
    for nm, uv, w, h in (('牌面(红5)', A.face_tile(M.face_of(9)), A.CARD_W, A.CARD_H),
                         ('牌背', A.face_tile(A.FACE_BACK), A.CARD_W, A.CARD_H),
                         ('按钮 出牌', A.btn_tile('play', 'normal'), A.BTN_W, A.BTN_H),
                         ('按钮 跳过', A.btn_tile('skip', 'normal'), A.BTN_W, A.BTN_H)):
        t = atlas.crop((uv[0], uv[1], uv[0] + w, uv[1] + h))
        # 贴到深色底上看白边
        bg = Image.new('RGB', (t.width + 40, t.height + 40), (24, 26, 32))
        bg.paste(t, (20, 20), t)
        bg = bg.resize((450, max(1, int((t.height + 40) * 450 / (t.width + 40)))))
        tiles.append(label(bg, 'D. ' + nm + ' 边缘'))
    H = max(t.height for t in tiles)
    out = Image.new('RGB', (450 * 4, H), (12, 14, 18))
    for i, t in enumerate(tiles):
        out.paste(t, (i * 450, 0))
    return out

a, b, c, d = player_view(), top_view(), deal(), edges()
W = 1800
sheet = Image.new('RGB', (W, 600 + 600 + 600 + d.height + 12), (12, 14, 18))
sheet.paste(a, (0, 0))
sheet.paste(b, (900, 0))
sheet.paste(c, (0, 600))
sheet.paste(d, (0, 1200))
sheet.save('_final_sheet.png')
print('saved _final_sheet.png', sheet.size)
