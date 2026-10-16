# -*- coding: utf-8 -*-
"""射线拾取自测：把 UnoTableRay 的数学与布局动画逐项对拍，并做端到端命中测试。

为什么需要它：射线是「纯数学近似」（每张牌用一个矩形代替真实倾斜卡面），
一旦常量或抬升方向与动画不一致，表现是「看得见却点不到」，服务端不报任何错误。
本脚本做三件事：
  1. Java 常量 ↔ build_model 常量 逐项等值（防止两边各改一处）；
  2. 用动画真实求值出的卡牌中心/朝向，验证射线矩形的中心与 U/V 轴；
  3. 从入座玩家眼睛位置朝每张牌、每个按钮打射线，断言命中的就是目标。

用法：python verify_ray.py
"""
import io
import json
import math
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import render_base as R
import render_uno as U
import build_model as M
import build_table as T

T_FLY_LIFT = T.FLY_LIFT
T_FLY_PILE_Y = T.FLY_PILE_Y

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.normpath(os.path.join(HERE, '..', '..'))
RAY_JAVA = os.path.join(REPO, 'src/main/java/com/tabletopgame/game/UnoTableRay.java')

problems = []


def ok(cond, msg):
    if not cond:
        problems.append(msg)
    return cond


def near(a, b, tol=1e-6):
    return abs(a - b) <= tol


# ------------------------------------------------------------------ 1. Java 常量对齐
with io.open(RAY_JAVA, encoding='utf-8') as fh:
    JAVA = fh.read()

RAW_D = dict(re.findall(r'public static final double ([A-Z_0-9]+) = ([^;]+);', JAVA))
RAW_I = dict(re.findall(r'public static final int ([A-Z_0-9]+) = ([^;]+);', JAVA))

# 先放动画侧的权威值，再迭代解析 Java 的派生常量（HAND_Y / RAISE_COS / RAISE_SIN ...）
ENV = {
    'OG': M.OG,
    'SG': M.SG,
    'HAND_LIFT': M.HAND_LIFT,
    'RAISE': M.RAISE,
}
for _ in range(6):
    for src in (RAW_D, RAW_I):
        for k, expr in src.items():
            e = expr.strip().rstrip('f')
            for name in sorted(ENV, key=len, reverse=True):
                e = re.sub(r'\b%s\b' % name, repr(ENV[name]), e)
            try:
                ENV[k] = eval(e, {'__builtins__': {}}, {})
            except Exception:                    # noqa: BLE001
                pass

EXPECT = {
    'MAX_DIST': 8.0,
    'SCALE': 16.0,
    'OG': M.OG,
    'SG': M.SG,
    'HAND_LIFT': M.HAND_LIFT,
    'HAND_Y': M.HAND_Y,
    'HAND_RADIUS': float(M.HAND_RADIUS),
    'RAISE': M.RAISE,
    'RAISE_COS': M.RAISE_COS,
    'RAISE_SIN': M.RAISE_SIN,
    'ROW_SIZE': int(M.ROW_SIZE),
    'CARD_H': float(M.CARD_H),
    'ROW_OUT': float(M.ROW_OUT),
    'ROW_UP': float(M.ROW_UP),
    # BUTTON_HALF_U/V 有意比按钮实际尺寸（BUTTON_W=3.1 / BUTTON_D=1.05）略大，
    # 是"好点一些"的手感padding，不参与等值对拍（UnoTableRay 注释里已说明）。
    'SPACING_MAX': 2.8,
    'SPACING_SPAN': 35.2,
    'CARD_HALF_U': M.CARD_SIZE[0] / 2.0,
    'CARD_HALF_V': M.CARD_SIZE[2] / 2.0,
    'CARD_HALF_T': M.CARD_SIZE[1] / 2.0,
    'BUTTON_RADIUS': M.BUTTON_RADIUS,
    'BUTTON_Y': M.BUTTON_Y,
    'BUTTON_GAP': M.BUTTON_GAP,
    # 手牌拾取余量（与动画无关，是「好点一些」的手感 padding，不参与几何对拍，
    # 但下面的命中测试必须用它，否则测试与 UnoTableRay 的实际判定不一致）
    'CARD_PICK_PAD_U': 0.5,
    'CARD_PICK_PAD_V': 0.35,
}
for k, want in EXPECT.items():
    got = ENV.get(k)
    ok(got is not None and near(float(got), float(want), 1e-9),
       'Java 常量 %s=%s，动画侧期望 %s' % (k, got, want))

JAVA_OUT_X = re.search(r'OUT_X\s*=\s*\{([^}]*)\}', JAVA)
JAVA_OUT_Z = re.search(r'OUT_Z\s*=\s*\{([^}]*)\}', JAVA)
if JAVA_OUT_X and JAVA_OUT_Z:
    ox = [int(x) for x in JAVA_OUT_X.group(1).split(',') if x.strip()]
    oz = [int(x) for x in JAVA_OUT_Z.group(1).split(',') if x.strip()]
    ok(ox == M.OUT_X, 'Java OUT_X=%s，模型 OUT_X=%s' % (ox, M.OUT_X))
    ok(oz == M.OUT_Z, 'Java OUT_Z=%s，模型 OUT_Z=%s' % (oz, M.OUT_Z))

