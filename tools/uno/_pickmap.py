# -*- coding: utf-8 -*-
"""从真机眼位逐像素做射线拾取，生成「拾取图」；再与「渲染图」逐像素比对，
就能定量看出每张牌有多大的可点区域（以及有没有『看得见但点不到』）。"""
import math, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import render_base as R, render_uno as U, build_model as M
from PIL import Image, ImageDraw

EYE_OUT, EYE_Y = 41.6, 10.92
MAX_DIST = 8.0
SCALE = 16.0
W, H, FOV = 640, 440, 70

def make_vars(viewer, hands, sel=None, controls=0, **kw):
    zones = {}
    slot = 0
    for s in range(4):
        for _ in range(hands[s]):
            zones[slot] = s + 1
            slot += 1
    return U.build_vars(viewer=viewer, hands=hands, sel=sel, controls=controls, **kw), zones

def hand_centers(viewer, count, sel_idx):
    out = []
    for idx in range(count):
        row = idx // M.ROW_SIZE
        in_row = idx - row * M.ROW_SIZE
        rc = min(M.ROW_SIZE, count - row * M.ROW_SIZE)
        sp = 0 if rc <= 1 else min(2.8, 35.2 / (rc - 1))
        o = (in_row - (rc - 1) / 2.0) * sp
        lifted = (idx == sel_idx)
        outL = M.HAND_RADIUS - row * M.ROW_OUT - (M.RAISE_COS if lifted else 0)
        tx, tz = M.OUT_X[viewer], M.OUT_Z[viewer]
        ax, az = M.AX_X[viewer], M.AX_Z[viewer]
        fx, fy, fz = tx*M.OG, M.SG, tz*M.OG
        out.append((tx*outL + ax*o + fx*M.CARD_SIZE[1]/2,
                    M.HAND_Y + row*M.ROW_UP + 0.01*in_row
                    + (M.RAISE_SIN if lifted else 0) + fy*M.CARD_SIZE[1]/2,
                    tz*outL + az*o + fz*M.CARD_SIZE[1]/2))
    return out

def rect_hit(o, d, c, u, hu, v, hv):
    n = (u[1]*v[2]-u[2]*v[1], u[2]*v[0]-u[0]*v[2], u[0]*v[1]-u[1]*v[0])
    den = d[0]*n[0]+d[1]*n[1]+d[2]*n[2]
    if abs(den) < 1e-8: return -1
    t = ((c[0]-o[0])*n[0]+(c[1]-o[1])*n[1]+(c[2]-o[2])*n[2])/den
    if t <= 0 or t > MAX_DIST: return -1
    p = (o[0]+d[0]*t-c[0], o[1]+d[1]*t-c[1], o[2]+d[2]*t-c[2])
    return t if abs(sum(p[i]*u[i] for i in range(3))) <= hu and \
                abs(sum(p[i]*v[i] for i in range(3))) <= hv else -1

def run(viewer, hands, sel=None, controls=0, tag='p'):
    V, zones = make_vars(viewer, hands, sel=sel, controls=controls)
    count = hands[viewer]
    own = [n for n in range(M.CARD_SLOTS) if zones.get(n, 0) == viewer + 1]
    sel_idx = own.index(sel) if (sel is not None and sel in own) else -1
    centers = hand_centers(viewer, count, sel_idx)
    tx, tz = M.OUT_X[viewer], M.OUT_Z[viewer]
    ax, az = M.AX_X[viewer], M.AX_Z[viewer]
    eye = (tx*EYE_OUT, EYE_Y, tz*EYE_OUT)
    up = (-tx*M.SG, M.OG, -tz*M.SG)
    # 相机：朝桌心 = -OUT；up 取世界 y
    fwd = (-tx, 0.0, -tz)
    right = (fwd[1]*0-fwd[2]*1, fwd[2]*0-fwd[0]*0, fwd[0]*1-fwd[1]*0)
    rl = math.sqrt(sum(c*c for c in right)); right = tuple(c/rl for c in right)
    cup = (right[1]*fwd[2]-right[2]*fwd[1], right[2]*fwd[0]-right[0]*fwd[2],
           right[0]*fwd[1]-right[1]*fwd[0])
    f = 1.0/math.tan(math.radians(FOV)/2)
    img = Image.new('RGB', (W, H), (0, 0, 0))
    px = img.load()
    counts = {}
    for py in range(H):
        for pxx in range(W):
            sx = (pxx - W/2)/(f*(H/2))
            sy = -(py - H/2)/(f*(H/2))
            d = tuple((fwd[i] + right[i]*sx + cup[i]*sy)*SCALE for i in range(3))
            best, bestT = -1, 0.0
            for idx, c in enumerate(centers):
                t = rect_hit(eye, d, c, (ax, 0, az), M.CARD_SIZE[0]/2, up, M.CARD_SIZE[2]/2)
                if t > 0 and (bestT <= 0 or t < bestT-1e-6):
                    best, bestT = idx, t
            if best >= 0:
                counts[best] = counts.get(best, 0) + 1
                col = ((best*53+40) % 200 + 55, (best*97+90) % 200 + 55, (best*31+150) % 200 + 55)
                px[pxx, py] = col
    img.save('_pickmap_%s.png' % tag)
    # 渲染图（同样的相机）
    faces = U.scene(viewer, **{k: v for k, v in dict(hands=hands, sel=sel, controls=0).items()})
    return counts, img

counts, img = run(1, [9, 24, 9, 9], sel=2, tag='24')
counts2, img2 = run(1, [7, 41, 7, 7], sel=None, tag='41')
print('24 张：各 idx 可点像素数')
for idx in sorted(counts):
    row = idx // M.ROW_SIZE
    print('   idx=%-2d 行%d%s  px=%d' % (idx, row+1, '  <-- 第二行' if row == 1 else '', counts[idx]))
print('总计 %d px，未取到任何牌 %d px' % (sum(counts.values()), W*H - sum(counts.values())))
