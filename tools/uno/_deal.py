# -*- coding: utf-8 -*-
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import render_base as R, render_uno as U, build_model as M
from PIL import Image, ImageDraw

def shot(viewer, deal, out):
    faces = U.scene(viewer, hands=[7,7,7,7], discard=27, pile=0, controls=0,
                    dealer=1, actor=1, acolor=0, direction=0, dseat=3, deal_n=deal)
    ox, oz = M.OUT_X[viewer], M.OUT_Z[viewer]
    img = R.render_textured(faces, (ox*52, 30, -oz*52), (0, 3, 0), W=420, H=300, fov=60)
    d = ImageDraw.Draw(img)
    d.text((8, 6), 'deal_n=%s' % ('255' if deal == 255 else deal), fill=(255,255,0))
    img.save(out)

sheet = Image.new('RGB', (420*4, 300*2), (10,12,16))
for i, dn in enumerate((1, 2, 3, 4, 5, 6, 7, 255)):
    shot(1, dn, '_d_%d.png' % dn)
    sheet.paste(Image.open('_d_%d.png' % dn), ((i % 4)*420, (i//4)*300))
sheet.save('_deal_seq.png')
print('ok')
