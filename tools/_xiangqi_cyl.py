# -*- coding: utf-8 -*-
"""象棋棋子模型改造：多 cube 拼圆 → 十六段圆柱 poly_mesh（与黑白棋 disc 同构）。

需求（2026-10-16 用户）：
  「把象棋换模型换贴图，模型换成像黑白棋那样的十二段圆柱，直径厚度那些参数按
   原来多 cube 的模型一样就行。贴图上传了表面底面，侧面都取棋子底面上面的那种
   颜色就行了，注意十二段表面底面的 UV 不要超出贴图的区域了。」

口径：
  · 黑白棋 disc 实测是 16 段（16 边缘方向），本脚本与其完全同构 —— 即"那样"的圆柱。
  · 直径/厚度按原多 cube：直径 1.88（R=0.94）、高 0.5（y 2.06..2.56，骨骼 pivot [0,0,0]）。
  · 贴图 = 用户上传的 256x256 四行棋子图（帥仕相車 / 馬炮兵將 / 士象車馬 / 炮卒·空白），
    原样贴进 304x304 palette 的 (24,24)；顶面/底面 UV = 该棋子格内缩 3px（绝不越界），
    侧面 = 空白棋子格的纯米黄色块（棋子底面上的颜色）。
  · marker / hover 骨骼原样保留（它们只用 palette (303,303) 的单像素，重绘时写回）。

产物（就地覆盖，原文件备份 .bak）：
  models/entity/xiangqi/tabletopgame_xiangqi_piece.geo.json
  textures/tabletopgame/xiangqi/xiangqi_palette.png
"""
import io
import json
import math
import os
import shutil
import sys

from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
RP = os.path.join(HERE, '../src/main/resources/assets/resource_pack')
SRC_IMG = r'C:/Users/27155/.workbuddy/clipboard-images/clipboard-2026-10-16T01-49-37-024Z-18645bab.png'

GEO = os.path.join(RP, 'models/entity/xiangqi/tabletopgame_xiangqi_piece.geo.json')
PAL = os.path.join(RP, 'textures/tabletopgame/xiangqi/xiangqi_palette.png')

# ---- 圆柱参数（与原多 cube 一致）----
R = 0.94                 # 半径（原外圈 cube 总宽 1.88 / 2）
Y_TOP, Y_BOT = 2.56, 2.06  # 原 cube y 范围（厚度 0.5）
SEG = 16                 # 黑白棋 disc 同款 16 段

# ---- palette 布局 ----
PAL_SIZE = 304
IMG_XY = (24, 24)        # 用户图在 palette 上的粘贴位
CELL = 64                # 用户图每格
INSET = 3                # 顶/底面 UV 内缩（防越界/压线）
SIDE_UV_C = (248, 248)   # 侧面取色点：空白棋子格 (3,3) 中心在 palette 上的坐标（24 + 3.5*64）

# 骨骼名 → 用户图格 (row, col)
CELL_MAP = {
    'red_chariot': (0, 3), 'red_horse': (1, 0), 'red_elephant': (0, 2),
    'red_guard': (0, 1), 'red_king': (0, 0), 'red_cannon': (1, 1),
    'red_pawn': (1, 2),
    'black_chariot': (2, 2), 'black_horse': (2, 3), 'black_elephant': (2, 1),
    'black_guard': (2, 0), 'black_king': (1, 3), 'black_cannon': (3, 0),
    'black_pawn': (3, 1),
}


