# -*- coding: utf-8 -*-
"""临时脚本：把出牌飞行的 6 个时刻放大渲染成拼图（mode 0 手牌起飞 / mode 1 牌堆翻牌）。"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import render_base as R
import render_uno as U
import build_model as M
import build_table as T
from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))


def frames(mode, ts, cam, out):
    tiles = []
    for t in ts:
        V = U.build_vars(viewer=1, hands=[9, 9, 9, 9], discard=14, pile=5, controls=U.PLAY_BTN,
                         dealer=1, actor=1, acolor=2, dseat=2, fly=(mode, t))
        faces, _, add = R.collect_scene(R.LAYOUT_SRC, V)
        for b in R.GEO['bones']:
            if not b.get('cubes'):
                continue
            if abs(R.eff_scale(R.LAYOUT_SRC, b['name'], V)) < 1e-6:
                continue
            add(b['name'])
        img = R.render_textured(faces, cam[0], cam[1], W=560, H=520, fov=40)
        d = ImageDraw.Draw(img)
        d.text((10, 8), 'mode %d  t=%.2f' % (mode, t), fill=(255, 235, 130))
        tiles.append(img)
    W, H = tiles[0].size
    sheet = Image.new('RGB', (W * 3, H * 2), (12, 14, 18))
    for i, im in enumerate(tiles):
        sheet.paste(im, ((i % 3) * W, (i // 3) * H))
    sheet.save(os.path.join(HERE, out))
    print('saved', out, sheet.size)


# 视角：从西南上方看向「南座（viewer=1）的出牌区」—— 飞行终点；起点在南座手牌中心
cam = ((M.OUT_X[1] * 26 + 22, 26.0, -(-M.OUT_Z[1] * 26) + 16), (M.OUT_X[1] * 13.5, 3, -M.OUT_Z[1] * 6))
frames(0, (0.0, 0.2, 0.4, 0.6, 0.8, 1.0), cam, '_flyzoom0.png')
frames(1, (0.0, 0.2, 0.4, 0.6, 0.8, 1.0), cam, '_flyzoom1.png')
