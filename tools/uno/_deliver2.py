# -*- coding: utf-8 -*-
"""临时脚本：生成本轮交付核对图（牌环填充 / 出牌飞行 / 倒计时）。"""
import os
import sys

from PIL import Image, ImageDraw

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import render_base as R
import render_uno as U
import build_model as M
import uno_assets as A

HERE = os.path.dirname(os.path.abspath(__file__))
ATLAS = Image.open(A.OUT_ATLAS).convert('RGBA')
DECK_SRC = Image.open(A.DECK_SRC).convert('RGBA')


def card_sheet(cols=8):
    tw, th = 108, 162
    img = Image.new('RGB', (cols * (tw + 6) + 6, 7 * (th + 6) + 6), (18, 20, 24))
    for k in range(56):
        c, r = k % cols, k // cols
        x, y = A.face_tile(k)
        t = ATLAS.crop((x, y, x + A.CARD_W, y + A.CARD_H)).convert('RGB')
        t = t.resize((tw, th), Image.LANCZOS)
        img.paste(t, (6 + c * (tw + 6), 6 + r * (th + 6)))
    return img


def corner_pair(k=0, z=7, box=52):
    x, y = A.face_tile(k)
    after = ATLAS.crop((x, y, x + box, y + box)).convert('RGB')
    src = DECK_SRC.crop(A.card_cell(k)).resize((A.CARD_W, A.CARD_H), Image.LANCZOS)
    before = src.convert('RGB').crop((0, 0, box, box))
    W = box * z
    img = Image.new('RGB', (W * 3 + 40, W), (18, 20, 24))
    img.paste(before.resize((W, W), Image.NEAREST), (0, 0))
    img.paste(after.resize((W, W), Image.NEAREST), (W + 20, 0))
    # 第三格：侧面取样色块（8x8）放大 —— 牌侧现在就是它
    bx, by = A.card_side_block(k)
    sw = ATLAS.crop((bx, by, bx + 8, by + 8)).convert('RGB').resize((W, W), Image.NEAREST)
    img.paste(sw, (W * 2 + 40, 0))
    return img


def edge_view():
    """低角度看台面上的牌：验证 0.12 厚的侧面已是牌环色（不再有白边）。"""
    kw = dict(hands=[9, 9, 9, 9], discard=14, pile=5, controls=0, dealer=1, actor=1,
              acolor=2, direction=0, dseat=2)
    faces = U.scene(1, **kw)
    eye = (M.OUT_X[1] * 30 + 16, 7.5, (-M.OUT_Z[1] * 30) - 4)
    img = R.render_textured(faces, eye, (M.OUT_X[1] * 13.5, 1.0, -M.OUT_Z[1] * 13.5),
                            W=620, H=430, fov=46)
    return img


def main():
    sheet = card_sheet()
    pair = corner_pair()
    edge = edge_view()
    fly0 = Image.open(os.path.join(HERE, '_flyzoom0.png'))
    fly1 = Image.open(os.path.join(HERE, '_flyzoom1.png'))
    cd = Image.open(os.path.join(HERE, '_cd_mock.png'))

    f = A.font(24)
    fs = A.font(19)
    # ---- 图 1：牌面 ----
    W = max(sheet.width, pair.width + edge.width + 30, 980)
    H = 46 + sheet.height + 56 + max(pair.height, edge.height)
    img = Image.new('RGB', (W, H), (14, 16, 20))
    d = ImageDraw.Draw(img)
    d.text((16, 12), '① 56 张牌面：白纸边已填成「围在牌那一圈环的颜色」（整张牌 = 长方形彩边卡）',
           font=f, fill=(255, 220, 120))
    img.paste(sheet, (16, 46))
    y2 = 46 + sheet.height + 52
    d.text((16, y2 - 34), '② 同一张牌的左上角：素材原样（白纸边） → 填充后（环色） → 侧面取样色块',
           font=f, fill=(255, 220, 120))
    img.paste(pair, (16, y2))
    img.paste(edge, (16 + pair.width + 30, y2))
    d.text((16 + pair.width + 34, y2 + 8),
           '低角度看台面：牌的\n四个侧面 = 各自的环色\n（原来是一圈纸白）',
           font=fs, fill=(225, 225, 230))
    img.save(os.path.join(HERE, '_deliver_cards.png'))

    # ---- 图 2：出牌飞行 ----
    W = max(fly0.width, cd.width)
    H = 46 + fly0.height + 46 + fly1.height + 46 + cd.height
    img = Image.new('RGB', (W, H), (14, 16, 20))
    d = ImageDraw.Draw(img)
    d.text((16, 12), '③ 出牌飞行（上：从出牌座位的手牌中心飞到自己出牌区；下：发完牌从牌堆翻起始牌）',
           font=f, fill=(255, 220, 120))
    img.paste(fly0, (0, 46))
    img.paste(fly1, (0, 46 + fly0.height + 46))
    d.text((16, 46 + fly0.height + 14), '（同一时刻的 6 帧：t = 0 → 0.2 → 0.4 → 0.6 → 0.8 → 1.0）',
           font=fs, fill=(200, 205, 215))
    y3 = 46 + fly0.height + 46 + fly1.height + 14
    d.text((16, y3 - 2), '④ 出牌倒计时（屏幕上方 action bar，每秒刷新；斗地主那版实现里其实没有，这是按你的意思补的）',
           font=f, fill=(255, 220, 120))
    img.paste(cd, (16, y3 + 34))
    img.save(os.path.join(HERE, '_deliver_fly.png'))
    print('saved _deliver_cards.png / _deliver_fly.png')


if __name__ == '__main__':
    main()