def cylinder_poly_mesh(face_cell):
    """十六段圆柱 poly_mesh（黑白棋 disc 同构）。

    face_cell: (row, col) 顶/底面 UV 取自该格（内缩 INSET）；侧面取纯色块。
    """
    row, col = face_cell
    gx0 = IMG_XY[0] + CELL * col + INSET
    gy0 = IMG_XY[1] + CELL * row + INSET
    gw = CELL - 2 * INSET
    # 顶/底面：圆盘 UV 投影到方形字面区（u=+x、v=+z；若真机字向颠倒翻此两行）
    def face_uv(x, z):
        u = (gx0 + (x / R * 0.5 + 0.5) * gw) / PAL_SIZE
        v = (gy0 + (z / R * 0.5 + 0.5) * gw) / PAL_SIZE
        return [round(u, 6), round(v, 6)]
    # 侧面：空白棋子格纯色小方块内取 2 个点（纯色，两面同色）
    su, sv = SIDE_UV_C
    uv_a = [(su - 2) / PAL_SIZE, (sv - 2) / PAL_SIZE]
    uv_b = [(su + 2) / PAL_SIZE, (sv + 2) / PAL_SIZE]

    positions, normals, uvs, polys = [], [], [], []

    def add_pos(p):
        positions.append([round(p[0], 6), round(p[1], 6), round(p[2], 6)])
        return len(positions) - 1

    def add_nor(n):
        normals.append([round(n[0], 6), round(n[1], 6), round(n[2], 6)])
        return len(normals) - 1

    top_c = add_pos((0, Y_TOP, 0))
    bot_c = add_pos((0, Y_BOT, 0))
    top_n = add_nor((0, 1, 0))
    bot_n = add_nor((0, -1, 0))
    uvs.append(face_uv(0, 0))
    top_uv_c = len(uvs) - 1  # poly 顶点的第 2 元素是 uvs 的索引（黑白棋同构）
    top_uvs = [uvs.append(face_uv(R * math.cos(2 * math.pi * i / SEG),
                                  R * math.sin(2 * math.pi * i / SEG))) or len(uvs) - 1
               for i in range(SEG)]
    bot_uvs = [uvs.append(face_uv(R * math.cos(2 * math.pi * i / SEG),
                                  R * math.sin(2 * math.pi * i / SEG))) or len(uvs) - 1
               for i in range(SEG)]

    top_rim, bot_rim, side_top, side_bot, side_n = [], [], [], [], []
    for i in range(SEG):
        a = 2 * math.pi * i / SEG
        cx, cz = R * math.cos(a), R * math.sin(a)
        top_rim.append(add_pos((cx, Y_TOP, cz)))
        bot_rim.append(add_pos((cx, Y_BOT, cz)))
        side_top.append(add_pos((cx, Y_TOP, cz)))
        side_bot.append(add_pos((cx, Y_BOT, cz)))
        side_n.append(add_nor((math.cos(a), 0, math.sin(a))))

    def quad(a, b, c, d):
        polys.append([a, b, c, d])

    # 顶面三角扇（第 4 顶点重复第 1 个 = 三角）
    for i in range(SEG):
        j = (i + 1) % SEG
        quad([top_c, top_uv_c, top_n],
             [top_rim[i], top_uvs[i], top_n],
             [top_rim[j], top_uvs[j], top_n],
             [top_c, top_uv_c, top_n])
    # 侧面 quad（外向：顶 i → 顶 j → 底 j → 底 i）
    uva, uvb = uvs.append(uv_a) or len(uvs) - 1, uvs.append(uv_b) or len(uvs) - 1
    for i in range(SEG):
        j = (i + 1) % SEG
        quad([side_top[i], uva, side_n[i]],
             [side_top[j], uvb, side_n[j]],
             [side_bot[j], uvb, side_n[j]],
             [side_bot[i], uva, side_n[i]])
    # 底面三角扇
    for i in range(SEG):
        j = (i + 1) % SEG
        quad([bot_c, bot_uvs[i], bot_n],
             [bot_rim[j], bot_uvs[j], bot_n],
             [bot_rim[i], bot_uvs[i], bot_n],
             [bot_c, bot_uvs[i], bot_n])

    return {'positions': positions, 'normals': normals, 'uvs': uvs, 'polys': polys}


def main():
    for p in (GEO, PAL):
        bak = p + '.bak'
        if not os.path.isfile(bak):
            shutil.copy(p, bak)
            print('备份 ->', os.path.relpath(bak, RP))

    # ---- 1) geo：32 个 slot 骨骼换圆柱，其余原样 ----
    doc = json.load(io.open(GEO, encoding='utf-8'))
    g = doc['minecraft:geometry'][0]
    n_replaced = 0
    for b in g['bones']:
        name = b['name']
        if not name.startswith('slot_'):
            continue
        kind = name[len('slot_'):].rsplit('_', 1)[0]  # 去掉尾部序号 _0/_1/...
        cell = CELL_MAP[kind]
        b.pop('cubes', None)
        b['poly_mesh'] = cylinder_poly_mesh(cell)
        n_replaced += 1
    doc['minecraft:geometry'] = [g]
    with io.open(GEO, 'w', encoding='utf-8') as fh:
        json.dump(doc, fh, ensure_ascii=False, separators=(',', ':'))
    print('geo: %d 个棋子骨骼已换十六段圆柱' % n_replaced)

    # ---- 2) palette：粘贴用户图 + 写回 marker 单像素 ----
    old = Image.open(PAL + '.bak').convert('RGBA')
    marker_px = old.getpixel((PAL_SIZE - 1, PAL_SIZE - 1))
    img = Image.open(SRC_IMG).convert('RGBA')
    if img.size != (256, 256):
        img = img.resize((256, 256), Image.LANCZOS)
    # 底涂棋子底面米黄再合成用户图：用户图格间/圆外是透明的，
    # alphatest 材质会把采到透明的顶面圆边裁出缺角 —— 合成后全图不透明（mipmap 也安全）。
    pal = Image.new('RGBA', (PAL_SIZE, PAL_SIZE), (244, 224, 182, 255))
    pal.alpha_composite(img, IMG_XY)
    pal.putpixel((PAL_SIZE - 1, PAL_SIZE - 1), marker_px)
    pal.save(PAL)
    print('palette: 304x304 重绘（用户图 @%s，marker 像素 %s 写回）' % (IMG_XY, marker_px[:3]))

    # ---- 3) 自检：UV 全部在 [0,1] 且对应像素不透明 ----
    doc = json.load(io.open(GEO, encoding='utf-8'))
    bad = 0
    for b in doc['minecraft:geometry'][0]['bones']:
        pm = b.get('poly_mesh')
        if not pm:
            continue
        for uv in pm['uvs']:
            if not (0.0 <= uv[0] <= 1.0 and 0.0 <= uv[1] <= 1.0):
                bad += 1
    print('UV 越界顶点: %d' % bad)
    assert bad == 0
    print('done')


if __name__ == '__main__':
    main()
