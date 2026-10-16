# -*- coding: utf-8 -*-
"""探针：确定按钮槽位在「入座玩家视角」下的左右顺序。

背景：BUTTON_GROUPS 的数组下标即 `controls` 的 4 位槽下标（slot0 在低 4 位），
但「slot0 在屏幕左边还是右边」取决于座位帧的 AX 轴方向，光看代码容易搞反。
本脚本用真实几何算出每个按钮在世界局部坐标里的中心，投影到观察者的
(right, forward) 基底上，打印横向坐标，并把真实按钮贴图拼成一张平面图目视复核。
"""
import os
import sys

from PIL import Image, ImageDraw

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import render_base as R
import render_uno as U
import uno_assets as A
import build_model as M

HERE = os.path.dirname(os.path.abspath(__file__))
OUT_X, OUT_Z = M.OUT_X, M.OUT_Z
AX_X, AX_Z = M.AX_X, M.AX_Z
BUTTON_RADIUS = M.BUTTON_RADIUS
BUTTON_GAP = M.BUTTON_GAP


def right_of(seat):
    """观察者的右方（世界局部 xz 单位向量）= up × OUT。"""
    ox, oz = OUT_X[seat], OUT_Z[seat]
    # up=(0,1,0)，OUT=(ox,0,oz)；up × OUT = (1*oz - 0*0, 0*ox - 0*oz, 0*0 - 1*ox)
    rx, rz = oz, -ox
    return rx, rz


def slot_centers(controls):
    """按 build_anim 的公式算出每个非空槽位的 (world_x, world_z)（局部坐标，单位 1/16 格）。"""
    codes = [(controls >> (4 * k)) & 15 for k in range(4)]
    cnt = sum(1 for c in codes if c)
    out = {}
    acc = 0
    for k in range(4):
        if codes[k]:
            off = (acc - (cnt - 1) / 2.0) * BUTTON_GAP
            out[k] = codes[k]
        acc += 1 if codes[k] else 0
    return out, codes, cnt


def probe(controls, label):
    codes = [(controls >> (4 * k)) & 15 for k in range(4)]
    print('== %s controls=0x%X  codes=%s' % (label, controls, codes))
    for seat in range(4):
        rx, rz = right_of(seat)
        nonempty, _, cnt = slot_centers(controls)
        acc = 0
        rows = []
        for k in range(4):
            if not codes[k]:
                continue
            off = (acc - (cnt - 1) / 2.0) * BUTTON_GAP
            px = OUT_X[seat] * BUTTON_RADIUS + AX_X[seat] * off
            pz = OUT_Z[seat] * BUTTON_RADIUS + AX_Z[seat] * off
            lateral = px * rx + pz * rz          # >0 = 观察者右侧
            rows.append((k, codes[k], lateral))
            acc += 1
        rows_sorted = sorted(rows, key=lambda r: -r[2])   # 屏幕从左到右
        desc = ' | '.join('slot%d(code=%d, 屏幕x=%+.1f)' % (k, c, x) for k, c, x in rows_sorted)
        print('   seat %d(P%d) 右=(%+d,%+d): 从左到右 -> %s' % (seat, seat + 1, rx, rz, desc))


def draw_flat(controls, title, out_path=None, canvas=None, y0=0):
    """把真实按钮贴图按几何位置拼成一张平面图（入座玩家俯视自己一侧）。"""
    seat = 1
    rx, rz = right_of(seat)
    nonempty, codes, cnt = slot_centers(controls)

    W, H = 900, 150
    img = canvas if canvas is not None else Image.new('RGB', (W, H), (16, 18, 24))
    d = ImageDraw.Draw(img)
    scale = 16.0
    cx, cy = W // 2, y0 + 92
    acc = 0
    for k in range(4):
        if not codes[k]:
            continue
        off = (acc - (cnt - 1) / 2.0) * BUTTON_GAP
        px = OUT_X[seat] * BUTTON_RADIUS + AX_X[seat] * off
        pz = OUT_Z[seat] * BUTTON_RADIUS + AX_Z[seat] * off
        lateral = (px * rx + pz * rz) * scale
        act = A.ACTIONS[codes[k] - 1]
        tile = A.btn_tile(act, 'normal')
        sub = R.ATLAS.crop((tile[0], tile[1], tile[0] + A.BTN_W, tile[1] + A.BTN_H))
        tw, th = int(A.BTN_W * 0.62), int(A.BTN_H * 0.62)
        sub = sub.resize((tw, th), Image.LANCZOS)
        x = int(cx + lateral - tw / 2)
        y = int(cy - th / 2)
        if act.startswith('c_'):
            # 选色按钮是程序绘制的圆角色块，素材表里没有，这里直接画
            col = A.UNO_COLORS[act]
            dd = ImageDraw.Draw(img)
            dd.rounded_rectangle([x, y, x + tw, y + th], radius=10,
                                 fill=(int(col[0] * .86), int(col[1] * .86), int(col[2] * .86)),
                                 outline=(255, 255, 255))
        else:
            img.paste(sub, (x, y), sub)
        d.text((x, y + th + 4), 'slot%d %s' % (k, act), fill=(230, 230, 230))
        acc += 1

    d.text((12, y0 + 10), title, fill=(255, 255, 255))
    d.text((12, y0 + 30), '入座玩家视角 · 光标左侧 == 屏幕左侧', fill=(160, 160, 160))
    if out_path:
        img.save(out_path)
        print('flat -> ' + out_path)
    return img


def main():
    probe(0x1245, '正常出牌(取消 提示 抽牌 出牌)')
    probe(0x31, '抽牌后(出牌 跳过)')
    probe(0x67, '结算(退出 下一局)')
    probe(0xBA98, '选色(红 黄 绿 蓝)')

    sheet = Image.new('RGB', (900, 600), (16, 18, 24))
    draw_flat(0x1245, 'A 正常出牌：取消 提示 抽牌 出牌', canvas=sheet, y0=0)
    draw_flat(0x31, 'B 抽牌后：出牌 跳过', canvas=sheet, y0=150)
    draw_flat(0x67, 'C 结算：退出 下一局', canvas=sheet, y0=300)
    draw_flat(0xBA98, 'D 选色：红 黄 绿 蓝', canvas=sheet, y0=450)
    sheet.save(os.path.join(HERE, '_probe_buttons.png'))
    print('flat -> _probe_buttons.png')


if __name__ == '__main__':
    main()
