# -*- coding: utf-8 -*-
"""把「拾取图」半透明叠在「同相机渲染图」上，直观看是否有『看得见但点不到』。"""
import math, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import render_base as R, render_uno as U, build_model as M
from PIL import Image

EYE_OUT, EYE_Y = 41.6, 10.92
W, H, FOV = 640, 440, 70

def render_same(viewer, hands, sel=None, tag='24'):
    faces = U.scene(viewer, hands=hands, sel=sel, controls=0)
    tx, tz = M.OUT_X[viewer], M.OUT_Z[viewer]
    img = R.render_textured(faces, (tx*EYE_OUT, EYE_Y, tz*EYE_OUT), (0, 3, 0),
                            W=W, H=H, fov=FOV)
    img.save('_rv_%s.png' % tag)
    return img

for tag, hands, sel in (('24', [9,24,9,9], 2), ('41', [7,41,7,7], 25)):
    rv = render_same(1, hands, sel, tag)
    pm = Image.open('_pickmap_%s.png' % tag).convert('RGB')
    out = Image.blend(rv, pm, 0.45)
    out = out.resize((W*2, H*2), Image.NEAREST)
    out.save('_overlay_%s.png' % tag)
print('ok')
