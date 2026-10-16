# -*- coding: utf-8 -*-
"""用**真实入座眼位**（3 格远、眼高 0.68 格）渲染，核对庄家徽记 / 回合箭头从本人视角可不可见。"""
import os
import sys

from PIL import Image, ImageDraw

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import render_base as R
import render_uno as U
import build_model as M

HERE = os.path.dirname(os.path.abspath(__file__))


def main():
    kw = dict(hands=[7, 12, 7, 7], discard=14, pile=5, controls=U.PLAY_BTN,
              dealer=1, actor=1, acolor=0, direction=0, seats=0x55, dseat=2)
    for seat in (0, 1):
        faces = U.scene(seat, **kw)
        ox, oz = M.OUT_X[seat], M.OUT_Z[seat]
        # UnoTableRay 的眼位约定：eye = OUT*48（3 格）、高 10.92 单位；
        # 渲染器内部对 z 做了取反（rot_pt/apex），所以这里与 render() 一样写 -oz。
        eye = (ox * 48.0, 10.92, -oz * 48.0)
        img = R.render_textured(faces, eye, (0, 3, 0), W=900, H=600, fov=70)
        d = ImageDraw.Draw(img)
        d.text((10, 8), 'seat %d real eye (3 blocks, 0.68 above tabletop)' % seat,
               fill=(255, 255, 255))
        img.save(os.path.join(HERE, '_eyereal_p%d.png' % seat))
    print('saved _eyereal_p0.png / _eyereal_p1.png')


if __name__ == '__main__':
    main()
