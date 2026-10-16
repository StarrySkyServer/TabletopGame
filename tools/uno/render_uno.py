# -*- coding: utf-8 -*-
"""离线预览 UNO 牌桌：不开服务器就能检查 4 个座位视角与卡片布局。"""
import math
import os
import sys

from PIL import Image, ImageDraw

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import render_base as R
import build_model as M
import uno_assets as A
import build_table as T

CARD_SLOTS = 108
SEAT_YAW = M.SEAT_YAW
OUT_X, OUT_Z = M.OUT_X, M.OUT_Z

# 准星编码（与 build_table.HV 一致）：每 viewer 7 bit，base 128
HOVER_NONE = T.HOVER_NONE
HOVER_BTN_BASE = T.HOVER_BTN_BASE


def hover_card(slot):
    """手牌槽 slot(0..107) 的准星值。"""
    return T.HOVER_CARD_BASE + slot


def hover_button(k):
    """按钮槽 k(0..3) 的准星值。"""
    return T.HOVER_BTN_BASE + k


def pack_hover(values):
    """values: 4 个 viewer 的准星值（列表/元组），打包成 uno_hover 属性。"""
    v = 0
    for k in range(4):
        v |= (values[k] & T.HOVER_MAX) << (T.HOVER_BITS * k)
    return v


def select_card(slot):
    """手牌槽 slot(0..107) 被选中时的 uno_sel 值；slot<0 表示无选中。"""
    return 0 if slot < 0 else T.HOVER_CARD_BASE + slot


