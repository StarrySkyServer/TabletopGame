# -*- coding: utf-8 -*-
import os, sys, math
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import render_base as R, render_uno as U, build_model as M
from PIL import Image

V = U.build_vars(viewer=1, hands=[7,7,7,7], discard=27, pile=5, controls=0,
                 dealer=2, actor=3, acolor=3, direction=0, dseat=3)
eye = (M.OUT_X[1]*46 + M.AX_X[1]*12, 40, -(M.OUT_Z[1]*46 + M.AX_Z[1]*12))
for nm in ('dealer_2', 'turn_2', 'dir_cw', 'color_disc_3'):
    faces, _, add = R.collect_scene(R.LAYOUT_SRC, V)
    add(nm)
    img = R.render_textured(faces, eye, (0, 0, 0), W=800, H=800, fov=40)
    img.save('_one_%s.png' % nm)
print('ok')
