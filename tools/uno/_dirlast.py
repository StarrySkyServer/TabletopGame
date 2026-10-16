# -*- coding: utf-8 -*-
"""最终核对：方向箭头 vs 颜色圆盘 的对称关系。"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import render_base as R, render_uno as U, build_model as M
from PIL import Image, ImageDraw

def label(im, text):
    d = ImageDraw.Draw(im)
    d.rectangle([0, 0, im.width, 24], fill=(12, 14, 18))
    d.text((8, 7), text, fill=(255, 235, 120))
    return im

# 1) 正俯视（相机在 -z 侧：屏幕上方 = 世界 +z = 座位1(南)的"正前方"）
faces = U.scene(1, hands=[7,7,7,7], discard=14, pile=5, controls=0,
                dealer=2, actor=3, acolor=0, direction=0, dseat=3)
top = R.render_textured(faces, (0.0, 120.0, -3.0), (0, 0, 0), W=900, H=620, fov=16)

# 2) 玩家 1 视角（眼位与真机一致）
faces2 = U.scene(1, hands=[7,7,7,7], discard=14, pile=5, controls=0,
                 dealer=2, actor=3, acolor=0, direction=1, dseat=3)
pv = R.render_textured(faces2, (0, 10.92, 41.6), (0, 3, 0), W=900, H=620, fov=70)

out = Image.new('RGB', (900, 1240), (12, 14, 18))
out.paste(label(top, 'A. 正俯视（上方=座位1的正前方）：红色=颜色圆盘(靠自己)  白色=方向箭头(越过牌堆)'),
          (0, 0))
out.paste(label(pv, 'B. 座位1 玩家视角：颜色圆盘在自己正前方，方向箭头在牌堆对面（同一半径）'),
          (0, 620))
out.save('_final_dir.png')
print('saved _final_dir.png')
