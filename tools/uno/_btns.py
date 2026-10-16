# -*- coding: utf-8 -*-
"""单独渲染 4 个颜色按钮的状态，并把图集里的 4 个颜色按钮贴图放大导出。"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import render_base as R, render_uno as U, build_model as M, uno_assets as A
from PIL import Image, ImageDraw

# BTN_COLOR 打包值：槽 0..3 = 红(8) 黄(9) 绿(10) 蓝(11)
PACK = 8 | (9 << 4) | (10 << 8) | (11 << 12)
EYE_OUT, EYE_Y = 41.6, 10.92

def shot(out, controls, tag):
    faces = U.scene(1, hands=[7,7,7,7], discard=14, pile=5, controls=controls,
                    dealer=1, actor=1, acolor=0)
    img = R.render_textured(faces, (0, EYE_Y, EYE_OUT), (0, 3, 0), W=900, H=620, fov=70)
    ImageDraw.Draw(img).text((10, 8), tag, fill=(255,255,0))
    return img

a = shot('_btn_color.png', PACK, 'BTN_COLOR pack=%d  期望：4 个颜色按钮' % PACK)
b = shot('_btn_play.png', U.PLAY_BTN, 'BTN_PLAY pack=%d  对比' % U.PLAY_BTN)

# 图集里的颜色按钮贴图（normal / pressed）
atlas = Image.open(A.OUT_ATLAS).convert('RGBA')
tiles = []
for act in ('c_red', 'c_yellow', 'c_green', 'c_blue'):
    row = []
    for st in ('normal', 'pressed'):
        uv = A.btn_tile(act, st)
        t = atlas.crop((uv[0], uv[1], uv[0] + A.BTN_W, uv[1] + A.BTN_H))
        bg = Image.new('RGB', (t.width + 16, t.height + 16), (24, 26, 32))
        bg.paste(t, (8, 8), t)
        row.append(bg)
    line = Image.new('RGB', (row[0].width * 2 + 8, row[0].height), (24, 26, 32))
    line.paste(row[0], (0, 0))
    line.paste(row[1], (row[0].width + 8, 0))
    tiles.append((act, line))
sheet = Image.new('RGB', (max(t.width for _, t in tiles), sum(t.height + 22 for _, t in tiles)), (24, 26, 32))
y = 0
for act, t in tiles:
    ImageDraw.Draw(sheet).text((4, y + 4), act, fill=(255, 235, 120))
    sheet.paste(t, (0, y + 20))
    y += t.height + 22
sheet.save('_btn_tiles.png')

# 每张贴图里有多少「非透明」像素 + 平均色，确认贴图不是空的
for act in ('c_red', 'c_yellow', 'c_green', 'c_blue', 'play', 'skip'):
    uv = A.btn_tile(act, 'normal')
    t = atlas.crop((uv[0], uv[1], uv[0] + A.BTN_W, uv[1] + A.BTN_H)).convert('RGBA')
    px = list(t.getdata())
    op = [p for p in px if p[3] > 8]
    if op:
        avg = tuple(round(sum(p[i] for p in op) / len(op)) for i in range(3))
    else:
        avg = None
    print('%-9s 不透明像素 %5d / %d  平均色 %s' % (act, len(op), len(px), avg))

out = Image.new('RGB', (1800, 620), (12, 14, 18))
out.paste(a, (0, 0)); out.paste(b, (900, 0))
out.resize((1350, 465)).save('_btn_cmp.png')
print('ok')
