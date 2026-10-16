# -*- coding: utf-8 -*-
"""俯视整桌：核对庄家徽记与回合箭头（同半径、靠右、不穿模）以及托管机器人的落点。"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import render_base as R
import render_uno as U

HERE = os.path.dirname(os.path.abspath(__file__))


def main():
    # 座位 1（南）的视角参数：庄家=南、行动方=南 → 回合箭头在正前方，徽记在其右手侧
    faces = U.scene(1, hands=[7, 12, 7, 7], discard=14, pile=5, controls=0,
                    dealer=2, actor=2, acolor=0, direction=0, seats=0x55, dseat=2,
                    btn_owner=2)
    for name, eye in (('_top_all.png', (0, 96, 0.1)),):
        img = R.render_textured(faces, eye, (0, 0, 0), W=820, H=820, fov=40)
        img.save(os.path.join(HERE, name))
    print('saved _top_all.png')


if __name__ == '__main__':
    main()
