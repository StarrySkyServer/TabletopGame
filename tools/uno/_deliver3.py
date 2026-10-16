# -*- coding: utf-8 -*-
"""临时脚本：本轮交付图 —— ① 牌沿"淡边"修复前后对照；② 悬浮倒计时在真实眼位下的位置模拟。"""
import math
import os
import sys

from PIL import Image, ImageDraw

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import render_base as R
import render_uno as U
import build_model as M
import uno_assets as A

HERE = os.path.dirname(os.path.abspath(__file__))
DECK = Image.open(A.DECK_SRC).convert('RGBA')


def old_fill(tile):
    """上一版的算法（按亮度向环色插值）—— 留"淡淡的边框"的那版，只为对照。"""
    w, h = tile.size
    out = tile.copy()
    px = out.load()
    mask = A.paper_mask(tile)
    ring = A.ring_color_of(tile, mask, 5)
    lum_ring, lum_paper = A._lum(ring), A._lum(A.PAPER)
    span = max(1.0, lum_paper - lum_ring)
    for j in range(h):
        for i in range(w):
            if mask[j * w + i]:
                px[i, j] = (ring[0], ring[1], ring[2], 255)
    near = bytearray(w * h)
    for j in range(h):
        for i in range(w):
            if not mask[j * w + i]:
                continue
            for dj in range(-2, 3):
                for di in range(-2, 3):
                    ni, nj = i + di, j + dj
                    if 0 <= ni < w and 0 <= nj < h:
                        near[nj * w + ni] = 1
    for j in range(h):
        for i in range(w):
            k = j * w + i
            if not near[k] or mask[k]:
                continue
            r, g, b, a = px[i, j]
            if a <= 0:
                continue
            wgt = (A._lum((r, g, b)) - lum_ring) / span
            if wgt <= 0.06:
                continue
            wgt = min(1.0, wgt)
            px[i, j] = (int(round(r + (ring[0] - r) * wgt)), int(round(g + (ring[1] - g) * wgt)),
                        int(round(b + (ring[2] - b) * wgt)), a)
    return out, ring


def edge_pair(k=0, box=40, z=9):
    cell = DECK.crop(A.card_cell(k)).resize((A.CARD_W, A.CARD_H), Image.LANCZOS)
    old, ring = old_fill(cell)
    new, _ = A.fill_paper_with_ring(cell)
    W = box * z
    img = Image.new('RGB', (W * 2 + 24, W + 124), (18, 20, 26))
    d = ImageDraw.Draw(img)
    f, fs = A.font(21), A.font(16)
    for idx, (t, tag1, tag2) in enumerate((
            (old, '旧：边界像素按亮度插值',
             '→ 留了一条比环色和描边都亮的「淡边」'),
            (new, '新：边界像素直接刷成环色',
             '→ 外围只有一种颜色（描边是牌自带的花纹）'))):
        x = idx * (W + 24)
        img.paste(t.convert('RGB').crop((0, 0, box, box)).resize((W, W), Image.NEAREST),
                  (x, 62))
        d.text((x + 4, 8), tag1, font=f, fill=(255, 220, 120))
        d.text((x + 4, 36), tag2, font=fs, fill=(215, 220, 230))
        px = t.load()
        col = [px[i, 120] for i in range(0, 4)]
        d.text((x + 4, 62 + W + 26), '牌左缘 x=0..3 像素：%s' % (col,), font=fs,
               fill=(190, 196, 208))
    img.save(os.path.join(HERE, '_deliver_edge.png'))
    print('saved _deliver_edge.png', img.size)


def countdown_shot(seat=1, dseat=2):
    """真实眼位 + 把「悬浮牌子」按 3D 投影画在它该在的位置。"""
    kw = dict(hands=[9, 9, 9, 9], discard=14, pile=5, controls=U.PLAY_BTN,
              dealer=dseat, actor=dseat, acolor=2, direction=0, dseat=dseat)
    W, H, fov = 900, 600, 70
    faces = U.scene(seat, **kw)
    ox, oz = M.OUT_X[seat], M.OUT_Z[seat]
    eye = (ox * 48.0, 10.92, -oz * 48.0)
    # 与 UnoTable.standAtSeat 同一套朝向：看向「方块底往上 0.6 格」⇒ pitch ≈ -18.8°
    # （台面在 +15/16 格处，所以模型空间里那个瞄准点是 (0.6-0.9375)*16 = -5.4 单位）
    target = (0, -5.4, 0)
    img = R.render_textured(faces, eye, target, W=W, H=H, fov=fov)

    # 复刻 render_base.render_textured 的投影，求「牌桌正上方 1.3 格」的屏幕位置
    ex, ey, ez = eye
    tx, ty, tz = target
    fwd = (tx - ex, ty - ey, tz - ez)
    fl = math.sqrt(sum(c * c for c in fwd))
    fwd = tuple(c / fl for c in fwd)
    up0 = (0, 1, 0)
    right = (fwd[1] * up0[2] - fwd[2] * up0[1], fwd[2] * up0[0] - fwd[0] * up0[2],
             fwd[0] * up0[1] - fwd[1] * up0[0])
    rl = math.sqrt(sum(c * c for c in right)) or 1
    right = tuple(c / rl for c in right)
    up = (right[1] * fwd[2] - right[2] * fwd[1], right[2] * fwd[0] - right[0] * fwd[2],
          right[0] * fwd[1] - right[1] * fwd[0])
    f = 1.0 / math.tan(math.radians(fov) / 2)

    def proj(p):
        d = (p[0] - ex, p[1] - ey, p[2] - ez)
        z = sum(d[i] * fwd[i] for i in range(3))
        x = sum(d[i] * right[i] for i in range(3))
        y = sum(d[i] * up[i] for i in range(3))
        return (W / 2 + (x / z) * f * (H / 2), H / 2 - (y / z) * f * (H / 2))

    # 牌子实体位置 = origin + COUNTDOWN_LIFT 格（1 格 = 16 模型单位）；
    # root 动画又抬了 0.25 单位 → 模型空间 y = 0.25 + 1.3*16
    px, py = proj((0.0, 0.25 + 0.62 * 16, 0.0))
    d = ImageDraw.Draw(img)
    f1, f2 = A.font(26), A.font(22)
    row1 = ('轮到 P2', (255, 226, 120), f1)
    row2 = [('剩余 ', (210, 210, 210), f1), ('38', (245, 215, 90), f1), (' 秒', (210, 210, 210), f1)]
    w1 = d.textlength(row1[0], font=row1[2])
    w2 = sum(d.textlength(t, font=f) for t, _, f in row2)
    bw = max(w1, w2) + 20
    bx, by = px - bw / 2, py - 34
    d.rectangle([bx, by, bx + bw, by + 66], fill=(0, 0, 0))
    d.text((px - w1 / 2, by + 4), row1[0], font=row1[2], fill=row1[1])
    x2 = px - w2 / 2
    for t, c, f in row2:
        d.text((x2, by + 36), t, font=f, fill=c)
        x2 += d.textlength(t, font=f)
    d.text((12, 10), '悬浮倒计时牌子（name tag）：牌桌原点正上方 0.62 格 · 按真实入座眼位投影',
           font=A.font(19), fill=(255, 255, 255))
    img.save(os.path.join(HERE, '_deliver_cd.png'))
    print('saved _deliver_cd.png 标牌投影点 = (%.0f, %.0f)' % (px, py))


def main():
    edge_pair()
    countdown_shot()


if __name__ == '__main__':
    main()
