# -*- coding: utf-8 -*-
"""核对：方向标记是否与颜色圆盘关于桌心对称。"""
import os, sys, math
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import render_base as R, render_uno as U, build_model as M
from PIL import Image, ImageDraw

# 俯视（正上方一点）看整个桌心
def top(out, viewer=1, **kw):
    faces = U.scene(viewer, **kw)
    img = R.render_textured(faces, (0.5, 130, -0.5), (0, 0, 0), W=900, H=900, fov=26)
    img = img.crop((90, 240, 810, 660))
    return img

a = top('_dir_top.png', viewer=1, hands=[7,7,7,7], discard=14, pile=5, controls=0,
        dealer=2, actor=3, acolor=0, direction=0, dseat=3)
ImageDraw.Draw(a).text((8, 8), '俯视：颜色圆盘(红,靠自己) / 方向箭头(白,越过牌堆) 应关于牌堆中心对称', fill=(255,235,120))

def pv(out, viewer, **kw):
    faces = U.scene(viewer, **kw)
    ox, oz = M.OUT_X[viewer], M.OUT_Z[viewer]
    img = R.render_textured(faces, (ox*41.6, 10.92, oz*41.6), (0, 3, 0), W=620, H=420, fov=70)
    ImageDraw.Draw(img).text((8, 6), 'viewer=P%d 视角' % (viewer+1), fill=(255,235,120))
    return img

tiles = [pv('_dir_p%d.png' % v, v, hands=[7,7,7,7], discard=14, pile=5, controls=0,
            dealer=(v+1) % 4, actor=(v+2) % 4, acolor=1, direction=1, dseat=(v+3) % 4)
         for v in range(4)]
out = Image.new('RGB', (620*2, 420*2), (12, 14, 18))
for i, t in enumerate(tiles):
    out.paste(t, ((i % 2)*620, (i//2)*420))
out = out.resize((930, 630))

sheet = Image.new('RGB', (930, a.height + 630 + 8), (12, 14, 18))
sheet.paste(a.resize((930, int(a.height*930/a.width))), (0, 0))
sheet.paste(out, (0, int(a.height*930/a.width) + 8))
sheet.save('_dir_sheet.png')
print('saved _dir_sheet.png', sheet.size)

# 数值核对：颜色圆盘与方向箭头是否点对称
for v in range(4):
    dx, dz = M.OUT_X[v]*M.COLOR_R, M.OUT_Z[v]*M.COLOR_R
    sx, sz = -M.OUT_X[v]*M.DIR_R, -M.OUT_Z[v]*M.DIR_R
    print('viewer P%d: 圆盘=(%+.1f,%+.1f)  箭头=(%+.1f,%+.1f)  和=(%+.1f,%+.1f) 半径 %.1f/%.1f'
          % (v+1, dx, dz, sx, sz, dx+sx, dz+sz, M.COLOR_R, M.DIR_R))
