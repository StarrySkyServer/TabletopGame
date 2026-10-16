# -*- coding: utf-8 -*-
"""用「真机眼位」渲染：眼高 10.92 局部单位、距桌心 41.6 局部单位。"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import render_base as R, render_uno as U, build_model as M
from PIL import Image, ImageDraw
EYE_OUT, EYE_Y = 41.6, 10.92   # 与 verify_ray / UnoTableRay 一致

def shot(out, viewer=1, out_dist=EYE_OUT, eye_y=EYE_Y, **kw):
    faces = U.scene(viewer, **kw)
    ox, oz = M.OUT_X[viewer], M.OUT_Z[viewer]
    img = R.render_textured(faces, (ox*out_dist, eye_y, -oz*out_dist), (0, 3, 0),
                            W=900, H=620, fov=70)
    ImageDraw.Draw(img).text((10, 8), 'eye=(%.1f, %.1f)' % (out_dist, eye_y), fill=(255,255,0))
    img.save(out)

BASE = dict(hands=[9, 24, 9, 9], discard=14, pile=5, controls=U.PLAY_BTN,
            dealer=1, actor=1, acolor=2, sel=2, btn_owner=2)
shot('_eye_many.png', **BASE)
shot('_eye_many_close.png', out_dist=30.0, **BASE)
shot('_eye_7.png', hands=[7,7,7,7], discard=14, pile=5, controls=U.PLAY_BTN,
     dealer=1, actor=1, acolor=2, btn_owner=2)
print('ok')
