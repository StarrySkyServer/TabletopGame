# -*- coding: utf-8 -*-
"""交付图（_deliver_locator3.png）：本轮的定位器改动
  ① 模型贴图：旧 16x16 几乎全黑（模型 = 黑棍）→ 剖面烘焙 + UV v 重映射（灰头/白环/灰颈/黑身）
  ② 光点：绿 → 白
  ③ 拖影：粒子寿命 0.18 → 0.06 秒（每 tick 补一颗）
  ④ 裁切：光点沿 +Y 抬 0.03 格（掠射角也不再被卡面裁掉）
"""
import io
import json
import math
import os
import sys

from PIL import Image, ImageDraw

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import render_base as R
import uno_assets as A

HERE = os.path.dirname(os.path.abspath(__file__))
RP = A.RP
GEO = os.path.join(RP, 'models/entity/uno/locator.geo.json')
TEX = os.path.join(RP, 'textures/tabletopgame/uno/locator.png')
OLD_TEX = 'D:/CodeProject/Gobang/象棋/激光笔/laser_pointer.png'

tex = Image.open(TEX).convert('RGBA')
tw, th = tex.size
geo = json.load(io.open(GEO, encoding='utf-8'))['minecraft:geometry'][0]
mesh = geo['bones'][0]['poly_mesh']
pos, uvs, polys = mesh['positions'], mesh['uvs'], mesh['polys']
rot = (113.2953, -26.3747, 32.0877)
off = (-7.10577, 15.78604, -5.32049)


def xform(p):
    q = R.rot_pt((p[0], p[1] - 8.0, p[2]), rot, (0.0, 0.0, 0.0))
    return (q[0] * 0.6 + off[0], q[1] * 0.6 + 8.0 + off[1], q[2] * 0.6 + off[2])


def build_faces(xf=None):
    out = []
    for poly in polys:
        pts = [tuple(pos[v[0]]) for v in poly]
        if xf:
            pts = [xf(p) for p in pts]
        src = [(uvs[v[2]][0] * tw, uvs[v[2]][1] * th) for v in poly]
        a, b, c = pts[0], pts[1], pts[2]
        u1 = (b[0] - a[0], b[1] - a[1], b[2] - a[2])
        u2 = (c[0] - a[0], c[1] - a[1], c[2] - a[2])
        n = (u1[1] * u2[2] - u1[2] * u2[1], u1[2] * u2[0] - u1[0] * u2[2],
             u1[0] * u2[1] - u1[1] * u2[0])
        ln = math.sqrt(sum(v * v for v in n)) or 1
        out.append((pts, (30, 30, 30), tuple(v / ln for v in n), ((0, 0, tw, th), src)))
    return out


R.ATLAS, R.APX, R.ATW, R.ATH = tex, tex.load(), tw, th

f, fs, fss = A.font(24), A.font(18), A.font(16)

# ---- 行 1：模型四视图 ----
views = [
    ('正面', (0.0, 14.0, -70.0), (0.0, 12.0, 0.0), 460, 560, 20),
    ('3/4', (40.0, 22.0, -58.0), (0.0, 12.0, 0.0), 460, 560, 20),
    ('侧面', (70.0, 14.0, 0.0), (0.0, 12.0, 0.0), 460, 560, 20),
]
tiles = []
for tag, eye, tgt, W, H, fov in views:
    img = R.render_textured(build_faces(), eye, tgt, W=W, H=H, fov=fov, bg=(214, 214, 220))
    ImageDraw.Draw(img).text((8, 6), '定位器 %s' % tag, font=A.font(20), fill=(20, 20, 24))
    tiles.append(img)
# 第一人称持握（照 attachable 姿态）
img = R.render_textured(build_faces(xform), (-7.2, 26.7, 10.6), (-7.2, 23.7, -5.4),
                        W=520, H=560, fov=50, bg=(120, 124, 132))
ImageDraw.Draw(img).text((8, 6), '第一人称持握（白环在笔尖远端）', font=A.font(20), fill=(255, 255, 255))
tiles.append(img)

row1_h = max(t.height for t in tiles)
row1_w = sum(t.width for t in tiles) + 3 * 10

# ---- 行 2：贴图对比 + 白点 ----
def zoom(im, z, bg=(52, 56, 64)):
    c = Image.new('RGB', (im.width * z, im.height * z), bg)
    r = im.resize((im.width * z, im.height * z), Image.NEAREST)
    c.paste(r, (0, 0), r)
    return c


old = zoom(Image.open(OLD_TEX).convert('RGBA'), 10)
new = zoom(tex, 5)
dot = zoom(Image.open(os.path.join(RP, 'textures/tabletopgame/uno/locator_dot.png')).convert('RGBA'), 12)
row2 = Image.new('RGB', (old.width + new.width + dot.width + 80, max(old.height, new.height, dot.height)),
                 (22, 24, 30))
x = 0
for im in (old, new, dot):
    row2.paste(im, (x, 0))
    x += im.width + 40

W = max(row1_w, row2.width) + 40
H = 118 + row1_h + 46 + row2.height + 92
sheet = Image.new('RGB', (W, H), (16, 18, 24))
d = ImageDraw.Draw(sheet)
d.text((20, 12), '定位器：模型贴图换新（剖面烘焙）+ 白点 + 拖影/裁切修正', font=f, fill=(255, 220, 120))
d.text((20, 50), '旧 16x16 贴图几乎全黑（250/256 像素纯黑）⇒ 手里的模型是一根黑棍；'
                 '现按 texture.png 剖面烘焙（整幅同色带）+ UV 的 v 按笔身高度重映射',
       font=fs, fill=(214, 220, 230))
x = 20
for t in tiles:
    sheet.paste(t, (x, 84))
    x += t.width + 10
y = 84 + row1_h + 30
sheet.paste(row2, (20, y))
d.text((20, y - 24), '旧贴图 16x16（全黑）          新贴图 32x32（剖面烘焙，整幅不透明）'
                     '          白点 16x16（绿→白）',
       font=fss, fill=(200, 206, 218))
y2 = y + row2.height + 14
for t, c in [
    ('② 光点：绿色 → 白色（「那个激光点换成白色的」）', (235, 235, 235)),
    ('③ 拖影：粒子寿命 0.18 → 0.06 秒 —— 每 tick 补一颗，不闪也不拖（「会同时存在多个激光点」）',
     (140, 235, 160)),
    ('④ 裁切：光点沿 +Y 抬 0.03 格（≈2cm）—— 掠射看卡面/按钮时也不再被平面裁掉半颗',
     (140, 200, 255)),
]:
    d.text((20, y2), t, font=fss, fill=c)
    y2 += 26

sheet.save(os.path.join(HERE, '_deliver_locator3.png'))
print('saved _deliver_locator3.png', sheet.size)
