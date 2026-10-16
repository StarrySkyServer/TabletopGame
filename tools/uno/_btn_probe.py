# -*- coding: utf-8 -*-
"""分析按钮源素材的结构：白高光描边离边缘多远、白字离边缘多远。"""
import sys
import os
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import uno_assets as A

sheet = Image.open(A.BTN_SRC).convert('RGBA')


def code(px):
    r, g, b, a = px
    if a < 16:
        return '.'
    mx, mn = max(r, g, b), min(r, g, b)
    if mn >= 238 and mx - mn <= 14:
        return 'W'
    if mx <= 70:
        return 'D'
    if g > r + 30 and g > b + 30:
        return 'G'
    if mx - mn <= 20:
        return 'g'
    return '?'


for act in ('play', 'hint'):
    for state, y0 in (('normal', A.SHEET_Y_NORMAL), ('pressed', A.SHEET_Y_PRESSED)):
        c = A.SHEET_INDEX[act]
        box = (A.SHEET_PAD + c * A.SHEET_PITCH_X, y0,
               A.SHEET_PAD + c * A.SHEET_PITCH_X + A.SHEET_CELL_W, y0 + A.SHEET_CELL_H)
        img = sheet.crop(box)
        px = img.load()
        print('== %s %s %s' % (act, state, img.size))
        for y in (10, 20, 60, 100, 110):
            print('  y=%3d ' % y + ''.join(code(px[x, y]) for x in range(0, img.width, 4)))
