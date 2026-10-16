# -*- coding: utf-8 -*-
"""生成 UNO 牌桌的动画与客户端实体定义（几何体见 build_model.py）。"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import uno_assets as A
import build_model as M

ANIM_OUT = M.ANIM_OUT
ENT_OUT = M.ENT_OUT
RC_OUT = M.RC_OUT

CARD_SLOTS = M.CARD_SLOTS
FAKE_MAX = M.FAKE_MAX
ROW_SIZE = M.ROW_SIZE
CARD_PITCH = M.CARD_PITCH
DISC_Y = M.DISC_Y
PILE_Y = M.PILE_Y
PILE_STACK = M.PILE_STACK
PLAY_R = M.PLAY_R
COLOR_R = M.COLOR_R
DIR_R = M.DIR_R
DRAW_X, DRAW_Z = M.DRAW_X, M.DRAW_Z
HAND_X, HAND_Z = M.HAND_X, M.HAND_Z
HAND_Y = M.HAND_Y
AX_X, AX_Z = M.AX_X, M.AX_Z
OUT_X, OUT_Z = M.OUT_X, M.OUT_Z
SEAT_YAW = M.SEAT_YAW
BUTTON_RADIUS = M.BUTTON_RADIUS
BUTTON_Y = M.BUTTON_Y
BUTTON_GAP = M.BUTTON_GAP
MARK_RADIUS = M.MARK_RADIUS
MARK_Y = M.MARK_Y
DISC_MARK_Y = M.DISC_MARK_Y
r6 = M.r6
nest = M.nest
card_axes = M.card_axes
OG, SG = M.OG, M.SG
RAISE_COS, RAISE_SIN = M.RAISE_COS, M.RAISE_SIN
CARD_HALF_T = M.CARD_HALF_T
ROW_OUT, ROW_UP = M.ROW_OUT, M.ROW_UP

# ------------------------------------------------------------------ 出牌飞行动画
# 「还原斗地主那个出牌动画」（用户 2026-10-15）：斗地主出牌时牌会从手牌**飞到**桌面
# （它用 AnimateEntityPacket 播一次性 `animation.ddz.play_flight`，0.12 秒）。
# 这里做同一件事，但用**客户端自走时钟**（`q.delta_time` 累加）而不是动画包：
# 服务端只在出牌瞬间往 `tabletopgame:uno_fly` 写一个"会变的值"（bit1 = 翻转位，
# bit0 = 来源：0 手牌 / 1 牌堆），客户端在 pre_animation 里检测到变化就把进度清零，
# 之后每帧 `v.ft += q.delta_time/FLY_T` 自己往前走，飞完（v.ft>=1）自动交还给静止位姿。
#
# 为什么不用动画包（斗地主的做法）：同一条通道被两个动画写时后者覆盖前者，所以"飞行"
# 这个动画必须为**非飞行的 107 张牌逐字复读 layout 的表达式**，实测会让动画文件从
# 485KB 涨到 1.87MB。而 `q.delta_time` 这套是斗地主**自己**在 pre_animation 里就用的
# （见 ddz 的 v.sel_t0 选择弹跳动画），同一个客户端已验证可用，代价只有二十来行变量。
#
# 三条约束（别改坏）：
#  1. 服务端每次出牌都要让 `uno_fly` 的**值发生变化**（翻转位），否则客户端认不出"新的一次"；
#  2. 起点 = 出牌座位的手牌中心（`v.dseat`）；来源 bit 为 1 时起点是中央牌堆顶，且
#     rx 从 180° 转到 0° —— 先露牌背、飞一半翻成牌面，就是"从牌堆翻出一张牌"；
#  3. 终点必须与 layout 的静止位姿**逐字一致**（v.dsx/DISC_Y/v.dsz + (0,VYAW,0)），
#     飞行结束那一帧才不会有"啪"的一下跳变。
FLY_T = 0.20                # 飞行时长（秒）
FLY_ARC = 3.2               # 抛物弧最高点（模型单位）
FLY_LIFT = 1.6              # 出手点在静止手牌高度上抬一点
# 从牌堆翻起始牌时的出手点高度：牌堆顶 + 一点余量
FLY_PILE_Y = PILE_Y + 4 * PILE_STACK + 2.5

# ------------------------------------------------------------------ 准星 / 选中编码
# 编码规则与 HV/SV 表达式的唯一真源在 build_model（因为 card_axes 也要用 sel_of），
# 这里只做转发，避免两处各写一遍位宽而悄悄跑偏。
HOVER_NONE = 0
HOVER_CARD_BASE = M.HOVER_CARD_BASE
HOVER_BTN_BASE = M.HOVER_BTN_BASE
HOVER_BITS = M.HOVER_BITS
HOVER_MAX = M.HOVER_MAX

HV = M.HV
SV = M.SV


def vn(fn):
    """按 viewer_mode 选择表达式（0..3），越界回落到 0 号座位。"""
    out = fn(0)
    for k in (3, 2, 1):
        out = '(v.viewer_mode==%d?%s:%s)' % (k, fn(k), out)
    return out


VYAW = vn(lambda j: SEAT_YAW[j])


# 定庄展示位：四张比大小的牌挂在各自座位的手牌区（区值 1..4），展示态下摆到
# 「该座位自己的出牌区」（OUT[seat]*PLAY_R），平放、朝向 viewer —— 谁抽到的牌就摆谁那侧。
SHOW_X = {j + 1: r6(M.OUT_X[j] * PLAY_R) for j in range(4)}
SHOW_Z = {j + 1: r6(M.OUT_Z[j] * PLAY_R) for j in range(4)}


def card_layout_expr(n):
    """第 n 个卡槽在 layout 动画里的表达式：返回 (position[3], rotation[3], scale)。

    位置/朝向比"纯静止布局"多一层**出牌飞行**判定：`v.fgo==1`（正在飞）且本卡在弃牌区
    （`v.z{n}==5`）时，直接吃 pre_animation 算好的飞行位姿（v.fx/v.fy/v.fz/v.frx）。
    换句话说飞行是 layout 自己的一部分 —— 没有第二个动画去覆盖它，
    所以这里绝不能再复制一份表达式到别的地方（历史上"改一处漏三处"就是这么来的）。
    """
    z = 'v.z%d' % n
    fly = '(v.fgo==1&&%s==5)' % z
    xs, ys, zs, rx, ry = {}, {}, {}, {}, {}
    for j in range(4):
        x, y, zz = card_axes(n, j)
        xs[j + 1], ys[j + 1], zs[j + 1] = x, y, zz
        rx[j + 1], ry[j + 1] = str(CARD_PITCH), str(SEAT_YAW[j])
    # 出牌区顶牌：平铺在「打出这张牌的座位」自己的出牌区里（v.dsx/v.dsz），
    # 绕 y 轴按 viewer 转 —— 每个玩家看到的都朝向自己（需求：所有人看到的牌都往自己这边）。
    xs[5], ys[5], zs[5] = 'v.dsx', str(DISC_Y), 'v.dsz'
    rx[5], ry[5] = '0', VYAW
    # 定庄展示（v.show_all=1，只可能出现在区 1..4）：同上平放，位置换成"本方出牌区"。
    showing = '(v.show_all==1&&%s>=1&&%s<=4)' % (z, z)
    pos = ['(%s?v.fx:%s)' % (fly, '(%s?%s:%s)' % (showing, nest(z, SHOW_X, '0'), nest(z, xs))),
           '(%s?v.fy:%s)' % (fly, '(%s?%s:%s)' % (showing, str(DISC_Y), nest(z, ys))),
           '(%s?v.fz:%s)' % (fly, '(%s?%s:%s)' % (showing, nest(z, SHOW_Z, '0'), nest(z, zs)))]
    rot = ['(%s?v.frx:%s)' % (fly, '(%s?0:%s)' % (showing, nest(z, rx, str(CARD_PITCH)))),
           '(%s?%s:%s)' % (fly, VYAW, '(%s?%s:%s)' % (showing, VYAW, nest(z, ry, '0'))), '0']
    # 发牌动画：把「第 k 张」之前的牌一张张亮出来（v.deal_n 由服务端逐 tick 递增）。
    # 只在手牌区（z 1..4）生效；定庄展示态下所有 viewer 都看得见。
    # 出牌区（z=5，即起始牌 / 弃牌堆顶）同样要等**发完牌之后**才出现 ——
    # 需求：「每人发完 7 张牌之后，从牌堆抽出一张牌，这张牌刚好放在庄家面前」。
    # 注意 v.s{n} 是**该座位区内序号**，服务端每 tick +1 时四家同时亮出各自的第 k 张，
    # 效果与真实发牌一致（一圈一张）。
    scale = ('(%s==0?0:(%s?1:((%s>=1&&%s<=4)?((v.viewer_mode==(%s-1)&&%s<v.deal_n)?1:0):'
             '((v.deal_n>=255)?1:0))))' % (z, showing, z, z, z, 'v.s%d' % n))
    return pos, rot, scale


# ------------------------------------------------------------------ 定位器激光点
# 需求（2026-10-15 用户）：「做成像黑色框那样的，是在平面上的」—— 粒子（朝镜头的小方片）
# 贴 65° 斜面永远有悬浮/穿模感，退役；激光点改为模型薄片骨骼 laser_dot，**与手牌共用同一套
# 布局数学**，命中点的牌面局部坐标 (u, v) 由服务端经 uno_laser_u / uno_laser_v 广播。
#
# 两个分支（v.lcat：2 = 手牌卡 / 1 = 按钮）：
#  · 手牌：中心 = card_axes 的动态版（槽号 v.lidx、张数 v.lh、常量按 viewer 展开 ——
#    射线只测自己的手牌，命中的必然是 viewer 自己的牌）+ 选中抬升（v.lsel，与 card_axes
#    同一个 RAISE 向量）+ 法线半厚补偿（与 UnoTableRay.CARD_HALF_T 同一个数）；
#    再叠加 u*U轴 + v*V轴（U = 手牌横轴 AX，V = 卡牌上方向 -OUT*SG + y*OG）。
#  · 按钮：中心 = 按钮骨骼同款表达式（槽号 v.lidx 选 v.button_offset_*）；
#    服务端的按钮命中矩形是**竖直**的（V 轴 = (0,1,0)），而按钮片绕 U 轴向玩家倾 65°
#    —— 把命中点投影到斜面：斜面局部高度 = v*OG（(0,1,0)·up_b = cos65°），
#    再沿斜面法线 n_b 抬 0.012 让薄片浮在按钮面之上（不 z-fight、不被裁）。
# 旋转两个分支相同：rx=65、ry=VYAW（手牌 yaw = 自己座位的 yaw = VYAW，按钮本来就是 VYAW）。
LASER_LIFT = 0.012           # 按钮分支沿斜面法线的抬升（卡分支靠 0.008 片厚自然悬浮）


def laser_card_center():
    """手牌分支：命中卡的枢轴位置（含选中抬升与半厚补偿），三分量表达式。"""
    s = 'v.lidx'
    row = 'math.floor(%s/%d)' % (s, ROW_SIZE)
    in_row = '(%s-%d*%s)' % (s, ROW_SIZE, row)
    cnt = 'math.min(%d,v.lh-%d*%s)' % (ROW_SIZE, ROW_SIZE, row)
    sp = 'math.min(2.8,35.2/math.max(1,(%s-1)))' % cnt
    off = '((%s-(%s-1)/2)*%s)' % (in_row, cnt, sp)
    axx = vn(lambda j: str(AX_X[j]))
    axz = vn(lambda j: str(AX_Z[j]))
    ox = vn(lambda j: str(OUT_X[j]))
    oz = vn(lambda j: str(OUT_Z[j]))
    fnx = vn(lambda j: r6(OUT_X[j] * OG))       # 牌面法线（水平朝外 + 抬 25°）
    fnz = vn(lambda j: r6(OUT_Z[j] * OG))
    # 注意：这里**不含**选中抬升 —— 服务端把 RAISE 折进 v 坐标（见 pre_animation 解码注释），
    # 激光表达式与「未抬起的牌」同一把尺。
    # 命中点偏移：U 轴 = 手牌横轴 AX（水平）；V 轴 = 卡牌上方向 (-OUT*SG, +OG, -OUT*SG)
    # （长度 1：SG⊥OG）。x/z/y 三分量都要叠加，否则激光点恒在卡面中心、不随准星移动。
    x = ('%s+%s*(%s)+v.lu*%s-v.lv*%s*%s-%s*(%s*%s)+%s*%s'
         % (vn(lambda j: r6(HAND_X[j])), axx, off, axx, ox, r6(SG),
            ox, row, r6(ROW_OUT), fnx, r6(CARD_HALF_T)))
    y = ('%s+(%s)*%s+0.01*(%s)+v.lv*%s+%s'
         % (r6(HAND_Y), row, r6(ROW_UP), in_row, r6(OG), r6(SG * CARD_HALF_T)))
    z = ('%s+%s*(%s)+v.lu*%s-v.lv*%s*%s-%s*(%s*%s)+%s*%s'
         % (vn(lambda j: r6(HAND_Z[j])), axz, off, axz, oz, r6(SG),
            oz, row, r6(ROW_OUT), fnz, r6(CARD_HALF_T)))
    return x, y, z


def laser_button_center():
    """按钮分支：命中按钮的斜面位置（含竖直→斜面投影与法线抬升），三分量表达式。"""
    lof = ('(v.lidx==0?v.button_offset_0:(v.lidx==1?v.button_offset_1:'
           '(v.lidx==2?v.button_offset_2:v.button_offset_3)))')
    axx = vn(lambda j: str(AX_X[j]))
    axz = vn(lambda j: str(AX_Z[j]))
    ox = vn(lambda j: str(OUT_X[j]))
    oz = vn(lambda j: str(OUT_Z[j]))
    upx = vn(lambda j: r6(-OUT_X[j] * SG))      # 斜面「上」方向（= 卡牌上方向，per viewer）
    upz = vn(lambda j: r6(-OUT_Z[j] * SG))
    nx = vn(lambda j: r6(OUT_X[j] * OG))        # 斜面法线（朝玩家上方）
    nz = vn(lambda j: r6(OUT_Z[j] * OG))
    x = '%s+%s*(%s)+v.lu*%s+v.lv*%s*%s+%s*%s' % (
        vn(lambda j: r6(OUT_X[j] * BUTTON_RADIUS)), axx, lof, axx, r6(OG), upx,
        r6(LASER_LIFT), nx)
    y = '%s+v.lv*%s*%s+%s' % (r6(BUTTON_Y), r6(OG), r6(OG), r6(LASER_LIFT * SG))
    z = '%s+%s*(%s)+v.lu*%s+v.lv*%s*%s+%s*%s' % (
        vn(lambda j: r6(OUT_Z[j] * BUTTON_RADIUS)), axz, lof, axz, r6(OG), upz,
        r6(LASER_LIFT), nz)
    return x, y, z


def build_anim():
    L = {'root': {'position': [0, 0.25, 0]}}

    for n in range(CARD_SLOTS):
        z = 'v.z%d' % n
        pos, rot, scale = card_layout_expr(n)
        L['card_%d' % n] = {'position': pos, 'rotation': rot, 'scale': scale}
        # 高亮框：**选中优先于悬停** —— 一旦有选中牌（例如刚摸到的那张会被强制选中），
        # 就只有它亮，准星扫过别的牌不会把高亮带跑（需求：「这时候不能碰其他的来控它的突出」）。
        # 没有选中牌时才用悬停高亮（SV==0 即「本 viewer 无选中」）。
        L['highlight_%d' % n] = {
            'scale': '((%s>=1&&%s<=4)&&(%s==%d||(%s==0&&%s==%d)))?1:0'
                     % (z, z, SV, HOVER_CARD_BASE + n, SV, HV, HOVER_CARD_BASE + n)}

    for s in range(4):
        # 定庄展示期间不画对手的"?"牌背（那两张牌不是手牌，是摆在出牌区的比大小牌）
        L['fake_vis_%d' % s] = {'scale': '((v.show_all==0)&&(v.viewer_mode!=%d))?1:0' % s}
        for i in range(FAKE_MAX):
            off = '(%d-(v.f%dn-1)/2)*v.f%dsp' % (i, s, s)
            L['fake_%d_%d' % (s, i)] = {
                'position': ['%s+%d*(%s)' % (r6(HAND_X[s]), AX_X[s], off),
                             r6(HAND_Y + 0.01 * i),
                             '%s+%d*(%s)' % (r6(HAND_Z[s]), AX_Z[s], off)],
                'rotation': [CARD_PITCH, SEAT_YAW[s], 0],
                # 逐张发牌：对手的牌背同样一张张出现（i < v.deal_n）
                'scale': '(v.f%dn>%d&&%d<v.deal_n)?1:0' % (s, i, i),
            }

    L['buttons_visibility'] = {
        'scale': '((v.viewer_mode>=0&&v.viewer_mode<=3)&&'
                 '(v.btn_owner==(v.viewer_mode+1)||v.btn_owner==5))?1:0'}

    # 定位器激光点：位置 = 手牌 / 按钮两分支（见 laser_card_center / laser_button_center），
    # 旋转与手牌卡 / 按钮片一致（rx=65、ry=VYAW）—— 薄片与被贴面**完全共面**。
    cx, cy, cz = laser_card_center()
    bx, by, bz = laser_button_center()
    L['laser_dot'] = {
        'position': ['(v.lcat==2?%s:(v.lcat==1?%s:0))' % (cx, bx),
                     '(v.lcat==2?%s:(v.lcat==1?%s:0))' % (cy, by),
                     '(v.lcat==2?%s:(v.lcat==1?%s:0))' % (cz, bz)],
        'rotation': [CARD_PITCH, VYAW, 0],
        'scale': '(v.lvis&&(v.lcat==1||v.lcat==2))?1:0',
    }

    for k in range(4):
        bx = vn(lambda j: '%s+%d*v.button_offset_%d'
                % (r6(OUT_X[j] * BUTTON_RADIUS), AX_X[j], k))
        bz = vn(lambda j: '%s+%d*v.button_offset_%d'
                % (r6(OUT_Z[j] * BUTTON_RADIUS), AX_Z[j], k))
        L['button_slot%d' % k] = {
            'position': [bx, BUTTON_Y, bz],
            'rotation': [CARD_PITCH, VYAW, 0],
            'scale': '(math.mod(math.floor(v.pk_controls/%d),16)!=0)?(%s==%d?1.06:1):0'
                     % (16 ** k, HV, HOVER_BTN_BASE + k),
        }
    for slot, act in A.SLOT_ACTION_PAIRS:
        code = A.CODE[act]
        L['button_label_slot%d_%s' % (slot, act)] = {
            'scale': '(math.mod(math.floor(v.pk_controls/%d),16))==%d?1:0' % (16 ** slot, code)}
        L['button_pressed_slot%d_%s' % (slot, act)] = {
            'scale': '(%s==%d&&math.mod(math.floor(v.pk_controls/%d),16)==%d)?1:0'
                     % (HV, HOVER_BTN_BASE + slot, 16 ** slot, code)}

    # 中央牌堆：**横着放在桌子正中**（需求「牌堆就横着放中间」）。
    # 卡是竖版 5x7.5，ry 加 90° 后变成横版 7.5x5；VYAW 让每个视角看到的都是"横"的。
    # 靠一点点横向错位与微小偏摆做出"随手一叠"的观感。
    jx = [0, 0.55, -0.45, 0.35, -0.3]
    jz = [0, -0.5, 0.4, -0.35, 0.3]
    jr = [0, 3, -2, 4, -3]
    for p in range(5):
        L['pile_%d' % p] = {
            'position': [r6(DRAW_X + jx[p]), r6(PILE_Y + p * PILE_STACK), r6(DRAW_Z + jz[p])],
            'rotation': [0, '(%s+90+%d)' % (VYAW, jr[p]), 0],
            'scale': '(v.pile_n>%d)?1:0' % p}

    # 当前颜色圆盘：每个 viewer 都摆在自己正前方（OUT*COLOR_R），
    # 「所有人看到颜色标记都是往自己这边」（需求原话）。圆盘本身旋转对称，故不转。
    disc_x = vn(lambda j: r6(OUT_X[j] * COLOR_R))
    disc_z = vn(lambda j: r6(OUT_Z[j] * COLOR_R))
    for i in range(4):
        L['color_disc_%d' % i] = {
            'position': [disc_x, DISC_MARK_Y, disc_z], 'scale': '(v.acolor==%d)?1:0' % i}
    # 出牌方向标记：放在**与当前颜色圆盘关于桌心对称**的位置 ——
    # 颜色圆盘在 OUT*COLOR_R（自己正前方），方向标记在 -OUT*DIR_R（越过牌堆的正对面），
    # 半径一致、方向相反，两者点对称（需求「方向箭头跟颜色标记位置对称」）。
    # yaw 仍跟 viewer 走，四个座位看到的箭头都是正立的。
    dir_x = vn(lambda j: r6(-OUT_X[j] * DIR_R))
    dir_z = vn(lambda j: r6(-OUT_Z[j] * DIR_R))
    L['dir_cw'] = {'position': [dir_x, DISC_MARK_Y, dir_z], 'rotation': [0, VYAW, 0],
                   'scale': '(v.dir==0)?1:0'}
    L['dir_ccw'] = {'position': [dir_x, DISC_MARK_Y, dir_z], 'rotation': [0, VYAW, 0],
                    'scale': '(v.dir==1)?1:0'}

    for s in range(4):
        L['turn_%d' % s] = {
            'position': [r6(OUT_X[s] * MARK_RADIUS), MARK_Y, r6(OUT_Z[s] * MARK_RADIUS)],
            'rotation': [0, SEAT_YAW[s], 0],
            'scale': '(v.actor==%d)?1:0' % (s + 1)}
        L['dealer_%d' % s] = {
            # 与回合箭头**同半径**（OUT*MARK_RADIUS），再沿玩家右手方向 AX 偏 DEALER_SIDE：
            # 两者排在同一条弧线上、互不重叠（需求「跟黄色箭头刚好平行、不穿模、靠右一点」）。
            'position': [r6(OUT_X[s] * MARK_RADIUS + AX_X[s] * M.DEALER_SIDE), 0.45,
                         r6(OUT_Z[s] * MARK_RADIUS + AX_Z[s] * M.DEALER_SIDE)],
            'rotation': [0, SEAT_YAW[s], 0],
            'scale': '(v.dealer==%d)?1:0' % (s + 1)}
    # 托管机器人：位置由 pre_animation 固定算好（v.bx/v.bz = 20 张满行最左牌的左手边，
    # 不随张数变化），朝向与手牌同一个「面朝牌主」约定；v.seats 每座 2 位（0 正常 / 1 托管 / 2 离线托管）。
    for j in range(4):
        L['bot_%d' % j] = {
            'position': ['v.bx%d' % j, r6(M.BOT_Y), 'v.bz%d' % j],
            'rotation': [0, SEAT_YAW[j], 0],
            'scale': 'math.mod(math.floor(v.seats/%d),4)!=0?1:0' % (4 ** j)}

    def viewer_anim(idx):
        return {'loop': True, 'animation_length': 1,
                'bones': {'viewer_state': {'scale': 'v.viewer_mode=%d;return 1;' % idx}}}

    doc = {'format_version': '1.8.0', 'animations': {
        'animation.tabletopgame.uno.layout': {'loop': True, 'bones': L},
        'animation.tabletopgame.uno.viewer_p0': viewer_anim(0),
        'animation.tabletopgame.uno.viewer_p1': viewer_anim(1),
        'animation.tabletopgame.uno.viewer_p2': viewer_anim(2),
        'animation.tabletopgame.uno.viewer_p3': viewer_anim(3),
        'animation.tabletopgame.uno.hidden': viewer_anim(-1),
    }}
    os.makedirs(os.path.dirname(ANIM_OUT), exist_ok=True)
    with open(ANIM_OUT, 'w', encoding='utf-8') as fh:
        json.dump(doc, fh, ensure_ascii=False, separators=(',', ':'))
    print('anim: %d bones -> %s' % (len(L), ANIM_OUT))


def build_pre_animation():
    pa = []
    for i in range(16):
        pa.append("v.pk_c%d=q.property('%s');" % (i, M.cards_prop(i)))
    pa.append("v.pk_sel=q.property('tabletopgame:uno_sel');")
    pa.append("v.pk_hover=q.property('tabletopgame:uno_hover');")
    pa.append("v.pk_table=q.property('tabletopgame:uno_table');")
    pa.append("v.pk_controls=q.property('tabletopgame:uno_controls');")
    pa.append("v.pk_pile=q.property('tabletopgame:uno_pile');")

    for n in range(CARD_SLOTS):
        pa.append("v.z%d=math.mod(math.floor(v.pk_c%d/%d),8);" % (n, n // 7, 8 ** (n % 7)))

    pa.append("v.h0c=0;v.h1c=0;v.h2c=0;v.h3c=0;v.dpc=0;")
    for n in range(CARD_SLOTS):
        z = 'v.z%d' % n
        pick = ('(%s==1?v.h0c:(%s==2?v.h1c:(%s==3?v.h2c:(%s==4?v.h3c:(%s==5?v.dpc:0)))))'
                % (z, z, z, z, z))
        inc = ('v.h0c=v.h0c+(%s==1?1:0);v.h1c=v.h1c+(%s==2?1:0);v.h2c=v.h2c+(%s==3?1:0);'
               'v.h3c=v.h3c+(%s==4?1:0);v.dpc=v.dpc+(%s==5?1:0);') % (z, z, z, z, z)
        pa.append('v.s%d=%s;%s' % (n, pick, inc))

    # 手牌的行号/行内序号/该行张数/该行间距全部改由动画内联计算
    # （card_axes 里的 math.floor(v.s/ROW_SIZE)），不再需要 v.ra/v.rb/v.ras/v.rbs ——
    # 那套变量只能表达两行，第三行起就没法摆了。这里只剩对手手牌（单行）用的 f*n / f*sp。
    for j in range(4):
        pa.append('v.f%dn=math.min(v.h%dc,%d);'
                  'v.f%dsp=v.f%dn<=1?0:math.min(2.8,35.2/(v.f%dn-1));'
                  % (j, j, FAKE_MAX, j, j, j))

    pa.append("v.btn_owner=math.mod(math.floor(v.pk_table/64),8);")
    pa.append("v.dealer=math.mod(v.pk_table,8);")
    pa.append("v.actor=math.mod(math.floor(v.pk_table/8),8);")
    pa.append("v.acolor=math.mod(math.floor(v.pk_table/512),4);")
    pa.append("v.dir=math.mod(math.floor(v.pk_table/2048),2);")
    # bits 12..14 = 顶牌是哪个座位打出的（1..4，0 = 未知 -> 按东位放）
    pa.append("v.dseat=math.mod(math.floor(v.pk_table/4096),8);")
    # bit 15 = 定庄比大小展示中（1）：区 1..4 的牌改摆到该座位自己的出牌区、且所有 viewer 可见
    pa.append("v.show_all=math.mod(math.floor(v.pk_table/32768),2);")
    # 出牌区位置：打出这张牌的座位自己的出牌区（OUT*PLAY_R）。
    # 用嵌套三元展开（Molang 没有数组/查表）。
    pa.append("v.dsx=%s;v.dsz=%s;" % (
        nest('v.dseat', {j + 1: r6(M.OUT_X[j] * PLAY_R) for j in range(4)}, r6(M.OUT_X[0] * PLAY_R)),
        nest('v.dseat', {j + 1: r6(M.OUT_Z[j] * PLAY_R) for j in range(4)}, r6(M.OUT_Z[0] * PLAY_R))))
    # ---- 出牌飞行（见文件头 FLY_* 注释）----
    # 客户端自走时钟：检测 uno_fly 的变化 → 进度清零 → 每帧 +q.delta_time/FLY_T。
    # 时序（同一帧内顺序执行，别打乱）：
    #   v.fnew 先看"和上一帧比是否变了"，再把 v.fprev 更新成本帧值，最后推进 v.ft。
    pa.append("v.pk_fly=q.property('tabletopgame:uno_fly');")
    pa.append("v.fnew=(v.fprev>=0&&v.pk_fly!=v.fprev)?1:0;")
    pa.append("v.fprev=v.pk_fly;")
    pa.append("v.fmode=math.mod(v.pk_fly,2);")           # bit0：0 = 从手牌飞，1 = 从牌堆翻
    pa.append("v.ft=v.fnew?0:math.min(1,v.ft+q.delta_time/%s);" % r6(FLY_T))
    pa.append("v.fe=1-math.pow(1-v.ft,2);")              # 减速：出手快、落桌稳
    pa.append("v.fgo=(v.ft<1)?1:0;")
    pa.append("v.fsy=%s;" % ('(v.fmode==1?%s:%s)' % (r6(FLY_PILE_Y), r6(HAND_Y + FLY_LIFT))))
    pa.append("v.fsx=%s;" % ('(v.fmode==1?%s:%s)' % (
        r6(DRAW_X), nest('v.dseat', {j + 1: r6(HAND_X[j]) for j in range(4)}, r6(HAND_X[0])))))
    pa.append("v.fsz=%s;" % ('(v.fmode==1?%s:%s)' % (
        r6(DRAW_Z), nest('v.dseat', {j + 1: r6(HAND_Z[j]) for j in range(4)}, r6(HAND_Z[0])))))
    # 终点 = 出牌区静止位姿（与 card_layout_expr 的区 5 分支逐字一致）
    pa.append("v.fx=v.fsx+(v.dsx-v.fsx)*v.fe;")
    pa.append("v.fy=v.fsy+(%s-v.fsy)*v.fe+%s*math.sin(180*v.ft);" % (r6(DISC_Y), r6(FLY_ARC)))
    pa.append("v.fz=v.fsz+(v.dsz-v.fsz)*v.fe;")
    # 从牌堆翻出：rx 180°→0°（先露牌背、飞一半翻成牌面）；从手牌：65°→0°（放平落桌）
    pa.append("v.frx=%s*(1-v.fe);" % ('(v.fmode==1?180:%s)' % r6(CARD_PITCH)))
    # 逐张发牌进度：手牌区第 k 张在 v.sN < v.deal_n 时才显示。服务端非发牌阶段直接写 255。
    pa.append("v.deal_n=q.property('tabletopgame:uno_deal');")
    # 托管状态：每座位 2 位（0 正常 / 1 托管 / 2 离线托管），控制机器人骨骼显隐。
    pa.append("v.seats=q.property('tabletopgame:uno_seats');")
    # 托管机器人站位：**固定在「第一行满 20 张」时最左牌的左手边**，不随手里张数变化
    # （用户 2026-10-15：「那个托管机器人模型改为放20牌情况的最左边，固定不动」）。
    # BOT_OFF20 = -(20-1)/2 × sp20 - BOT_SIDE = -22.95：满行时与最左牌间隙恰为 BOT_GAP，
    # 张数更少时只会更靠左 ⇒ 任何张数都不穿模，也不需要逐帧重算。
    for j in range(4):
        pa.append("v.bo%d=%s;" % (j, r6(M.BOT_OFF20)))
        pa.append("v.bx%d=%s+%d*(v.bo%d);" % (j, r6(M.BOT_X[j]), M.AX_X[j], j))
        pa.append("v.bz%d=%s+%d*(v.bo%d);" % (j, r6(M.BOT_Z[j]), M.AX_Z[j], j))
    pa.append("v.pile_n=math.min(v.pk_pile,5);")
    pa.append("v.hv=%s;" % HV)
    pa.append("v.sv=%s;" % SV)
    # ---- 定位器激光点：解码 uno_laser_u / uno_laser_v / uno_laser_s（每座位 7 位，127 = 隐藏）----
    # 每个客户端只看自己座位那份（命中必然是自己的手牌 / 自己的按钮），四人互不干扰。
    # laser_s = 命中牌的「区内展示序号」（手牌布局表达式吃区内序号 v.sN；hover 里的
    # 绝对卡槽号对布局没用 —— 真实对局手牌是任意槽号集合，客户端推不出排名）。
    pa.append("v.pk_laser_u=q.property('tabletopgame:uno_laser_u');")
    pa.append("v.pk_laser_v=q.property('tabletopgame:uno_laser_v');")
    pa.append("v.pk_laser_s=q.property('tabletopgame:uno_laser_s');")
    pa.append("v.luq=%s;" % vn(lambda j: 'math.mod(math.floor(v.pk_laser_u/%d),128)' % (128 ** j)))
    pa.append("v.lvq=%s;" % vn(lambda j: 'math.mod(math.floor(v.pk_laser_v/%d),128)' % (128 ** j)))
    pa.append("v.lsid=%s;" % vn(lambda j: 'math.mod(math.floor(v.pk_laser_s/%d),128)' % (128 ** j)))
    # 有效打包值 0..100（= round((坐标+OFFSET)*8)，V 的 OFFSET=6.3 含选中抬升余量，
    # 见 UnoTableEntity.P_LASER_U 的 javadoc）；101..126 也当无效处理（防脏数据）
    pa.append("v.lu=v.luq/8-3.3;")
    pa.append("v.lv=v.lvq/8-6.3;")
    # 类别与槽号：1..108 = 卡（区内序号来自 laser_s），120..123 = 按钮槽
    pa.append("v.lcat=(v.hv>=%d)?1:((v.hv>=%d)?2:0);" % (HOVER_BTN_BASE, HOVER_CARD_BASE))
    pa.append("v.lidx=(v.lcat==1)?(v.hv-%d):(v.lsid);" % HOVER_BTN_BASE)
    # 显示条件：坐标有效 + （卡：序号有效；按钮：直接有效）+ 观众不显示
    pa.append("v.lvis=(v.luq<120&&v.lvq<120&&v.viewer_mode>=0&&"
              "((v.lcat==2)?(v.lsid<120):1))?1:0;")
    # 选中抬升：服务端已把 RAISE 折进 v（客户端拿不到绝对槽号，算不出 sv 对应关系），恒 0
    pa.append("v.lsel=0;")
    pa.append("v.lh=%s;" % vn(lambda j: 'v.h%dc' % j))
    pa.append("v.button_0=math.mod(v.pk_controls,16);")
    pa.append("v.button_1=math.mod(math.floor(v.pk_controls/16),16);")
    pa.append("v.button_2=math.mod(math.floor(v.pk_controls/256),16);")
    pa.append("v.button_3=math.mod(math.floor(v.pk_controls/4096),16);")
    pa.append("v.button_count=(v.button_0!=0?1:0)+(v.button_1!=0?1:0)+"
              "(v.button_2!=0?1:0)+(v.button_3!=0?1:0);")
    pa.append("v.button_offset_0=(0-(v.button_count-1)/2)*%s;" % BUTTON_GAP)
    pa.append("v.button_offset_1=((v.button_0!=0?1:0)-(v.button_count-1)/2)*%s;" % BUTTON_GAP)
    pa.append("v.button_offset_2=((v.button_0!=0?1:0)+(v.button_1!=0?1:0)"
              "-(v.button_count-1)/2)*%s;" % BUTTON_GAP)
    pa.append("v.button_offset_3=((v.button_0!=0?1:0)+(v.button_1!=0?1:0)+(v.button_2!=0?1:0)"
              "-(v.button_count-1)/2)*%s;" % BUTTON_GAP)
    return pa


def build_entity():
    pa = build_pre_animation()
    doc = {'format_version': '1.10.0', 'minecraft:client_entity': {'description': {
        'identifier': 'tabletopgame:uno_table',
        'materials': {'default': 'entity_alphatest'},
        'textures': {'default': 'textures/tabletopgame/uno/uno_atlas'},
        'geometry': {'default': 'geometry.tabletopgame.uno_table'},
        'animations': {
            'layout': 'animation.tabletopgame.uno.layout',
            'viewer_p0': 'animation.tabletopgame.uno.viewer_p0',
            'viewer_p1': 'animation.tabletopgame.uno.viewer_p1',
            'viewer_p2': 'animation.tabletopgame.uno.viewer_p2',
            'viewer_p3': 'animation.tabletopgame.uno.viewer_p3',
            'hidden': 'animation.tabletopgame.uno.hidden',
        },
        'render_controllers': ['controller.render.tabletopgame.uno_table'],
        'scripts': {
            'should_update_bones_and_effects_offscreen': False,
            # v.fprev=-1：首帧不做"飞行触发"（否则进场时弃牌区那张会凭空飞一次）；
            # v.ft=1：进度置满 = 不飞；两个变量都由 pre_animation 持续维护。
            'initialize': ['v.viewer_mode=-1;', 'v.fprev=-1;', 'v.ft=1;', 'v.fgo=0;'],
            'pre_animation': pa,
            'animate': ['layout'],
        },
    }}}
    os.makedirs(os.path.dirname(ENT_OUT), exist_ok=True)
    with open(ENT_OUT, 'w', encoding='utf-8') as fh:
        json.dump(doc, fh, ensure_ascii=False, separators=(',', ':'))
    print('entity: %d pre_animation lines -> %s' % (len(pa), ENT_OUT))

    # 点击捕获框实体：不画任何东西（几何体只有一根空骨骼），只承载一块看不见的碰撞箱。
    box = {'format_version': '1.10.0', 'minecraft:client_entity': {'description': {
        'identifier': 'tabletopgame:uno_clickbox',
        'materials': {'default': 'entity_alphatest'},
        'textures': {'default': 'textures/tabletopgame/uno/uno_atlas'},
        'geometry': {'default': 'geometry.tabletopgame.uno_clickbox'},
        'render_controllers': ['controller.render.tabletopgame.uno_clickbox'],
    }}}
    os.makedirs(os.path.dirname(M.CLICKBOX_ENT_OUT), exist_ok=True)
    with open(M.CLICKBOX_ENT_OUT, 'w', encoding='utf-8') as fh:
        json.dump(box, fh, ensure_ascii=False, separators=(',', ':'))
    print('entity: clickbox -> %s' % os.path.basename(M.CLICKBOX_ENT_OUT))

    rc = {'format_version': '1.8.0', 'render_controllers': {
        'controller.render.tabletopgame.uno_table': {
            'geometry': 'Geometry.default',
            'materials': [{'*': 'Material.default'}],
            'textures': ['Texture.default'],
            'ignore_lighting': True,
        },
        'controller.render.tabletopgame.uno_clickbox': {
            'geometry': 'Geometry.default',
            'materials': [{'*': 'Material.default'}],
            'textures': ['Texture.default'],
            'ignore_lighting': True,
        }}}
    os.makedirs(os.path.dirname(RC_OUT), exist_ok=True)
    with open(RC_OUT, 'w', encoding='utf-8') as fh:
        json.dump(rc, fh, ensure_ascii=False, separators=(',', ':'))
    print('render controller -> ' + os.path.basename(RC_OUT))


def face_check():
    """核对 108 张牌 id 的图集格覆盖（每色 25 张 + 8 张野牌）。"""
    from collections import Counter
    cnt = Counter(M.face_of(i) for i in range(CARD_SLOTS))
    expect = Counter()
    for c in range(4):
        expect[c * 13] += 1
        for i in range(1, 13):
            expect[c * 13 + i] += 2
    expect[A.FACE_WILD] = 4
    expect[A.FACE_WILD4] = 4
    assert cnt == expect, (sorted(cnt.items()), sorted(expect.items()))
    print('face map ok: %d cards / %d tiles' % (CARD_SLOTS, len(cnt)))


def main():
    face_check()
    M.build_geo()
    build_anim()
    build_entity()


if __name__ == '__main__':
    main()