def build_vars(viewer=1, hands=None, discard=None, sel=None, controls=0,
               dealer=1, actor=1, btn_owner=None, acolor=0, direction=0,
               pile=5, hover=0, dseat=0, deal_n=255, seats=0, show=0, fly=None,
               laser=None):
    """hands: [n0,n1,n2,n3]（每座手牌张数）；discard: 弃牌堆顶牌 id（**负数 = 台面上没有弃牌**）；
    sel: 被选中的手牌槽（0..107）或 None；hover: int 或 4 元素序列；
    dseat: 打出中央那张牌的座位（1..4，0=未知）；deal_n: 发牌进度（255=已完成）；
    seats: uno_seats 打包值（每座 2 位：0 正常 / 1 托管 / 2 离线托管）；
    show: 定庄展示态（1 = 区 1..4 的牌摆到各自出牌区、所有人可见）；
    fly: (mode, t) 出牌飞行快照 —— mode 0 = 从手牌、1 = 从牌堆翻；t = 进度 0..1（见 apply_flight）；
    laser: (seat, idx, u, v) 定位器激光命中快照 —— idx = 区内序号、(u, v) = 牌面局部坐标
    （v 为服务端折算值，选中牌已含 RAISE；None = 四座全隐藏）。"""
    hands = hands or [7, 7, 7, 7]
    discard = 0 if discard is None else discard
    zones = {}
    slot = 0
    for s in range(4):
        for _ in range(hands[s]):
            zones[slot] = s + 1
            slot += 1
    if discard >= 0:                 # discard < 0 = 台面上暂时没有弃牌（例如定庄展示阶段）
        zones[slot] = 5
        slot += 1

    V = R.Vars({'viewer_mode': viewer})
    for i in range(16):
        val = 0
        for k in range(7):
            n = i * 7 + k
            if n < CARD_SLOTS:
                val |= (zones.get(n, 0) & 7) << (3 * k)
        V['pk_c%d' % i] = val
    V['pk_sel'] = select_card(-1 if sel is None else sel)
    V['pk_hover'] = hover if isinstance(hover, int) else pack_hover(hover)
    # 定位器激光：每座位 7 位，值 = round((坐标+OFFSET)*8)，127 = 隐藏（与 Java quantizeLaser 同式）。
    # laser = (seat, idx, u, v)：v 是服务端折算后的值（选中牌已加 RAISE）。
    pk_lu = 0
    pk_lv = 0
    pk_ls = 0
    for s in range(4):
        if laser is not None and s == laser[0]:
            pk_lu |= round((laser[2] + 3.3) * 8) << (7 * s)
            pk_lv |= round((laser[3] + 6.3) * 8) << (7 * s)
            pk_ls |= (laser[1] & 127) << (7 * s)
        else:
            pk_lu |= 127 << (7 * s)
            pk_lv |= 127 << (7 * s)
            pk_ls |= 127 << (7 * s)
    V['pk_laser_u'] = pk_lu
    V['pk_laser_v'] = pk_lv
    V['pk_laser_s'] = pk_ls
    V['pk_controls'] = controls
    V['pk_pile'] = pile
    V['pk_deal'] = deal_n
    if btn_owner is None:
        btn_owner = viewer + 1
    # 位域与 UnoTableEntity.TABLE_* 一致（共 16 bit）：
    # 0..2 dealer / 3..5 actor / 6..8 btn_owner / 9..10 acolor / 11 dir / 12..14 dseat / 15 show
    V['pk_table'] = (dealer & 7) | ((actor & 7) << 3) | ((btn_owner & 7) << 6) \
                    | ((acolor & 3) << 9) | ((direction & 1) << 11) \
                    | ((dseat & 7) << 12) | ((show & 1) << 15)

    for n in range(CARD_SLOTS):
        V['z%d' % n] = zones.get(n, 0)

    counts = [0, 0, 0, 0]
    dc = 0
    for n in range(CARD_SLOTS):
        z = zones.get(n, 0)
        V['s%d' % n] = counts[z - 1] if 1 <= z <= 4 else (dc if z == 5 else 0)
        if 1 <= z <= 4:
            counts[z - 1] += 1
        elif z == 5:
            dc += 1
    for j in range(4):
        V['h%dc' % j] = counts[j]
        # 手牌的行数/间距在动画里内联算（math.floor(v.s/ROW_SIZE)），这里不再需要 v.ra/v.rb。
        fn = min(counts[j], M.FAKE_MAX)
        V['f%dn' % j] = fn
        V['f%dsp' % j] = 0 if fn <= 1 else min(2.8, 35.2 / (fn - 1))
    V['dpc'] = dc
    V['pile_n'] = min(pile, 5)
    V['dealer'] = dealer
    V['actor'] = actor
    V['btn_owner'] = btn_owner
    V['acolor'] = acolor
    V['dir'] = direction
    V['dseat'] = dseat
    V['dsx'] = M.OUT_X[max(0, dseat - 1)] * M.PLAY_R
    V['dsz'] = M.OUT_Z[max(0, dseat - 1)] * M.PLAY_R
    V['deal_n'] = deal_n
    V['seats'] = seats
    V['pk_seats'] = seats
    V['show_all'] = show
    # 托管机器人站位（镜像 build_table.build_pre_animation 的 v.bo/bx/bz）：
    # **固定在「第一行满 20 张」时最左牌的左手边**（BOT_OFF20），不随手牌张数变化。
    for j in range(4):
        bo = M.BOT_OFF20
        V['bo%d' % j] = bo
        V['bx%d' % j] = M.BOT_X[j] + M.AX_X[j] * bo
        V['bz%d' % j] = M.BOT_Z[j] + M.AX_Z[j] * bo
    V['hv'] = hover if isinstance(hover, int) else hover[viewer]
    V['sv'] = select_card(-1 if sel is None else sel)
    for k in range(4):
        V['button_%d' % k] = (controls >> (4 * k)) & 15
    cnt = sum(1 for k in range(4) if V['button_%d' % k])
    V['button_count'] = cnt
    acc = 0
    for k in range(4):
        V['button_offset_%d' % k] = (acc - (cnt - 1) / 2) * M.BUTTON_GAP
        acc += 1 if V['button_%d' % k] else 0
    if fly is not None:
        apply_flight(V, fly[0], fly[1])
    return V


