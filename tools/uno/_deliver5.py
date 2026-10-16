# -*- coding: utf-8 -*-
"""本轮三项改动的交付核对图（_deliver_round4.png）：
  ① 托管机器人：固定站在「第一行满 20 张」时最左牌的左手边 —— 24 张 / 9 张位置完全一致
  ② 绿点常驻：每 tick 补一颗（寿命 0.18 秒）→ 不再闪烁
  ③ 实体碰撞箱恢复默认 0.001（捕获框退役，手牌点击交给「定位器」）
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import uno_assets as A
import render_uno as U
from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
BASE = dict(discard=14, pile=3, controls=U.PLAY_BTN, dealer=1, actor=1,
            acolor=2, dseat=2, seats=0x55)


def shot(name, hands):
    path = os.path.join(HERE, name)
    U.render(1, path, hands=hands, **BASE)
    return Image.open(path)


a = shot('_bot_24.png', [9, 24, 9, 9])
b = shot('_bot_9.png', [9, 9, 9, 9])
BOX = (60, 262, 430, 480)
Z = 1.55
ca = a.crop(BOX)
cb = b.crop(BOX)
w, h = int(ca.width * Z), int(ca.height * Z)
ca = ca.resize((w, h), Image.LANCZOS)
cb = cb.resize((w, h), Image.LANCZOS)

f, fs, fss = A.font(24), A.font(18), A.font(16)
W = w * 2 + 20 * 3 + 30
H = 92 + h + 168
img = Image.new('RGB', (W, H), (16, 18, 24))
d = ImageDraw.Draw(img)
d.text((24, 14), '① 托管机器人：固定站在「第一行满 20 张」时最左牌的左手边（不随手牌张数变化）',
       font=f, fill=(255, 220, 120))
d.text((24, 50), '对比：同一视角、同一座位，只改手牌张数 —— 机器人像素位置完全一致（牌越打越少也不飘）',
       font=fs, fill=(214, 220, 230))
img.paste(ca, (24, 84))
img.paste(cb, (24 * 2 + w, 84))
# 机器人所在竖线（两图对齐用）：整图坐标 x≈178（灰度本体 bbox 实测 152..~205）
gx = int(round((178 - BOX[0]) * Z))
for x0 in (24 + gx, 24 * 2 + w + gx):
    for yy in range(84, 84 + h, 14):
        d.line([(x0, yy), (x0, yy + 7)], fill=(255, 220, 90), width=3)
d.text((24 + w // 2 - 60, 84 + h + 6), '手牌 24 张（第一行 20 + 第二行 4）', font=fs,
       fill=(200, 206, 218))
d.text((24 * 2 + w + w // 2 - 40, 84 + h + 6), '手牌 9 张', font=fs, fill=(200, 206, 218))
d.text((24, 84 + h + 32),
       '（黄线 = 机器人位置：两图逐像素完全对齐；牌行会随张数重新居中，别被它带偏）',
       font=fss, fill=(255, 220, 120))

y = 84 + h + 74
for t, c in [
    ('② 绿点常驻：改为每 tick 补一颗（粒子寿命 0.18 秒，3 颗重叠）—— 不再是"一闪一闪"',
     (140, 235, 160)),
    ('③ 实体碰撞箱恢复默认 0.001（捕获框退役）：准星交互交给手持「定位器」的"使用"信号',
     (140, 200, 255)),
]:
    d.text((24, y), t, font=fss, fill=c)
    y += 26

img.save(os.path.join(HERE, '_deliver_round4.png'))
print('saved _deliver_round4.png', img.size)
