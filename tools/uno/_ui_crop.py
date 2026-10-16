# -*- coding: utf-8 -*-
"""放大用户截图的关键区域，用于确认庄家徽记的目标位置。"""
from PIL import Image

SRC = 'D:/图片/Screenshots/屏幕截图 2026-10-15 162922.png'
im = Image.open(SRC).convert('RGB')
print('size', im.size)

crops = {
    'right': (660, 230, 1000, 470),      # D 徽记 + 红圈
    'left': (200, 350, 400, 520),        # 左侧黄色箭头
    'bottom': (450, 660, 660, 820),      # 底部黄色箭头
    'top': (420, 250, 700, 400),         # 顶部白色环形箭头
}
for name, box in crops.items():
    c = im.crop(box)
    s = 3 if max(c.size) < 400 else 2
    c.resize((c.width * s, c.height * s), Image.NEAREST).save(
        'D:/CodeProject/Gobang/TabletopGamePlugin/tools/uno/_ui_%s.png' % name)
print('ok')
