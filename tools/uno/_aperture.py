# -*- coding: utf-8 -*-
"""量「瞄准孔径」：从真机眼位逐像素拾取，统计每张牌能点到多少像素 + 行均值。"""
import math, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import build_model as M

EYE_OUT, EYE_Y = 41.6, 10.92
MAX_DIST, SCALE, W, H, FOV = 8.0, 16.0, 640, 440, 70

def go(pad_u, pad_v, count=24, eye_out=41.6, eye_y=EYE_Y):
    viewer = 1
    tx, tz, ax, az = M.OUT_X[viewer], M.OUT_Z[viewer], M.AX_X[viewer], M.AX_Z[viewer]
    up = (-tx*M.SG, M.OG, -tz*M.SG)
    axU = (ax, 0.0, az)
    halfU = M.CARD_SIZE[0]/2 + pad_u
    halfV = M.CARD_SIZE[2]/2 + pad_v
    cen = []
    for idx in range(count):
        row = idx // M.ROW_SIZE
        in_row = idx - row*M.ROW_SIZE
        rc = min(M.ROW_SIZE, count - row*M.ROW_SIZE)
        sp = 0 if rc <= 1 else min(2.8, 35.2/(rc-1))
        o = (in_row - (rc-1)/2.0)*sp
        outL = M.HAND_RADIUS - row*M.ROW_OUT
        fx, fy, fz = tx*M.OG, M.SG, tz*M.OG
        cen.append((tx*outL+ax*o+fx*0.06, M.HAND_Y+row*M.ROW_UP+0.01*in_row+fy*0.06,
                    tz*outL+az*o+fz*0.06))
    eye = (tx*eye_out, eye_y, tz*eye_out)
    tgt = (0, 3, 0)
    fwd = tuple(tgt[i]-eye[i] for i in range(3))
    fl = math.sqrt(sum(c*c for c in fwd)); fwd = tuple(c/fl for c in fwd)
    r = (fwd[1]*0-fwd[2]*1, fwd[2]*0-fwd[0]*0, fwd[0]*1-fwd[1]*0)
    rl = math.sqrt(sum(c*c for c in r)); r = tuple(c/rl for c in r)
    cup = (r[1]*fwd[2]-r[2]*fwd[1], r[2]*fwd[0]-r[0]*fwd[2], r[0]*fwd[1]-r[1]*fwd[0])
    f = 1.0/math.tan(math.radians(FOV)/2)
    def hit(o, d, c):
        n = (axU[1]*up[2]-axU[2]*up[1], axU[2]*up[0]-axU[0]*up[2], axU[0]*up[1]-axU[1]*up[0])
        den = d[0]*n[0]+d[1]*n[1]+d[2]*n[2]
        if abs(den) < 1e-8: return -1
        t = ((c[0]-o[0])*n[0]+(c[1]-o[1])*n[1]+(c[2]-o[2])*n[2])/den
        if t <= 0 or t > MAX_DIST: return -1
        p = (o[0]+d[0]*t-c[0], o[1]+d[1]*t-c[1], o[2]+d[2]*t-c[2])
        return t if abs(sum(p[i]*axU[i] for i in range(3))) <= halfU and \
                    abs(sum(p[i]*up[i] for i in range(3))) <= halfV else -1
    cnt = {}
    for py in range(H):
        for px_ in range(W):
            sxv = (px_-W/2)/(f*(H/2)); syv = -(py-H/2)/(f*(H/2))
            d = tuple((fwd[i]+r[i]*sxv+cup[i]*syv)*SCALE for i in range(3))
            best, bt = -1, 0.0
            for idx, c in enumerate(cen):
                t = hit(eye, d, c)
                if t > 0 and (bt <= 0 or t < bt-1e-6):
                    best, bt = idx, t
            if best >= 0:
                cnt[best] = cnt.get(best, 0) + 1
    rows = {}
    for idx, v in cnt.items():
        rows.setdefault(idx//M.ROW_SIZE, []).append(v)
    return cnt, rows

for pad in ((0.0, 0.0), (0.5, 0.35)):
    for count in (24, 41):
        cnt, rows = go(pad[0], pad[1], count, EYE_OUT)
        names = ['第%d行' % (r+1) for r in sorted(rows)]
        detail = ', '.join('%s均值=%.0fpx(最少%.0f)' % (
            n, sum(rows[r])/len(rows[r]), min(rows[r]))
            for r, n in zip(sorted(rows), names))
        print('余量 %.2f/%.2f  %2d 张：总可点 %6d px | %s' % (pad[0], pad[1], count,
              sum(cnt.values()), detail))

print()
print('=== 不同站位下各行瞄准孔径（余量 0.5/0.35）===')
for dist in (30.0, 41.6, 55.0, 70.0, 90.0):
    cnt, rows = go(0.5, 0.35, 24, dist)
    detail = ', '.join('第%d行=%.0fpx' % (r+1, sum(rows[r])/len(rows[r])) for r in sorted(rows))
    print('  眼距 %5.1f 局部单位：总可点 %6d px | %s' % (dist, sum(cnt.values()), detail))

print()
print('=== 眼高变化下各行瞄准孔径（眼距 41.6，余量 0.5/0.35）===')
for ey in (2.0, 4.0, 7.0, 10.92, 14.0, 20.0, 28.0):
    cnt, rows = go(0.5, 0.35, 24, 41.6, ey)
    detail = ', '.join('第%d行=%.0fpx' % (r+1, sum(rows[r])/len(rows[r])) for r in sorted(rows))
    print('  眼高 %5.2f：总可点 %6d px | %s' % (ey, sum(cnt.values()), detail))