# ------------------------------------------------------------------ 2/3. 几何与命中
ANIM = json.load(io.open(os.path.join(R.RP, 'animations/uno/uno_table.animation.json'),
                         encoding='utf-8'))
LAYOUT = ANIM['animations']['animation.tabletopgame.uno.layout']['bones']
CUBE_CENTER = (0.0, 0.06, 0.0)            # CARD_ORIGIN + CARD_SIZE/2


def rotv(p, rot):
    """客户端实际使用的旋转：Rz·Ry·Rx，其中 **pitch 取负**。

    为什么 pitch 要取负：本项目用「斗地主自己座位的动画 + 斗地主自己的射线」做过铁证——
    只有把 Rx 的符号反过来，斗地主手牌的长轴才与它 {@code TableRay.cardUp}
    （= {@code -OUT*SG + y*OG}）精确重合，且牌面法线恰好指向该座位的玩家
    （生产环境里玩家确实能看到自己的牌面）。三点同时成立才唯一确定该符号。
    因此 {@code render_base.rot_pt} / {@code rot_mat} 里的 {@code Rx(+pitch)}
    是与真实客户端相反的一份独立实现，**不能**拿来对拍几何。
    """
    rx, ry, rz = [-math.radians(rot[0]), math.radians(rot[1]), math.radians(rot[2])]
    x, y, z = p
    y, z = y * math.cos(rx) - z * math.sin(rx), y * math.sin(rx) + z * math.cos(rx)
    x, z = x * math.cos(ry) + z * math.sin(ry), -x * math.sin(ry) + z * math.cos(ry)
    x, y = x * math.cos(rz) - y * math.sin(rz), x * math.sin(rz) + y * math.cos(rz)
    return (x, y, z)


def eval3(spec, V):
    raw = spec if isinstance(spec, list) else [spec, spec, spec]
    return [R.ev(x, V) if isinstance(x, str) else float(x) for x in raw]


def card_plane(n, V):
    """动画真实求值出的卡牌平面：(中心, U 轴单位向量, V 轴单位向量)。"""
    b = LAYOUT['card_%d' % n]
    pos = eval3(b['position'], V)
    rot = eval3(b['rotation'], V)
    c = rotv(CUBE_CENTER, rot)
    c = [c[0] + pos[0], c[1] + pos[1], c[2] + pos[2]]
    u = rotv((1, 0, 0), rot)
    v = rotv((0, 0, 1), rot)
    return c, u, v


