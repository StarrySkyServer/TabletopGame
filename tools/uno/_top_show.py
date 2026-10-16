# -*- coding: utf-8 -*-
"""定庄展示态俯视图：四张比大小的牌各摆在自己那侧的出牌区。"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import render_base as R
import render_uno as U

HERE = os.path.dirname(os.path.abspath(__file__))


def main():
    # viewer=1（南）：四家各一张牌（区 1..4），show=1 → 摆到各自出牌区
    faces = U.scene(1, hands=[1, 1, 1, 1], discard=-1, pile=5, controls=0,
                    dealer=0, actor=0, acolor=0, direction=0, show=1, deal_n=255,
                    seats=0, btn_owner=2)
    img = R.render_textured(faces, (0, 92, 0.1), (0, 0, 0), W=760, H=760, fov=40)
    img.save(os.path.join(HERE, '_top_show.png'))
    print('saved _top_show.png')


if __name__ == '__main__':
    main()
