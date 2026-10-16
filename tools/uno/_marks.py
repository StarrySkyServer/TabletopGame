# -*- coding: utf-8 -*-
"""只渲染桌面标记，用于核对 圆盘/方向/庄家/行动 的相对位置。"""
import math, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import render_base as R, render_uno as U, build_model as M
from PIL import Image, ImageDraw

KEEP = ('dealer', 'dir_', 'color_disc', 'turn_')
def marks(viewer, out, eye_rel=(0.0, 1.0), **kw):
    V = U.build_vars(viewer=viewer, **kw)
    faces, _, add = R.collect_scene(R.LAYOUT_SRC, V)
    for b in R.GEO['bones']:
        nm = b['name']
        if not nm.startswith(KEEP):
            continue
        if abs(R.eff_scale(R.LAYOUT_SRC, nm, V)) < 1e-6:
            continue
        add(nm)
    ox, oz = M.OUT_X[viewer], M.OUT_Z[viewer]
    ax, az = M.AX_X[viewer], M.AX_Z[viewer]
    # 相机在玩家斜上方（略偏右一点，避免俯视退化）
    ex = ox * 46 + ax * 12
    ez = -oz * 46 - az * 12
    img = R.render_textured(faces, (ex, 40, ez), (0, 0, 0), W=800, H=800, fov=40)
    img.save(out)

# viewer=1(南)：右手边 = 东(座位0)。dealer=2(西=左)，actor=3(北)，颜色=蓝
marks(1, '_m_v1.png', hands=[7,7,7,7], discard=27, pile=5, controls=0,
      dealer=2, actor=3, acolor=3, direction=0, dseat=3)
print('ok')