def cross(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def norm(a):
    m = math.sqrt(dot(a, a)) or 1.0
    return (a[0] / m, a[1] / m, a[2] / m)


def rect_hit(o, d, c, u, half_u, v, half_v, max_dist):
    """UnoTableRay.rectHit 的 Python 镜像。"""
    n = cross(u, v)
    denom = dot(d, n)
    if abs(denom) < 1e-8:
        return -1
    t = dot((c[0] - o[0], c[1] - o[1], c[2] - o[2]), n) / denom
    if t <= 0 or t > max_dist:
        return -1
    p = (o[0] + d[0] * t - c[0], o[1] + d[1] * t - c[1], o[2] + d[2] * t - c[2])
    return t if abs(dot(p, u)) <= half_u and abs(dot(p, v)) <= half_v else -1


EYE_OUT = 41.6           # 玩家站在离桌心 2.6 格处（局部单位 = 格 × 16）
EYE_Y = 10.92            # 眼高 1.62 格，减桌面 0.9375 格 → 0.6825 格 = 10.92 局部单位


def seat_eye(seat):
    return (M.OUT_X[seat] * EYE_OUT, EYE_Y, M.OUT_Z[seat] * EYE_OUT)


SCALE = 16.0


def ray_to(eye, target):
    """Java 里方向向量是 `dir * SCALE`，因此 t 的单位是**方块**，与 MAX_DIST=8 同一量纲。

    这里若返回单位向量，t 会变成「局部单位」（= 16 倍方块数），会被 `t > 8` 全部误拒，
    表现为「明明对准了却一张都命中不了」。
    """
    d = norm((target[0] - eye[0], target[1] - eye[1], target[2] - eye[2]))
    return (d[0] * SCALE, d[1] * SCALE, d[2] * SCALE)


HALF_T = M.CARD_SIZE[1] / 2.0            # 卡厚 0.12 的一半：枢轴在底面 → 可见卡心要补


def hand_center(idx, count, seat, sel=-1, slot=None):
    """射线侧的手牌位置公式（与 UnoTableRay 手牌分支一致）。

    注意末项 `+ 法线*HALF_T`：布局动画给的是骨骼枢轴，而立方体 origin.y = 0..0.12，
    枢轴在牌的**底面**，所以可见卡面中心还要沿牌面法线偏半厚。
    """
    row = idx // M.ROW_SIZE
    row_count = min(M.ROW_SIZE, count - row * M.ROW_SIZE)
    in_row = idx - row * M.ROW_SIZE
    sp = 0 if row_count <= 1 else min(2.8, 35.2 / (row_count - 1))
    o = (in_row - (row_count - 1) / 2.0) * sp
    lifted = (slot is not None and slot == sel)
    # 换行位移沿卡牌「上方向」（朝桌心 + 向上），与选中抬升同一个方向。
    out = M.HAND_RADIUS - row * M.ROW_OUT - (M.RAISE_COS if lifted else 0)
    # 牌面法线：水平朝外 + 抬高 25°（= 90°-65°）
    fx, fy, fz = M.OUT_X[seat] * M.OG, M.SG, M.OUT_Z[seat] * M.OG
    return (M.OUT_X[seat] * out + M.AX_X[seat] * o + fx * HALF_T,
            M.HAND_Y + row * M.ROW_UP + 0.01 * in_row
            + (M.RAISE_SIN if lifted else 0) + fy * HALF_T,
            M.OUT_Z[seat] * out + M.AX_Z[seat] * o + fz * HALF_T)


checked_cards = 0
checked_hits = 0

for seat in range(4):
    # 用例覆盖：单行不满 / 正好一行 / 两行(末行只有 4 张) / 三行(末行 1 张) /
    # 三行(末行 5 张) / 正好三行。注意总槽位只有 CARD_SLOTS=108，所以单座张数别取满。
    for count, sel_idx in ((7, -1), (20, -1), (24, 2), (41, 25), (45, 40), (60, 55)):
        hands = [7, 7, 7, 7]
        hands[seat] = count
        zones = {}
        slot = 0
        for s in range(4):
            for _ in range(hands[s]):
                zones[slot] = s + 1
                slot += 1
        own = [n for n in range(M.CARD_SLOTS) if zones.get(n, 0) == seat + 1]
        ok(len(own) == count, '座位 %d 手牌张数应为 %d，实际 %d' % (seat, count, len(own)))
        sel_slot = own[sel_idx] if sel_idx >= 0 else -1
        V = U.build_vars(viewer=seat, hands=hands, discard=0, pile=5, controls=0,
                         dealer=1, actor=seat, btn_owner=seat + 1, acolor=0,
                         direction=0, sel=(sel_slot if sel_slot >= 0 else None), hover=0)
        tx, tz = M.OUT_X[seat], M.OUT_Z[seat]
        ax, az = M.AX_X[seat], M.AX_Z[seat]
        up = norm((-tx * M.SG, M.OG, -tz * M.SG))
        eye = seat_eye(seat)

        for idx, slot_id in enumerate(own):
            c_true, u_true, v_true = card_plane(slot_id, V)
            c_ray = hand_center(idx, count, seat, sel_slot, slot_id)
            checked_cards += 1
            dist = math.sqrt(sum((c_true[k] - c_ray[k]) ** 2 for k in range(3)))
            ok(dist < 1e-4,
               '座位%d 第%d张(槽%d) 射线中心与动画中心偏差 %.5f：ray=%s anim=%s'
               % (seat, idx, slot_id, dist, ['%.3f' % x for x in c_ray],
                  ['%.3f' % x for x in c_true]))
            ok(abs(dot(u_true, (ax, 0, az))) > 0.999,
               '座位%d 槽%d 动画 U 轴与手牌横轴不平行：%s' % (seat, slot_id, u_true))
            ok(abs(dot(v_true, up)) > 0.999,
               '座位%d 槽%d 动画 V 轴与 -OUT*SG+y*OG 不平行：%s' % (seat, slot_id, v_true))

            # 端到端命中：必须点「看到的那条边」而不是牌心。
            #
            # 手牌是重叠扇形（间距 ≤2.8 < 牌宽 5），同排内槽位更大的牌按骨骼顺序画在上面，
            # 射线又落在**同一个平面**上（同排共面），所以平局时取槽位更大者——
            # 即"点到的是叠在最上面的那张"。这跟斗地主 TableRay.better() 的规则一致，
            # 也符合直觉：牌被压在下面时，只有露出来的那条边是它的可点区域。
            # 因此测试点取每张牌**左侧露出的边**，并自检该点确实没被更大槽位的牌盖住。
            pts_hit = False
            for aim in [-(M.CARD_SIZE[0] / 2.0) + 0.2 + 0.3 * s for s in range(8)]:
                if abs(aim) > M.CARD_SIZE[0] / 2.0:
                    break
                px = c_ray[0] + ax * aim
                py = c_ray[1]
                pz = c_ray[2] + az * aim
                covered = False
                for j, sid in enumerate(own):
                    if sid <= slot_id:
                        continue
                    cc = hand_center(j, count, seat, sel_slot, sid)
                    du = (px - cc[0]) * ax + (pz - cc[2]) * az
                    dv = ((px - cc[0]) * up[0] + (py - cc[1]) * up[1]
                          + (pz - cc[2]) * up[2])
                    if (abs(du) <= M.CARD_SIZE[0] / 2.0
                            and abs(dv) <= M.CARD_SIZE[2] / 2.0):
                        covered = True
                        break
                if covered:
                    continue
                d = ray_to(eye, (px, py, pz))
                best, best_t = -1, 0.0
                for j, sid in enumerate(own):
                    cc = hand_center(j, count, seat, sel_slot, sid)
                    t = rect_hit(eye, d, cc, (ax, 0, az),
                                 M.CARD_SIZE[0] / 2.0 + ENV['CARD_PICK_PAD_U'],
                                 up, M.CARD_SIZE[2] / 2.0 + ENV['CARD_PICK_PAD_V'], 8.0)
                    if t > 0 and (best_t <= 0 or t < best_t - 1e-6 or
                                  (abs(t - best_t) <= 1e-6 and sid > best)):
                        best, best_t = sid, t
                checked_hits += 1
                pts_hit = True
                ok(best == slot_id,
                   '座位%d 点槽%d 露出的边(偏移%.2f) 却%s'
                   % (seat, slot_id, aim,
                      '未命中任何牌' if best < 0 else '命中槽%d' % best))
                break
            if not pts_hit:
                ok(False, '座位%d 槽%d 整张牌被上层牌完全遮住，点不到' % (seat, slot_id))

# ---- 按钮命中 ----
btn_hits = 0
for seat in range(4):
    for codes in (U.PLAY_BTN, U.DRAW_BTN, U.SETTLE_BTN, U.COLOR_BTN):
        active = [(k, (codes >> (4 * k)) & 15) for k in range(4)]
        active = [(k, c) for k, c in active if c]
        n = len(active)
        tx, tz = M.OUT_X[seat], M.OUT_Z[seat]
        ax, az = M.AX_X[seat], M.AX_Z[seat]
        up = (0.0, 1.0, 0.0)
        centers = []
        for i, (k, _) in enumerate(active):
            o = (i - (n - 1) / 2.0) * M.BUTTON_GAP
            centers.append((tx * M.BUTTON_RADIUS + ax * o, M.BUTTON_Y,
                            tz * M.BUTTON_RADIUS + az * o))
        eye = seat_eye(seat)
        for i, (k, _) in enumerate(active):
            d = ray_to(eye, centers[i])
            best, best_t = -1, 0.0
            for j in range(n):
                t = rect_hit(eye, d, centers[j], (ax, 0, az), 3.25, up, 1.6, 8.0)
                if t > 0 and (best_t <= 0 or t < best_t - 1e-6 or
                              (abs(t - best_t) <= 1e-6 and j > best)):
                    best, best_t = j, t
            btn_hits += 1
            ok(best == i, '座位%d 看向按钮槽%d 却命中槽%d' % (seat, k, best))

# ------------------------------------------------------------------ 4. 桌面标记 / 托管机器人布局
# 这一段跑的是资源包里**真实的 pre_animation**（属性名换成 build_vars 备好的 pk_* 镜像值），
# 因此校验的是「客户端实际会执行的语句」，任何一侧写歪都会在这里对不上。
ENT = json.load(io.open(os.path.join(R.RP, 'entity/uno/uno_table.entity.json'),
                        encoding='utf-8'))
PA_LINES = ENT['minecraft:client_entity']['description']['scripts']['pre_animation']
_PROP = re.compile(r"q\.property\('([^']+)'\)")
_SEAT_CODE = {}


def prop_var(prop):
    """q.property 名 → build_vars 里的镜像变量名。"""
    t = prop[len('tabletopgame:'):]
    t = t[len('uno_'):]
    m = re.fullmatch(r'cards_(\d+)', t)
    return 'pk_c' + m.group(1) if m else 'pk_' + t


def run_pre_animation(V, pin=None):
    out = R.Vars(V)
    for line in PA_LINES:
        text = _PROP.sub(lambda m: 'v.' + prop_var(m.group(1)), line)
        for stmt in text.split(';'):
            stmt = stmt.strip()
            m = re.fullmatch(r'v\.([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.+)', stmt)
            if m:
                if pin and m.group(1) in pin:
                    # 把「客户端自走时钟」钉在指定值上：飞行进度 v.ft 由 q.delta_time
                    # 累加，离线求值器里 q.* 是常量，没法精确控制进度，只能这样注入。
                    out[m.group(1)] = pin[m.group(1)]
                else:
                    out[m.group(1)] = R.ev(m.group(2), out)
    return out


mark_checks = 0
TABLE_HALF = 24.0        # 3x3 桌面半宽（局部单位）
BADGE_HALF, ARROW_HALF = 3.4 / 2.0, 4.0 / 2.0
for seat in range(4):
    hands = [7, 7, 7, 7]
    hands[seat] = 24                       # 两行：机器人必须贴**第一行最左**那张，不是最后一张
    others = 0
    for s in range(4):
        if s != seat:
            others |= 1 << (2 * s)         # 顺带验证「别的座位托管不画错座位的机器人」
    V = run_pre_animation(U.build_vars(
        viewer=seat, hands=hands, discard=0, pile=5, controls=0, hover=0,
        dealer=seat + 1, actor=seat + 1, btn_owner=seat + 1, acolor=0, direction=0,
        seats=(1 << (2 * seat)) | others))
    tx, tz = M.OUT_X[seat], M.OUT_Z[seat]
    ax, az = M.AX_X[seat], M.AX_Z[seat]

    # 4.1 庄家徽记：与回合箭头同半径，沿 AX 偏 DEALER_SIDE，两者不重叠
    dpos = eval3(LAYOUT['dealer_%d' % seat]['position'], V)
    want = [tx * M.MARK_RADIUS + ax * M.DEALER_SIDE, 0.45,
            tz * M.MARK_RADIUS + az * M.DEALER_SIDE]
    mark_checks += 1
    ok(max(abs(dpos[k] - want[k]) for k in range(3)) < 1e-6,
       '座位%d 庄家徽记位置 %s ≠ 期望 %s' % (seat, dpos, want))
    arrow = (tx * M.MARK_RADIUS, 0.0, tz * M.MARK_RADIUS)
    off_ax = (dpos[0] - arrow[0]) * ax + (dpos[2] - arrow[2]) * az
    off_out = (dpos[0] - arrow[0]) * tx + (dpos[2] - arrow[2]) * tz
    ok(abs(off_ax - M.DEALER_SIDE) < 1e-6 and abs(off_out) < 1e-6,
       '座位%d 徽记与回合箭头不同半径：AX 偏 %.2f / OUT 偏 %.2f' % (seat, off_ax, off_out))
    ok(M.DEALER_SIDE >= BADGE_HALF + ARROW_HALF + 1.0,
       '座位%d 徽记与箭头间距 %.2f 不足（会穿模）' % (seat, M.DEALER_SIDE))

    # 4.2 托管机器人：**固定在「第一行满 20 张」时最左牌的左手边**（用户 2026-10-15：
    #     「那个托管机器人模型改为放20牌情况的最左边，固定不动」）—— 不随手牌张数变化。
    bpos = eval3(LAYOUT['bot_%d' % seat]['position'], V)
    off = M.BOT_OFF20
    want = [M.BOT_X[seat] + ax * off, M.BOT_Y, M.BOT_Z[seat] + az * off]
    mark_checks += 1
    ok(max(abs(bpos[k] - want[k]) for k in range(3)) < 1e-6,
       '座位%d 机器人位置 %s ≠ 期望（20 张满行最左的左手边）%s' % (seat, bpos, want))
    zones = {}
    slot = 0
    for s in range(4):
        for _ in range(hands[s]):
            zones[slot] = s + 1
            slot += 1
    own = [n for n in range(M.CARD_SLOTS) if zones.get(n, 0) == seat + 1]
    # 本用例第一行是满的（24 张 = 20 + 4）：机器人应恰好贴住第一行最左牌，间隙 = BOT_GAP；
    # 张数更少时最左牌只会更靠里 ⇒ 任何张数都不穿模。
    c_true, _, _ = card_plane(own[0], V)
    du = (bpos[0] - c_true[0]) * ax + (bpos[2] - c_true[2]) * az
    gap = abs(du) - (M.CARD_SIZE[0] / 2.0 + M.BOT_W / 2.0)
    ok(du < 0 and gap >= M.BOT_GAP - 1e-6,
       '座位%d 满行时机器人未贴住最左牌：AX 偏 %+.2f 间隙 %.3f' % (seat, du, gap))
    ok(M.BOT_R + M.BOT_D / 2.0 <= TABLE_HALF + 1e-9,
       '座位%d 机器人探出台沿：%.2f > %.2f' % (seat, M.BOT_R + M.BOT_D / 2.0, TABLE_HALF))
    # 手牌砍到 3 张：位置必须**原地不动**（固定站位的核心诉求）
    V3 = run_pre_animation(U.build_vars(
        viewer=seat, hands=[3, 3, 3, 3], discard=0, pile=5, controls=0, hover=0,
        dealer=seat + 1, actor=seat + 1, btn_owner=seat + 1, acolor=0, direction=0,
        seats=(1 << (2 * seat)) | others))
    bpos3 = eval3(LAYOUT['bot_%d' % seat]['position'], V3)
    mark_checks += 1
    ok(max(abs(bpos3[k] - bpos[k]) for k in range(3)) < 1e-6,
       '座位%d 机器人位置随手牌张数变化：24 张 %s vs 3 张 %s' % (seat, bpos, bpos3))
    ok(eval3(LAYOUT['bot_%d' % seat]['scale'], V)[0] > 0.5,
       '座位%d 托管中但机器人被隐藏' % seat)
    V_off = run_pre_animation(U.build_vars(
        viewer=seat, hands=hands, discard=0, pile=5, controls=0, hover=0,
        dealer=seat + 1, actor=seat + 1, btn_owner=seat + 1, acolor=0, direction=0,
        seats=(others & ~(3 << (2 * seat)))))
    ok(eval3(LAYOUT['bot_%d' % seat]['scale'], V_off)[0] < 0.5,
       '座位%d 没开托管却画了机器人' % seat)

# 机器人骨骼必须成对存在（身体 + 头，头挂在身体下）
BONES = {b['name']: b for b in R.GEO['bones']}
for seat in range(4):
    ok('bot_%d' % seat in BONES and BONES['bot_%d' % seat].get('cubes'),
       '几何体缺少 bot_%d 骨骼' % seat)
    ok(BONES.get('bot_head_%d' % seat, {}).get('parent') == 'bot_%d' % seat,
       'bot_head_%d 必须挂在 bot_%d 下（否则头不跟身体走）' % (seat, seat))

# ------------------------------------------------------------------ 5. 定庄展示：谁的牌摆谁的出牌区
# 展示态下服务端把四张比大小牌挂在**各自座位的手牌区**（区值 1..4），客户端应把它们平铺到
# 「该座位自己的出牌区」OUT[seat]*PLAY_R，且对任何 viewer 都可见。
show_checks = 0
for seat in range(4):
    V = run_pre_animation(U.build_vars(
        viewer=seat, hands=[1, 1, 1, 1], discard=None, pile=5, controls=0, hover=0,
        dealer=0, actor=0, btn_owner=0, acolor=0, direction=0, dseat=0, show=1, deal_n=255))
    slot = seat          # 该座位抽到的那张牌 = 它手牌区里唯一一张（卡槽按座位升序排）
    pos = eval3(LAYOUT['card_%d' % slot]['position'], V)
    want = [M.OUT_X[seat] * M.PLAY_R, M.DISC_Y, M.OUT_Z[seat] * M.PLAY_R]
    show_checks += 1
    ok(max(abs(pos[k] - want[k]) for k in range(3)) < 1e-6,
       '定庄展示：座位%d 的牌位置 %s ≠ 该座出牌区 %s' % (seat, pos, want))
    rot = eval3(LAYOUT['card_%d' % slot]['rotation'], V)
    ok(abs(rot[0]) < 1e-6, '定庄展示：牌应平放（rx=0），实际 %s' % rot)
    sc = eval3(LAYOUT['card_%d' % slot]['scale'], V)
    ok(sc[0] > 0.5, '定庄展示：牌应对所有 viewer 可见（scale=%s）' % sc)
    # 展示态下这张牌不能还占着手牌位（否则和发牌后的手牌重叠）
    hand_pos = eval3(LAYOUT['card_%d' % slot]['position'], U.build_vars(
        viewer=seat, hands=[1, 1, 1, 1], discard=None, pile=5, controls=0, hover=0,
        dealer=0, actor=0, btn_owner=0, acolor=0, direction=0, dseat=0, show=0, deal_n=255))
    ok(max(abs(hand_pos[k] - pos[k]) for k in range(3)) > 1.0,
       '定庄展示态与手牌态的位置没变（v.show_all 分支没生效）')

# ------------------------------------------------------------------ 6. 出牌飞行
# 服务端只把 uno_fly 的值"变一下"，飞行位姿由资源包**真实的 pre_animation** 算出来
# （v.fx/fy/fz/frx/fgo），layout 的 card_N 在「本卡在弃牌区且 v.fgo==1」时直接吃这组变量。
# 三条硬约束必须成立，否则真机上就是"飞歪了"或"落地闪一下"：
#   1. 起点 = 出牌座位的手牌中心（mode 0）/ 中央牌堆顶（mode 1）；
#   2. 弧线：飞到一半时比两端都高；
#   3. 终点 ≈ 静止位姿（t→1 时逐项收敛到 layout 的区 5 分支）—— 落地不跳变。
flight_checks = 0
FLIGHT_HANDS = [7, 7, 7, 7]
DISCARD_SLOT = sum(FLIGHT_HANDS)          # build_vars：弃牌摆在各家手牌之后的第一格
for seat in range(4):
    for mode in (0, 1):
        kw = dict(viewer=seat, hands=list(FLIGHT_HANDS), discard=14, pile=5, controls=0, hover=0,
                  dealer=seat + 1, actor=seat + 1, btn_owner=seat + 1, acolor=0, direction=0,
                  dseat=seat + 1)

        def flight_at(t):
            V = U.build_vars(**kw)
            V['pk_fly'] = mode
            V = run_pre_animation(V, pin={'ft': t, 'fnew': 0, 'fprev': mode})
            return (eval3(LAYOUT['card_%d' % DISCARD_SLOT]['position'], V),
                    eval3(LAYOUT['card_%d' % DISCARD_SLOT]['rotation'], V), V)

        p0, r0, _ = flight_at(0.0)
        p_mid, _, V_mid = flight_at(0.5)
        p_end, r_end, _ = flight_at(0.999)
        V_static = U.build_vars(**kw)
        V_static['pk_fly'] = mode
        V_static = run_pre_animation(V_static, pin={'ft': 1.0, 'fnew': 0, 'fprev': mode})
        p_true = eval3(LAYOUT['card_%d' % DISCARD_SLOT]['position'], V_static)

        if mode == 0:
            want0 = [M.HAND_X[seat], M.HAND_Y + T_FLY_LIFT, M.HAND_Z[seat]]
            label = '手牌中心'
        else:
            want0 = [M.DRAW_X, T_FLY_PILE_Y, M.DRAW_Z]
            label = '中央牌堆顶'
        flight_checks += 1
        ok(max(abs(p0[k] - want0[k]) for k in range(3)) < 1e-4,
           '座位%d mode%d 飞行起点 %s ≠ %s %s' % (seat, mode, p0, label, want0))
        # 弧线：拿资源包**自己的缓动值** v.fe 算出「无弧线时的弦高」，实际高度必须明显更高。
        chord = p0[1] + (p_true[1] - p0[1]) * V_mid['fe']
        ok(p_mid[1] - chord > 2.0,
           '座位%d mode%d 飞行弧线项没生效：t=0.5 实际 y=%.2f，弦高 y=%.2f'
           % (seat, mode, p_mid[1], chord))
        ok(p_mid[1] > p_true[1] + 2.0,
           '座位%d mode%d 飞行半途就已贴地：y=%.2f（终点 %.2f）' % (seat, mode, p_mid[1], p_true[1]))
        ok(max(abs(p_end[k] - p_true[k]) for k in range(3)) < 0.05,
           '座位%d mode%d 飞行终点 %s 与静止位姿 %s 相差过大（落地会跳变）'
           % (seat, mode, p_end, p_true))
        ok(abs(r_end[0]) < 0.5, '座位%d mode%d 落地时未放平：rx=%.2f' % (seat, mode, r_end[0]))
        if mode == 1:
            ok(abs(r0[0] - 180) < 1e-4,
               '座位%d 从牌堆翻起始牌时应从牌背朝上（rx=180）起飞，实际 %.2f' % (seat, r0[0]))

# ------------------------------------------------------------------ 7. 定位器激光点（牌面共面）
# 需求（2026-10-15）：「做成像黑色框那样的，是在平面上的」。激光点是模型薄片 laser_dot，
# 位置 = 手牌/按钮布局表达式 + 命中点牌面局部坐标 (u,v)。三条硬约束：
#   1. 手牌分支：激光点 = 动画真实卡面中心 + u*U + v*V（card_plane 的轴就是动画真源）；
#   2. 共面：激光点到卡面法线的投影 ≈ 0 —— 不共面就是"穿模感"回归；
#   3. 按钮分支：激光点落在按钮斜面上（沿法线抬 LASER_LIFT），且竖直命中坐标按 cos65° 折算。
laser_checks = 0
LASER_HANDS = [9, 7, 7, 7]
for seat in range(4):
    hands = list(LASER_HANDS)
    hands[seat] = 24
    zones = {}
    slot = 0
    for s in range(4):
        for _ in range(hands[s]):
            zones[slot] = s + 1
            slot += 1
    own = [n for n in range(M.CARD_SLOTS) if zones.get(n, 0) == seat + 1]
    # 用例覆盖：第一行最左 / 第二行（选中抬起） / 第一行中间，各带不同的命中偏移
    for idx, u_hit, v_hit, sel_idx in ((0, -2.0, -3.0, -1), (22, 1.5, 2.5, 22), (5, 0.4, 0.8, -1)):
        slot_id = own[idx]
        selected = sel_idx >= 0
        # 服务端折算：命中平面贴「抬起后」牌面，v 要减去（换算到未抬基准要加）RAISE
        v_packed = v_hit + (M.RAISE if selected else 0.0)
        V = U.build_vars(viewer=seat, hands=hands, discard=0, pile=5, controls=0,
                         dealer=1, actor=seat + 1, btn_owner=seat + 1, acolor=0,
                         direction=0, sel=None, laser=(seat, idx, u_hit, v_packed))
        # hover 是「每 viewer 7 位」打包属性：把本座位的值放到自己的位段
        V['pk_hover'] = (slot_id + 1) << (7 * seat)
        if selected:
            V['pk_sel'] = (slot_id + 1) << (7 * seat)     # 选中 = 命中同一张牌（抬起）
        V = run_pre_animation(V, pin={'ft': 1.0, 'fnew': 0, 'fprev': 0})
        lp = eval3(LAYOUT['laser_dot']['position'], V)
        ls = R.ev(LAYOUT['laser_dot']['scale'], V)
        c, uu, vv = card_plane(slot_id, V)
        want = [c[k] + u_hit * uu[k] + v_hit * vv[k] for k in range(3)]
        laser_checks += 1
        ok(ls == 1, '座位%d 槽%d 命中时激光应显示（scale=%s）' % (seat, slot_id, ls))
        ok(max(abs(lp[k] - want[k]) for k in range(3)) < 0.08,
           '座位%d 槽%d 激光位置 %s ≠ 卡面中心+偏移 %s（量化 u=%.1f v=%.1f）'
           % (seat, slot_id, ['%.3f' % x for x in lp],
              ['%.3f' % x for x in want], u_hit, v_hit))
        n = cross(uu, vv)
        off_n = dot((lp[0] - c[0], lp[1] - c[1], lp[2] - c[2]), n)
        # 容差 5e-4：解析表达式（r6 六位舍入常数）与动画旋转矩阵求值之间的浮点残差。
        # 穿模感是 0.01 量级，0.0005 以下肉眼不可分，仍能拦住真正的共面性回归。
        ok(abs(off_n) < 5e-4,
           '座位%d 槽%d 激光点不与卡面共面：法向偏移 %.4f（穿模感来源）' % (seat, slot_id, off_n))

# 隐藏：未命中（hover=0、无 laser）时必须不显示
V = U.build_vars(viewer=0, hands=LASER_HANDS, discard=0, pile=5, controls=0,
                 dealer=1, actor=1, btn_owner=1, acolor=0, direction=0, hover=0)
V = run_pre_animation(V, pin={'ft': 1.0, 'fnew': 0, 'fprev': 0})
laser_checks += 1
ok(R.ev(LAYOUT['laser_dot']['scale'], V) == 0, '未命中时激光应隐藏（scale≠0）')

# 按钮分支：命中按钮 0 的竖直矩形 (u,v)，激光要落在按钮斜面上
V = U.build_vars(viewer=1, hands=LASER_HANDS, discard=0, pile=5, controls=1,
                 dealer=2, actor=2, btn_owner=2, acolor=0, direction=0,
                 laser=(1, 127, 1.0, 0.8))
V['pk_hover'] = T.HOVER_BTN_BASE << (7 * 1)
V = run_pre_animation(V, pin={'ft': 1.0, 'fnew': 0, 'fprev': 0})
lp = eval3(LAYOUT['laser_dot']['position'], V)
ok(R.ev(LAYOUT['laser_dot']['scale'], V) == 1, '命中按钮时激光应显示')
bc = eval3(LAYOUT['button_slot0']['position'], V)
br = eval3(LAYOUT['button_slot0']['rotation'], V)
seat = 1
u_hit, v_hit = 1.0, 0.8
ax, az = M.AX_X[seat], M.AX_Z[seat]
tx, tz = M.OUT_X[seat], M.OUT_Z[seat]
up_b = (-tx * M.SG, M.OG, -tz * M.SG)          # 按钮斜面「上」方向（= 卡牌上方向）
n_b = (tx * M.OG, M.SG, tz * M.OG)             # 按钮斜面法线（朝玩家上方）
want = [bc[0] + u_hit * ax + v_hit * M.OG * up_b[0] + T.LASER_LIFT * n_b[0],
        bc[1] + v_hit * M.OG * up_b[1] + T.LASER_LIFT * n_b[1],
        bc[2] + u_hit * az + v_hit * M.OG * up_b[2] + T.LASER_LIFT * n_b[2]]
laser_checks += 1
ok(max(abs(lp[k] - want[k]) for k in range(3)) < 0.08,
   '按钮激光位置 %s ≠ 斜面投影 %s' % (['%.3f' % x for x in lp], ['%.3f' % x for x in want]))
# 与按钮片实际平面（动画真实旋转）比对：激光点沿斜面法线浮 LASER_LIFT。
# 动画旋转后薄片法线方向（n_anim）与解析法线（n_b，朝玩家）可能反向（薄片双面渲染），
# 所以只约束「沿法线的距离 = LASER_LIFT」，不约束符号。
u_btn = rotv((1, 0, 0), br)
v_btn = rotv((0, 0, 1), br)
n_anim = norm(cross(u_btn, v_btn))
off_n = dot((lp[0] - bc[0], lp[1] - bc[1], lp[2] - bc[2]), n_anim)
ok(abs(abs(off_n) - T.LASER_LIFT) < 0.02,
   '按钮激光未平行贴在按钮斜面上：法向距离 %.4f ≠ %.3f' % (abs(off_n), T.LASER_LIFT))

print('手牌几何对拍 : %d 张' % checked_cards)
print('手牌命中测试 : %d 次' % checked_hits)
print('按钮命中测试 : %d 次' % btn_hits)
print('标记/机器人布局 : %d 组（庄家徽记半径+间距 / 机器人位置+间隙 / 显隐）' % mark_checks)
print('定庄展示布局   : %d 组（谁的牌摆谁的出牌区 / 平放 / 全员可见）' % show_checks)
print('出牌飞行       : %d 组（起点=手牌中心/牌堆顶 · 有弧线 · 终点=静止位姿）' % flight_checks)
print('激光点共面     : %d 组（手牌=卡面+局部偏移 · 按钮=斜面投影 · 隐藏）' % laser_checks)
print('total problems : %d' % len(problems))
for p in problems[:25]:
    print('  FAIL ' + p)
sys.exit(1 if problems else 0)