def apply_flight(V, mode, t):
    """把 pre_animation 里那组飞行变量按进度 t 灌进 V（与 build_table.build_pre_animation 同式）。

    mode 0 = 从出牌座位的手牌中心飞出（normal 出牌）；1 = 从中央牌堆顶翻出（起始牌）。
    t = 0 起飞、1 落桌；t>=1 时 v.fgo=0（交还静止位姿）。
    """
    e = 1 - (1 - t) ** 2                       # 与 v.fe 同式：减速
    if mode == 1:
        sx, sy, sz = M.DRAW_X, T.FLY_PILE_Y, M.DRAW_Z
    else:
        d = max(0, V['dseat'] - 1)
        sx, sy, sz = M.HAND_X[d], M.HAND_Y + T.FLY_LIFT, M.HAND_Z[d]
    V['fgo'] = 0 if t >= 1 else 1
    V['fx'] = sx + (V['dsx'] - sx) * e
    V['fy'] = sy + (M.DISC_Y - sy) * e + T.FLY_ARC * math.sin(math.radians(180 * t))
    V['fz'] = sz + (V['dsz'] - sz) * e
    V['frx'] = (180 if mode == 1 else M.CARD_PITCH) * (1 - e)


def scene(viewer, **kw):
    V = build_vars(viewer=viewer, **kw)
    faces, _, add = R.collect_scene(R.LAYOUT_SRC, V)
    cache = {}
    for b in R.GEO['bones']:
        if not b.get('cubes'):
            continue
        # 必须用**有效** scale（含祖先）：开关骨骼靠父级 scale=0 隐藏整棵子树
        if abs(R.eff_scale(R.LAYOUT_SRC, b['name'], V)) < 1e-6:
            continue
        add(b['name'])
    return faces


def render(viewer, out, **kw):
    faces = scene(viewer, **kw)
    ox, oz = OUT_X[viewer], OUT_Z[viewer]
    eye = (ox * 58.0, 24.0, -oz * 58.0)
    img = R.render_textured(faces, eye, (0, 2, 0), W=900, H=600, fov=64)
    d = ImageDraw.Draw(img)
    d.text((12, 10), 'viewer seat %d (P%d)  eye=(%.0f,%.0f,%.0f)' %
           (viewer, viewer + 1, eye[0], eye[1], eye[2]), fill=(255, 255, 255))
    img.save(out)
    return img


def top(out, **kw):
    faces = scene(1, **kw)
    # 俯视：不能正上方直视（相机 up=(0,1,0) 会退化），偏一点角度 + 小 fov 看桌心
    img = R.render_textured(faces, (5, 44, -5), (0, 0, 0), W=760, H=760, fov=34)
    img.save(out)
    return img


def pack(*actions):
    """按「屏幕从左到右」的动作列表打包 controls（数组下标 = 4 位槽下标）。"""
    v = 0
    for slot, act in enumerate(actions):
        v |= (A.CODE[act] & 15) << (4 * slot)
    return v


