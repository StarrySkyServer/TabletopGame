# -*- coding: utf-8 -*-
"""渲染定位器模型：常规三视图 + 第一人称持握姿态（核对配色与朝向）。"""
import io, json, math, os, sys
from PIL import Image, ImageDraw
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import render_base as R
import uno_assets as A

HERE = os.path.dirname(os.path.abspath(__file__))
GEO = os.path.join(A.RP, 'models/entity/uno/locator.geo.json')
TEX = os.path.join(A.RP, 'textures/tabletopgame/uno/locator.png')
tex = Image.open(TEX).convert('RGBA')
tw, th = tex.size
geo = json.load(io.open(GEO, encoding='utf-8'))['minecraft:geometry'][0]
mesh = geo['bones'][0]['poly_mesh']
pos, uvs, polys = mesh['positions'], mesh['uvs'], mesh['polys']

def faces(xform=None):
    out = []
    for poly in polys:
        pts = [tuple(pos[v[0]]) for v in poly]
        if xform:
            pts = [xform(p) for p in pts]
        src = [(uvs[v[2]][0] * tw, uvs[v[2]][1] * th) for v in poly]
        a, b, c = pts[0], pts[1], pts[2]
        u1 = (b[0]-a[0], b[1]-a[1], b[2]-a[2]); u2 = (c[0]-a[0], c[1]-a[1], c[2]-a[2])
        n = (u1[1]*u2[2]-u1[2]*u2[1], u1[2]*u2[0]-u1[0]*u2[2], u1[0]*u2[1]-u1[1]*u2[0])
        ln = math.sqrt(sum(v*v for v in n)) or 1
        out.append((pts, (30, 30, 30), tuple(v/ln for v in n), ((0, 0, tw, th), src)))
    return out

R.ATLAS, R.APX, R.ATW, R.ATH = tex, tex.load(), tw, th

# 1) 常规三视图
tiles = []
for tag, eye in (('正面', (0.0, 14.0, -70.0)), ('3/4', (40.0, 22.0, -58.0)), ('侧面', (70.0, 14.0, 0.0))):
    img = R.render_textured(faces(), eye, (0.0, 12.0, 0.0), W=460, H=560, fov=20, bg=(214, 214, 220))
    ImageDraw.Draw(img).text((8, 6), '定位器(新贴图) %s' % tag, font=A.font(20), fill=(20, 20, 24))
    tiles.append(img)

# 2) 第一人称持握姿态（照 attachable 动画的 rot/pos）
rot = (113.2953, -26.3747, 32.0877)
off = (-7.10577, 15.78604, -5.32049)
scale = 0.6
def xform(p):
    q = tuple(p[k] - 8.0 if k == 1 else p[k] for k in range(3))
    q = R.rot_pt(q, rot, (0.0, 0.0, 0.0))
    return ((q[0] * scale) + 8.0 + off[0], (q[1] * scale) + 8.0 + off[1], (q[2] * scale) + 8.0 + off[2])
img = R.render_textured(faces(xform), (-5.0, 28.5, 4.0), (-7.1, 23.8, -5.3), W=520, H=430, fov=50,
                        bg=(120, 124, 132))
ImageDraw.Draw(img).text((8, 6), '第一人称持握（核对笔尖朝向：灰头/白环应在远端）', font=A.font(18),
                         fill=(255, 255, 255))
tiles.append(img)

W = sum(t.width for t in tiles) + 3 * 10
H = max(t.height for t in tiles)
sheet = Image.new('RGB', (W, H), (214, 214, 220))
x = 0
for t in tiles:
    sheet.paste(t, (x, 0))
    x += t.width + 10
sheet.save(os.path.join(HERE, '_locator_look.png'))
print('saved _locator_look.png', sheet.size)
