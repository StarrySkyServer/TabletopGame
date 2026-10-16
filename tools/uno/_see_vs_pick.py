# -*- coding: utf-8 -*-
"""「看得见 vs 点得到」逐牌定量：把每张手牌真实渲染出来的四边形投影到屏幕，
在四边形内部均匀采样，用 UnoTableRay 的数学打射线，统计命中该牌的比例。
比例低 = 看得见但点不到（或点到的其实是别的牌）。"""
import math, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import render_base as R, render_uno as U, build_model as M

EYE_OUT, EYE_Y = 41.6, 10.92
MAX_DIST, SCALE = 8.0, 16.0
PAD_U, PAD_V = 0.0,0.0
W, H, FOV = 640, 440, 70

def rect_hit(o, d, c, u, hu, v, hv):
    n = (u[1]*v[2]-u[2]*v[1], u[2]*v[0]-u[0]*v[2], u[0]*v[1]-u[1]*v[0])
    den = d[0]*n[0]+d[1]*n[1]+d[2]*n[2]
    if abs(den) < 1e-8: return -1
    t = ((c[0]-o[0])*n[0]+(c[1]-o[1])*n[1]+(c[2]-o[2])*n[2])/den
    if t <= 0 or t > MAX_DIST: return -1
    p = (o[0]+d[0]*t-c[0], o[1]+d[1]*t-c[1], o[2]+d[2]*t-c[2])
    return t if abs(sum(p[i]*u[i] for i in range(3))) <= hu and \
                abs(sum(p[i]*v[i] for i in range(3))) <= hv else -1

def hand_centers(viewer, count, sel_idx):
    res = []
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
        res.append((tx*outL + ax*o + fx*M.CARD_SIZE[1]/2,
                    M.HAND_Y + row*M.ROW_UP + 0.01*in_row
                    + (M.RAISE_SIN if lifted else 0) + fy*M.CARD_SIZE[1]/2,
                    tz*outL + az*o + fz*M.CARD_SIZE[1]/2))
    return res

def analyse(viewer, hands, sel=None, label=''):
    zones = {}
    slot = 0
    for s in range(4):
        for _ in range(hands[s]):
            zones[slot] = s + 1
            slot += 1
    V = U.build_vars(viewer=viewer, hands=hands, sel=sel,
                     controls=U.PLAY_BTN, dealer=1, actor=viewer, acolor=0)
    count = hands[viewer]
    own = [n for n in range(M.CARD_SLOTS) if zones.get(n, 0) == viewer + 1]
    sel_idx = own.index(sel) if (sel is not None and sel in own) else -1
    centers = hand_centers(viewer, count, sel_idx)
    tx, tz = M.OUT_X[viewer], M.OUT_Z[viewer]
    ax, az = M.AX_X[viewer], M.AX_Z[viewer]
    eye = (tx*EYE_OUT, EYE_Y, tz*EYE_OUT)
    up = (-tx*M.SG, M.OG, -tz*M.SG)
    # 相机与 render_textured 一致：fwd = normalize(target-eye)，up0=(0,1,0)
    target = (0, 3, 0)
    fwd = tuple(target[i]-eye[i] for i in range(3))
    fl = math.sqrt(sum(c*c for c in fwd)); fwd = tuple(c/fl for c in fwd)
    right = (fwd[1]*0-fwd[2]*1, fwd[2]*0-fwd[0]*0, fwd[0]*1-fwd[1]*0)
    rl = math.sqrt(sum(c*c for c in right)); right = tuple(c/rl for c in right)
    cup = (right[1]*fwd[2]-right[2]*fwd[1], right[2]*fwd[0]-right[0]*fwd[2],
           right[0]*fwd[1]-right[1]*fwd[0])
    f = 1.0/math.tan(math.radians(FOV)/2)
    def proj(p):
        d = tuple(p[i]-eye[i] for i in range(3))
        z = sum(d[i]*fwd[i] for i in range(3))
        x = sum(d[i]*right[i] for i in range(3)); y = sum(d[i]*cup[i] for i in range(3))
        return (W/2 + (x/z)*f*(H/2), H/2 - (y/z)*f*(H/2))
    # 每张牌的四角（渲染出来的卡面 quad：卡中心 ± U*halfU ± V*halfV）
    axU = (ax, 0.0, az)
    print('=== %s  viewer=P%d  张数=%d ===' % (label, viewer+1, count))
    bad_total = 0
    for idx in range(count):
        c = centers[idx]
        quad = []
        for du, dv in ((-1,-1), (1,-1), (1,1), (-1,1)):
            p = tuple(c[i] + axU[i]*M.CARD_SIZE[0]/2*du + up[i]*M.CARD_SIZE[2]/2*dv
                      for i in range(3))
            quad.append(proj(p))
        # 四边形内均匀采样
        S = 9
        tot = okn = 0
        firstw = {}
        for iu in range(S):
            for iv in range(S):
                u0 = -1 + 2*(iu+0.5)/S
                v0 = -1 + 2*(iv+0.5)/S
                # 双线性插值四角
                p2 = (1-u0)*(1-v0), (1+u0)*(1-v0), (1+u0)*(1+v0), (1-u0)*(1+v0)
                sx = sum(quad[k][0]*p2[k]/4 for k in range(4))
                sy = sum(quad[k][1]*p2[k]/4 for k in range(4))
                if not (0 <= sx < W and 0 <= sy < H):
                    continue
                tot += 1
                dd = tuple((fwd[i] + right[i]*((sx-W/2)/(f*(H/2)))
                            + cup[i]*(-(sy-H/2)/(f*(H/2))))*SCALE for i in range(3))
                best, bestT = -1, 0.0
                for j, cc in enumerate(centers):
                    t = rect_hit(eye, dd, cc, axU, M.CARD_SIZE[0]/2+PAD_U, up, M.CARD_SIZE[2]/2+PAD_V)
                    if t > 0 and (bestT <= 0 or t < bestT-1e-6):
                        best, bestT = j, t
                if best == idx:
                    okn += 1
                else:
                    firstw[best] = firstw.get(best, 0) + 1
        row = idx // M.ROW_SIZE + 1
        flag = ''
        if tot and okn / tot < 0.75:
            flag = '   <== 点不到！(被 %s 抢走)' % sorted(firstw.items(), key=lambda kv: -kv[1])[:3]
            bad_total += 1
        print('  idx=%-2d 行%d  可见采样=%3d 命中自己=%3d (%.0f%%)%s'
              % (idx, row, tot, okn, 100.0*okn/tot if tot else 0, flag))
    print('  -> 点不到比例低的牌数: %d / %d' % (bad_total, count))
    return bad_total

analyse(1, [9, 24, 9, 9], sel=2, label='两行 24 张')
analyse(1, [7, 41, 7, 7], sel=None, label='三行 41 张')
analyse(1, [7, 61, 7, 7], sel=None, label='四行 61 张')
