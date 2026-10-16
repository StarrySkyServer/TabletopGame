# -*- coding: utf-8 -*-
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import render_base as R, render_uno as U, build_model as M

def shot(out, viewer=1, fov=26, eye=(0.5, 130, -0.5), **kw):
    faces = U.scene(viewer, **kw)
    img = R.render_textured(faces, eye, (0, 0, 0), W=1000, H=1000, fov=fov)
    img.save(out)
    return img

# 四人各 7 张；弃牌由座位 3 打出（acolor=1 蓝）
shot('_t_wide.png', hands=[7,7,7,7], discard=27, pile=5, controls=0, dealer=1, actor=3,
     acolor=1, direction=1, dseat=3)
# 出牌座位=2（西），方向逆时针
shot('_t_wide2.png', hands=[7,9,7,7], discard=52, pile=5, controls=0, dealer=2, actor=2,
     acolor=3, direction=0, dseat=2)
print('ok')
