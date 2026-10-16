# -*- coding: utf-8 -*-
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import render_base as R, render_uno as U, build_model as M

def shot(out, viewer=1, fov=62, close=False, **kw):
    faces = U.scene(viewer, **kw)
    ox, oz = M.OUT_X[viewer], M.OUT_Z[viewer]
    d = 34.0 if close else 58.0
    eye = (ox*d, 18.0 if close else 24.0, -oz*d)
    img = R.render_textured(faces, eye, (0, 3, 0), W=900, H=600, fov=fov)
    img.save(out)

# 玩家视角（座位1=南），弃牌由座位0（东）打出，颜色=蓝，方向=顺时针
shot('_z_center.png', close=True, hands=[7,7,7,7], discard=27, pile=5, controls=0,
     dealer=3, actor=1, acolor=3, direction=0, dseat=0)
print('ok')