# 与 uno_assets.BUTTON_GROUPS 一一对应（左下角起，slot0 在屏幕最左）
PLAY_BTN = pack('cancel', 'hint', 'draw', 'play')      # 0x1245
DRAW_BTN = pack('play', 'skip')                        # 0x0031
SETTLE_BTN = pack('exit', 'next')                      # 0x0067
COLOR_BTN = pack('c_red', 'c_yellow', 'c_green', 'c_blue')   # 0xBA98


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    # 四人各 7 张、中央 1 张弃牌、抽牌堆 5 张。
    # btn_owner 必须随 viewer 变化（buttons_visibility: btn_owner == viewer_mode+1），
    # 否则该视角自己的按钮组会被隐藏；不要像以前那样用一个固定 btn_owner 渲染四个视角。
    base = dict(hands=[7, 7, 7, 7], discard=0, pile=5, controls=PLAY_BTN, dealer=1, actor=2,
                acolor=0, direction=0)
    tiles = [render(i, os.path.join(here, '_view_p%d.png' % i),
                    btn_owner=i + 1, **base) for i in range(4)]
    sheet = Image.new('RGB', (900 * 2, 600 * 2), (10, 12, 16))
    for i, im in enumerate(tiles):
        sheet.paste(im, ((i % 2) * 900, (i // 2) * 600))
    sheet.resize((900, 600)).save(os.path.join(here, '_views.png'))

    # 自己的手牌 24 张（两行）+ 4 个按钮；第 3 张处于"选中"状态（黑框）
    # 注意 hands 是按座位下标给的：viewer=1 时要把 24 张放在 hands[1]，否则
    # 那 24 张会落到对手身上、只显示成一叠 "?" 牌背。
    # 注意：buttons_visibility 要求 btn_owner == viewer_mode+1，故 viewer=1 时必须让
    # btn_owner=2（= 默认值 viewer+1）。此前误传 btn_owner=1 会让整排按钮被隐藏。
    render(1, os.path.join(here, '_view_many.png'), hands=[9, 24, 9, 9], discard=14, pile=3,
           controls=PLAY_BTN, dealer=1, actor=1, acolor=2, hover=hover_card(2), sel=2)
    render(1, os.path.join(here, '_view_color.png'), hands=[7, 7, 7, 7], discard=52, pile=5,
           controls=COLOR_BTN, dealer=1, actor=1, acolor=3)
    render(1, os.path.join(here, '_view_draw.png'), hands=[8, 7, 7, 7], discard=27, pile=2,
           controls=DRAW_BTN, dealer=2, actor=1, acolor=1)
    render(2, os.path.join(here, '_view_settle.png'), hands=[0, 5, 3, 9], discard=33, pile=0,
           controls=SETTLE_BTN, dealer=2, actor=2, acolor=3)
    # 托管机器人（四座全开）+ 新庄家徽记位置：自己 24 张（两行），机器人应贴在第一行最左牌的左侧
    render(1, os.path.join(here, '_view_bot.png'), hands=[9, 24, 9, 9], discard=14, pile=3,
           controls=PLAY_BTN, dealer=1, actor=1, acolor=2, dseat=2, seats=0x55)
    # 四座位各来一张（每张庄家都是自己、都开托管），核对徽记与机器人相对手牌的位置
    bot_tiles = [render(i, os.path.join(here, '_view_bot_p%d.png' % i),
                        hands=[9, 9, 9, 9], discard=(14 + i), pile=5, controls=PLAY_BTN,
                        dealer=i + 1, actor=i + 1, acolor=i, direction=0, seats=0x55,
                        btn_owner=i + 1)
                 for i in range(4)]
    sheet = Image.new('RGB', (900 * 2, 600 * 2), (10, 12, 16))
    for i, im in enumerate(bot_tiles):
        sheet.paste(im, ((i % 2) * 900, (i // 2) * 600))
    sheet.resize((900, 600)).save(os.path.join(here, '_views_bot.png'))
    # 定庄比大小展示：四家各一张牌，摆在自己那侧的出牌区（谁抽到的牌放谁那侧）
    render(1, os.path.join(here, '_view_show.png'), hands=[1, 1, 1, 1], discard=-1, pile=5,
           controls=0, dealer=0, actor=0, acolor=0, direction=0, show=1, deal_n=255)
    # 出牌飞行：mode 0 = 从自己手牌飞到自己的出牌区（下方一排）；mode 1 = 从牌堆翻起始牌
    for mode in (0, 1):
        tiles = [render(1, os.path.join(here, '_fly_m%d_%02d.png' % (mode, int(t * 100))),
                        hands=[9, 9, 9, 9], discard=14, pile=5, controls=PLAY_BTN,
                        dealer=1, actor=1, acolor=2, dseat=2, fly=(mode, t))
                 for t in (0.0, 0.25, 0.5, 0.75, 1.0)]
        W, H = tiles[0].size
        sheet = Image.new('RGB', (W * len(tiles), H), (10, 12, 16))
        for i, im in enumerate(tiles):
            sheet.paste(im, (i * W, 0))
        sheet.resize((sheet.width // 3, sheet.height // 3)).save(
            os.path.join(here, '_view_fly%d.png' % mode))
    top(os.path.join(here, '_view_top.png'), **base)
    print('previews written')


if __name__ == '__main__':
    main()
