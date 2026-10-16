# -*- coding: utf-8 -*-
"""临时脚本：离线渲染「定位器」模型（poly_mesh + 16x16 UV 贴图）核对观感。"""
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


def build_faces():
    geo = json.load(io.open(GEO, encoding='utf-8'))['minecraft:geometry'][0]
    tex = Image.open(TEX).convert('RGBA')
    tw, th = tex.size
    mesh = geo['bones'][0]['poly_mesh']
    pos, nrm, uvs, polys = mesh['positions'], mesh['normals'], mesh['uvs'], mesh['polys']
    norm = mesh.get('normalized_uvs')
    faces = []
    for poly in polys:
        pts = [tuple(pos[v[0]]) for v in poly]
        src = [(uvs[v[2]][0] * tw if norm else uvs[v[2]][0],
                uvs[v[2]][1] * th if norm else uvs[v[2]][1]) for v in poly]
        a, b, c = pts[0], pts[1], pts[2]
        n = (0.0, 0.0, 0.0)
        if len(pts) >= 3:
            u1 = (b[0] - a[0], b[1] - a[1], b[2] - a[2])
            u2 = (c[0] - a[0], c[1] - a[1], c[2] - a[2])
            n = (u1[1] * u2[2] - u1[2] * u2[1], u1[2] * u2[0] - u1[0] * u2[2],
                 u1[0] * u2[1] - u1[1] * u2[0])
            ln = math.sqrt(sum(v * v for v in n)) or 1.0
            n = tuple(v / ln for v in n)
        faces.append((pts, (20, 20, 20), n, ((0, 0, tw, th), src)))
    return faces, tex


def main():
    faces, tex = build_faces()
    # 让渲染器用这张 16x16 贴图当"图集"
    R.ATLAS = tex
    R.APX = tex.load()
    R.ATW, R.ATH = tex.size
    # 模型是斜持的（原动画里第一人称是 rotation [113,-26,32]、位置偏移），这里只转个小角度看正面
    z = 6.0
    W = int(120 * z)
    tiles = []
    for tag, eye in (('正面', (0.0, 14.0, -70.0)), ('3/4', (40.0, 22.0, -58.0)),
                     ('侧面', (70.0, 14.0, 0.0))):
        img = R.render_textured(faces, eye, (0.0, 12.0, 0.0), W=W, H=int(150 * z), fov=20,
                                bg=(214, 214, 220))
        d = ImageDraw.Draw(img)
        d.text((8, 6), '定位器 %s' % tag, font=A.font(22), fill=(20, 20, 24))
        tiles.append(img)
    sheet = Image.new('RGB', (sum(t.width for t in tiles) + 20, tiles[0].height), (214, 214, 220))
    x = 0
    for t in tiles:
        sheet.paste(t, (x, 0))
        x += t.width + 10
    sheet.save(os.path.join(HERE, '_locator_view.png'))
    print('saved _locator_view.png', sheet.size, '（模型单位：1 = 1/16 格，高 15 单位）')


if __name__ == '__main__':
    main()
