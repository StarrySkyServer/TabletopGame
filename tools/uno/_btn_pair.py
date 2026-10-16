# -*- coding: utf-8 -*-
"""对比「按钮源素材」与「我们图集里的按钮」在常态 / 按下态下的差别。"""
import sys
import os
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import uno_assets as A

sheet = Image.open(A.BTN_SRC).convert('RGBA')
atlas = Image.open(A.OUT_ATLAS).convert('RGBA')

rows = []
names = ['play', 'cancel', 'hint', 'draw']
for act in names:
    c = A.SHEET_INDEX[act]
    src_n = sheet.crop((A.SHEET_PAD + c * A.SHEET_PITCH_X, A.SHEET_Y_NORMAL,
                        A.SHEET_PAD + c * A.SHEET_PITCH_X + A.SHEET_CELL_W,
                        A.SHEET_Y_NORMAL + A.SHEET_CELL_H))
    src_p = sheet.crop((A.SHEET_PAD + c * A.SHEET_PITCH_X, A.SHEET_Y_PRESSED,
                        A.SHEET_PAD + c * A.SHEET_PITCH_X + A.SHEET_CELL_W,
                        A.SHEET_Y_PRESSED + A.SHEET_CELL_H))
    for state, img in (('normal', src_n), ('pressed', src_p)):
        x, y = A.btn_tile(act, state)
        ours = atlas.crop((x, y, x + A.BTN_W, y + A.BTN_H))
        rows.append((act + '_' + state, img, ours))

W = A.BTN_W * 2 + 20
H = A.BTN_H
out = Image.new('RGBA', (W, H * len(rows)), (24, 24, 28, 255))
for i, (label, a, b) in enumerate(rows):
    out.paste(a.resize((A.BTN_W, A.BTN_H), Image.LANCZOS), (0, i * H), a.resize((A.BTN_W, A.BTN_H), Image.LANCZOS))
    out.paste(b.resize((A.BTN_W, A.BTN_H), Image.LANCZOS), (A.BTN_W + 20, i * H), b.resize((A.BTN_W, A.BTN_H), Image.LANCZOS))
    print('%2d %s' % (i, label))
out = out.resize((out.width * 2, out.height * 2), Image.NEAREST)
out.save(os.path.join(os.path.dirname(os.path.abspath(__file__)), '_btn_pair.png'))
print('rows 左=源素材 右=我们的图集')
