# -*- coding: utf-8 -*-
"""核对「入座归位」的站位点：示意图 + 叠加到用户截图。"""
import os, sys, math
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from PIL import Image, ImageDraw

OUT_X = [1, 0, -1, 0]
OUT_Z = [0, -1, 0, 1]
SEAT_LABEL = ['东 P1', '南 P2', '西 P3', '北 P4']
RADIUS = 3.0            # 棋心 -> 站位点（格）
HALF = 1.5              # 3x3 棋盘半宽

# ---------- A. 示意图（棋盘 + 站位点 + 朝向） ----------
S = 90                  # 每格像素
W = H = int(S * 9)
im = Image.new('RGB', (W, H), (18, 20, 26))
d = ImageDraw.Draw(im)
ox = oy = W / 2.0

def w2p(gx, gz):        # 格坐标 -> 像素（+x 向右，+z 向下）
    return (ox + gx * S, oy + gz * S)

# 棋盘 3x3
d.rectangle([w2p(-HALF, -HALF), w2p(HALF, HALF)], fill=(7, 46, 73), outline=(150, 150, 150), width=3)
# 网格辅助线
for k in range(-4, 5):
    d.line([w2p(k, -4.2), w2p(k, 4.2)], fill=(45, 48, 58))
    d.line([w2p(-4.2, k), w2p(4.2, k)], fill=(45, 48, 58))
d.rectangle([w2p(-HALF, -HALF), w2p(HALF, HALF)], fill=(7, 46, 73), outline=(170, 170, 170), width=3)
d.ellipse([ox-5, oy-5, ox+5, oy+5], fill=(220, 60, 60))

for j in range(4):
    px, pz = w2p(OUT_X[j]*RADIUS, OUT_Z[j]*RADIUS)
    # 站位方块（1 格）
    d.rectangle([px-S/2, pz-S/2, px+S/2, pz+S/2], outline=(120, 200, 120), width=3)
    d.ellipse([px-7, pz-7, px+7, pz+7], fill=(90, 230, 120))
    # 朝向箭头 -> 棋心
    L = 0.75
    ex, ez = w2p(OUT_X[j]*(RADIUS-L)*0.0 + 0, 0)  # 占位
    ux, uz = -OUT_X[j], -OUT_Z[j]
    ax0, az0 = px + ux*14, pz + uz*14
    ax1, az1 = px + ux*(S*0.92), pz + uz*(S*0.92)
    d.line([ax0, az0, ax1, az1], fill=(255, 90, 90), width=4)
    # 箭头头部
    ang = math.atan2(az1-az0, ax1-ax0)
    for s in (+1, -1):
        d.line([ax1, az1,
                ax1 - 16*math.cos(ang - s*0.5), az1 - 16*math.sin(ang - s*0.5)],
               fill=(255, 90, 90), width=4)
    d.text((px-24, pz+S*0.62), SEAT_LABEL[j], fill=(230, 230, 120))
    d.text((px-30, pz-S*0.62-14), '%.1f 格' % RADIUS, fill=(150, 210, 255))
d.text((8, 6), '入座归位示意：站位 = 棋心 + 朝外方向 x %.1f 格（棋盘 3x3，外隔 1 格），朝向 = 棋心' % RADIUS,
       fill=(255, 235, 120))
im = im.crop((int(ox-4.6*S), int(oy-4.6*S), int(ox+4.6*S), int(oy+4.6*S)))
im.save('_seat_schematic.png')

# ---------- B. 叠加到用户截图 ----------
p = r'D:/图片/Screenshots/屏幕截图 2026-10-15 161116.png'
shot = Image.open(p).convert('RGB')
# 实测：棋心 (592.5, 456.5)、每格 126.3px
cx, cy, cell = 592.5, 456.5, 126.3
d2 = ImageDraw.Draw(shot)
for j in range(4):
    px = cx + OUT_X[j]*RADIUS*cell
    py = cy + OUT_Z[j]*RADIUS*cell
    d2.ellipse([px-9, py-9, px+9, py+9], outline=(0, 255, 0), width=4)
    d2.text((px+12, py-8), '%s' % SEAT_LABEL[j], fill=(0, 255, 0))
    # 从站位到棋心的连线
    d2.line([px, py, cx, cy], fill=(0, 255, 0), width=2)
shot.save('_seat_overlay.png')

print('ok')
print('数值：棋心 = base(1.5, 1.5)，站位 = 棋心 + OUT*%.1f' % RADIUS)
for j in range(4):
    print('  座位%d %s: 局部坐标 = (%.1f, %.1f)  -> 世界 (baseX%+.1f, baseZ%+.1f)'
          % (j+1, SEAT_LABEL[j], 1.5 + OUT_X[j]*RADIUS, 1.5 + OUT_Z[j]*RADIUS,
             OUT_X[j]*RADIUS, OUT_Z[j]*RADIUS))
    yaw = math.degrees(math.atan2(-(-OUT_X[j]*RADIUS), -OUT_Z[j]*RADIUS))
    print('       朝向 yaw = %.1f°（面向棋心），pitch ≈ %.1f°'
          % (yaw, math.degrees(math.atan2(0.6-1.62, RADIUS))))
