# -*- coding: utf-8 -*-
"""生成 UNO 牌桌的几何体、动画与客户端实体定义（一个实体画整桌）。

输出：
  models/entity/uno/uno_table.geo.json
  animations/uno/uno_table.animation.json
  entity/uno/uno_table.entity.json
  render_controllers/uno/uno_table.render_controllers.json

坐标约定（与斗地主牌桌一致）：牌桌实体以 yaw=0 生成于 3x3 中心，局部单位 1/16 方块，
局部 +x = 世界东、局部 +z = 世界**南**（z 是镜像的：世界→局部为 local.z = -(z-ez)，
与 UnoTableRay / render_base.apex 同一约定）。台面顶 = 实体原点（y=0）。手牌距中心 23、按钮 25.5。

座位（顺时针，P1..P4）：0=东 1=南 2=西 3=北。
"""
import json
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import uno_assets as A

HERE = os.path.dirname(os.path.abspath(__file__))
RP = A.RP
GEO_OUT = os.path.join(RP, 'models/entity/uno/uno_table.geo.json')
ANIM_OUT = os.path.join(RP, 'animations/uno/uno_table.animation.json')
ENT_OUT = os.path.join(RP, 'entity/uno/uno_table.entity.json')
RC_OUT = os.path.join(RP, 'render_controllers/uno/uno_table.render_controllers.json')
# 「点击捕获框」实体：只有一根空骨骼、什么都不画（做法与斗地主插件的 table_anchor 一致）。
# 它的唯一作用是给客户端一块看不见的碰撞箱（服务端 configureClickHitbox 设置），
# 让准星在"悬浮手牌"上方也能命中实体 → 客户端才肯把右键交互发给服务端。
CLICKBOX_GEO_OUT = os.path.join(RP, 'models/entity/uno/uno_clickbox.geo.json')
CLICKBOX_ENT_OUT = os.path.join(RP, 'entity/uno/uno_clickbox.entity.json')

# ------------------------------------------------------------------ 布局常量
CARD_SLOTS = 108
CARD_COLORS = 4
COLOR_CARDS = 25                      # 每色 25 张（0 一张、1..9 各两张、跳过/反转/+2 各两张）
WILD_START = COLOR_CARDS * CARD_COLORS        # 100
WILD4_START = WILD_START + 4                  # 104

CARD_ORIGIN = [-2.5, 0, -3.75]
CARD_SIZE = [5, 0.12, 7.5]
CARD_PITCH = 65
# sin65° / cos65°：卡牌「上方向」的 y 与 xz 分量（UnoTableRay 必须用同一对数）
OG = math.sin(math.radians(CARD_PITCH))
SG = math.cos(math.radians(CARD_PITCH))

RAISE = 2.1333333333333333
RAISE_COS = RAISE * math.cos(math.radians(CARD_PITCH))     # 0.9015856250468255
RAISE_SIN = RAISE * math.sin(math.radians(CARD_PITCH))     # 1.933456612344853
# 卡厚（0.12）的一半：骨骼枢轴在牌底面，可见卡面 / 激光点命中面沿法线再抬这么些
# （与 UnoTableRay.CARD_HALF_T 同一个数 —— 射线平面才与可见卡面重合）。
CARD_HALF_T = CARD_SIZE[1] / 2
HAND_LIFT = 1.75
HAND_Y = 7.5 / 2 * math.sin(math.radians(CARD_PITCH)) - 1 + HAND_LIFT   # 4.1486542013874375
HAND_RADIUS = 23

ROW_SIZE = 20                          # 每行最多 20 张，超出则沿斜线换下一行
# 行的堆叠方向 = 卡牌自身的「上方向」= -OUT*cos65° + y*sin65°（与选中抬升 / 射线 V 轴同一个方向）。
# 行距取**一个牌高**，于是下一行的底边恰好贴住上一行的顶边（"起点恰好衔接上一行弹起后的最高点"）；
# 第三行及以后每一行都沿同一条斜线继续往上叠。
CARD_H = CARD_SIZE[2]                                          # 7.5
ROW_OUT = CARD_H * SG                                          # 3.169637 朝桌心（沿 -OUT）
ROW_UP = CARD_H * OG                                           # 6.797308 向上

FAKE_MAX = 30                          # 对手手牌最多摆 30 张

BUTTON_RADIUS = 25.5
BUTTON_Y = -0.25
# 必须为正：按钮沿 AX 轴排开，AX 指向「玩家的右手边」，所以 offset = (序号-居中)*BUTTON_GAP
# 在 GAP>0 时使 slot0 落在 **-AX 侧 = 玩家左手边**，与需求「取消 提示 抽牌 出牌（屏幕从左到右）」
# 一致。写成负值会把整排按钮左右镜像（slot0 跑到最右），射线与动画仍自洽、只是排序反了。
BUTTON_GAP = 6.6
BUTTON_W, BUTTON_D = 3.1, 1.05

# 中央牌堆 / 弃牌堆的摆放（本轮改版）：
#  · 「牌堆」横着放在桌子正中（每个视角都转 90° 成横向，见 pile_* 的 ry）；
#  · 「出牌」不再堆在中间，而是**平铺在打出这张牌的玩家自己的出牌区**里，
#    位置 = OUT[打出座位]*PLAY_R（v.dsx/v.dsz），朝向按 viewer 转（谁看都正立）。
# 台面顶 = 实体原点（方块几何顶面 15/16，实体生成在该高度），root 再抬 0.25 单位，
# 所以这里的 y 只要 ≈0 就已经离台面 0.25/16≈0.016 格，既贴面又不穿模。
PILE_Y = 0.01                            # 牌堆最底一张的底面高度
PILE_STACK = 0.13                        # 每张叠高（卡厚 0.12 + 一丝缝隙）
# 牌堆中心 = 桌子正中（需求「牌堆就横着放中间」）。保留常量是为了让 build_table /
# render_uno / verify_ray 都能引用同一个真源，避免又出现"改一处漏三处"。
DRAW_X, DRAW_Z = 0.0, 0.0
DISC_Y = 0.02                            # 出牌区那张牌的底面高度
# 出牌区半径：牌竖着放（5x7.5），长轴朝外，故占 OUT∈[PLAY_R-3.75, PLAY_R+3.75]
PLAY_R = 13.5
# 当前颜色圆盘半径：每个 viewer 都渲染在自己正前方一点（需求「所有人看到的圆圈都是往自己这边」）
COLOR_R = 7.0
# 出牌方向标记（顺时针 / 逆时针箭头）的半径：**与当前颜色圆盘取同一个半径**，
# 位置取反方向（颜色圆盘在 OUT*COLOR_R = 自己正前方，方向标记在 -OUT*DIR_R = 越过牌堆），
# 两者关于桌心点对称 —— 需求「方向箭头跟颜色标记位置对称」。
# build_table 里 dir_x/dir_z 用的是 -OUT，符号别漏。
DIR_R = COLOR_R

# 座位 0=东 1=南 2=西 3=北
OUT_X = [1, 0, -1, 0]
OUT_Z = [0, -1, 0, 1]
AX_X = [0, 1, 0, -1]
AX_Z = [1, 0, -1, 0]
SEAT_YAW = [-90, 0, 90, 180]
HAND_X = [OUT_X[j] * HAND_RADIUS for j in range(4)]
HAND_Z = [OUT_Z[j] * HAND_RADIUS for j in range(4)]

MARK_RADIUS = 19.0
MARK_Y = 0.55
DISC_MARK_Y = 0.30
# 庄家徽记：**与回合箭头同半径**（OUT*MARK_RADIUS），再沿玩家右手方向 AX 偏 DEALER_SIDE，
# 于是「箭头在正前方、徽记在右前方」排在同一条弧线上、互不重叠（需求：跟黄色箭头平行、
# 之间不穿模、整体靠右一点）。偏量按用户截图红圈反解：徽记中心 ≈ 东 18.9 / 北 6.5 单位，
# 即 OUT*19 + AX*6.5；徽记半宽 1.7 + 箭头半宽 2.0 = 3.7 < 6.5，必然不穿模。
DEALER_SIDE = 6.5

# ------------------------------------------------------------------ 托管机器人
# 「托管」时站在本方手牌旁边的小机器人：**直接沿用斗地主插件那张模型**
# （斗地主/Doudizhu .../models/entity/table.geo.json 的 trusteeship_p* / trusteeship_head_p*，
#  也就是 vanilla agent 模型按 3/16 缩放；贴图由 uno_assets.robot_src_tile() 搬过来）。
#  · 单位：原模型 1 单位 = 1/16 方块；这里统一乘 BOT_SCALE，其余数据逐字节照抄。
#  · 站位：**固定在「第一行满 20 张」时最左牌的左手边**，不随手牌张数变化
#    （用户 2026-10-15：「那个托管机器人模型改为放20牌情况的最左边，固定不动」——
#     原来按当前张数逐帧算，牌越出越少时机器人会跟着往中间飘）。
#  · 朝向：ry = SEAT_YAW[j]，与手牌同一个「面朝牌主」的约定 —— 自己看到的是机器人的正面。
BOT_SCALE = 2.0
BOT_Y = 0.02                              # 脚底高度（贴在台面上，与出牌区的牌同高）
BOT_R = HAND_RADIUS - 1.0                 # 站位半径：比手牌骨骼线（23）往桌心收 1，鼻尖不探出台沿
BOT_GAP = 0.6                             # 机器人侧边 ↔ 最左牌侧边 的空隙
BOT_W = 12 * 0.1875 * BOT_SCALE           # 宽（含双臂）= 4.5
BOT_D = 8 * 0.1875 * BOT_SCALE            # 厚 = 3.0
BOT_H = 16 * 0.1875 * BOT_SCALE           # 高 = 6.0
# 机器人中心相对「手牌横向中心」的 AX 偏移量 = -(最左牌偏移 + 半牌宽 + 空隙 + 半机器人宽)
BOT_SIDE = CARD_SIZE[0] / 2 + BOT_GAP + BOT_W / 2     # 2.5 + 0.6 + 2.25 = 5.35
# 「第一行满 20 张」时的行内间距与机器人偏移（固定站位用；14~20 张时最左牌都恰好
# 在 ±17.6，所以满行时间隙正好 = BOT_GAP，张数更少时只会更靠左 ⇒ 永不穿模）
BOT_SP20 = min(2.8, 35.2 / (ROW_SIZE - 1))            # 35.2/19 ≈ 1.852632
BOT_OFF20 = -(ROW_SIZE - 1) / 2.0 * BOT_SP20 - BOT_SIDE    # -17.6 - 5.35 = -22.95
BOT_X = [OUT_X[j] * BOT_R for j in range(4)]
BOT_Z = [OUT_Z[j] * BOT_R for j in range(4)]

FACE_SIZE = (A.CARD_W, A.CARD_H)
HILITE = A.HILITE


# ------------------------------------------------------------------ 牌面映射
def face_of(card_id):
    """牌 id(0..107) -> 图集格索引(0..55)，与 UnoDeck.face() 完全一致。"""
    if card_id >= WILD4_START:
        return A.FACE_WILD4
    if card_id >= WILD_START:
        return A.FACE_WILD
    c, k = divmod(card_id, COLOR_CARDS)
    if k == 0:
        i = 0
    elif k <= 18:
        i = (k + 1) // 2
    elif k <= 20:
        i = 10           # 跳过
    elif k <= 22:
        i = 11           # 反转
    else:
        i = 12           # +2
    return c * 13 + i


# ------------------------------------------------------------------ UV 工具
def rect(uv, w, h):
    x, y = uv
    return {'uv': [x, y], 'uv_size': [w, h]}


def _side_uv(k):
    """卡片立方体的四个侧面：**纯白 (#ffffff)** 长条（所有牌共用）。

    需求演化（2026-10-15）：纸白 → 各自环色 → 最终定为「在大贴图上画一条纯白长条，
    所有牌侧面都框过去，亮牌侧面就是纯白」。k 参数保留仅为签名兼容，实际不再按牌取环色。
    """
    p = A.card_side_white_uv()
    return {'north': rect(p, 4, 4), 'east': rect(p, 4, 4),
            'south': rect(p, 4, 4), 'west': rect(p, 4, 4)}


def _side_uv_clear():
    """**桌面标记 / 按钮 / 高亮框**专用：四面全透明。

    这些是「贴在台面上的薄片 / 镂空框」，一旦沿用纸白就会渲染成一圈白描边。
    卡片不要用这个 —— 卡片走 {@link _side_uv}（纸白）。
    """
    return {'north': rect(A.SWATCH_CLEAR, 4, 4), 'east': rect(A.SWATCH_CLEAR, 4, 4),
            'south': rect(A.SWATCH_CLEAR, 4, 4), 'west': rect(A.SWATCH_CLEAR, 4, 4)}


def _tile(x, y, w, h):
    """图块贴法：竖边翻在正面朝上时保持正立（与斗地主 table.geo.json 的 down 写法一致）。"""
    return {'uv': [x, y + h], 'uv_size': [w, -h]}


def card_uv(k):
    """卡面牌（k = 图集格索引）：up = 牌面，down = **牌背**（黑底圆环那张，是所有牌的牌背）。

    牌背不是空白灰底 —— 手牌倾斜 65° 时对手会看到牌的背面，牌堆/弃牌平放时
    也要靠它撑住观感，空白底会露出「没有牌背」的破绽。
    """
    x, y = A.face_tile(k)
    bx, by = A.face_tile(A.FACE_BACK)
    d = _side_uv(k)
    d['up'] = {'uv': [x, y], 'uv_size': [A.CARD_W, A.CARD_H]}
    d['down'] = _tile(bx, by, A.CARD_W, A.CARD_H)
    return d


def opponent_uv():
    """对手手牌：**朝牌主那是 `?`（牌面/未知），朝外这面是牌背**。

    朝向判定（这次是拿真机事实倒推出来的，不再靠离线渲染器）：
    - 自己手牌的骨骼 `card_i` 与对手手牌的 `fake_s_i` **同座位同朝向** ——
      `card_0` 的 yaw 是 `z0==1?-90 : z0==2?0 : z0==3?90 : 180`，与
      `fake_0_0(-90) / fake_1_0(0) / fake_2_0(90) / fake_3_0(180)` 一字不差，rx 同为 65。
    - `card_uv()` 里 `up = 牌面`，而真机上「自己手牌显示正常（看得见彩色牌面）」
      ⇒ **`up` = 朝牌主的那面**，`down` = 朝其他观察者那面。
    - `fake_vis_s` 又把「牌主自己看自己」这条路走的是 `card_i`，所以对手手牌的 `up`
      面实际上任何客户端都看不到，贴 `?` 只是语义占位。

    历史教训：上两轮分别在 `up`/`down` 上反复贴反，最后是「`up`=`?`、`down`=牌背」
    这一个组合同时满足「对面看到牌背」和「牌面 = ?」两条要求。
    """
    d = _side_uv(A.FACE_HIDDEN)
    hx, hy = A.face_tile(A.FACE_HIDDEN)
    bx, by = A.face_tile(A.FACE_BACK)
    d['up'] = {'uv': [hx, hy], 'uv_size': [A.CARD_W, A.CARD_H]}
    d['down'] = _tile(bx, by, A.CARD_W, A.CARD_H)
    return d


def pile_uv():
    """中央抽牌堆：朝上的面是**牌背**（黑底圆环圆圈），整叠牌都是盖着的。

    以前这里错用了 `?` 盘面 —— `?` 是「未知的牌面」，属于对手手牌，不属于抽牌堆。
    """
    d = _side_uv(A.FACE_BACK)
    bx, by = A.face_tile(A.FACE_BACK)
    d['up'] = {'uv': [bx, by], 'uv_size': [A.CARD_W, A.CARD_H]}
    d['down'] = _tile(bx, by, A.CARD_W, A.CARD_H)
    return d


def tile_uv(uv, w, h, clear_sides=False):
    """平面贴图：up = 图块，down = 同块镜像。

    侧面默认走 {@link _side_uv}（**纯白长条**，卡片侧面 / 激光点共用）；
    {@code clear_sides=true} 时四面用全透明取样点（**按钮 / 高亮框 / 桌面标记**专用，
    见 {@link _side_uv_clear}）。
    """
    x, y = uv
    d = _side_uv_clear() if clear_sides else _side_uv(0)
    d['up'] = {'uv': [x, y], 'uv_size': [w, h]}
    d['down'] = {'uv': [x, y + h], 'uv_size': [w, -h]}
    return d


def plate(name, parent, sx, sz, uv, tw, th, y=0.0):
    """台面上的标记贴片。侧面必须全透明，否则一圈近白描边会被看成「白色边边」。"""
    return {
        'name': name, 'parent': parent, 'pivot': [0, 0, 0],
        'cubes': [{
            'origin': [round(-sx / 2, 6), round(y, 6), round(-sz / 2, 6)],
            'size': [sx, 0.02, sz],
            'uv': tile_uv(uv, tw, th, clear_sides=True),
        }],
    }


# ------------------------------------------------------------------ 变量名
def cards_prop(i):
    return 'tabletopgame:uno_cards_%d' % i


# ------------------------------------------------------------------ 动画表达式
def vn(j, fn):
    """按 viewer_mode 选择表达式（0..3），越界回落到 0 号座位。"""
    out = fn(0)
    for k in (3, 2, 1):
        out = '(%s==%d?%s:%s)' % ('v.viewer_mode', k, fn(k), out)
    return out


VYAW = vn(0, lambda j: SEAT_YAW[j])

# ------------------------------------------------------------------ 准星 / 选中编码（唯一真源）
# 每个 viewer 占 7 bit（base 128），4 个 viewer 共 28 bit，各塞进 1 个实体属性。
# 取值空间（必须互不重叠，否则按钮和手牌会一起高亮）：
#   0            无
#   1..108       手牌槽 slot+1（与 highlight_N 的 N+1 对齐）
#   120..123     功能/选色按钮 slot 0..3
# 7 bit 上限 127，必须 ≥ 123。
# 注意：不要用 6 bit —— 手牌槽可达 107，6 位（0..63）会让槽位 ≥63 的手牌永远无法高亮。
HOVER_BITS = 7
HOVER_MAX = (1 << HOVER_BITS) - 1               # 127
HOVER_CARD_BASE = 1
HOVER_BTN_BASE = 120


def _viewer_pick(var):
    """按 v.viewer_mode 从打包属性 var 中取出本 viewer 的 7 位值。"""
    b = 1 << HOVER_BITS
    return ('(v.viewer_mode==0?math.mod(v.%s,%d):'
            '(v.viewer_mode==1?math.mod(math.floor(v.%s/%d),%d):'
            '(v.viewer_mode==2?math.mod(math.floor(v.%s/%d),%d):'
            'math.mod(math.floor(v.%s/%d),%d))))'
            % (var, b, var, b, b, var, b ** 2, b, var, b ** 3, b))


HV = _viewer_pick('pk_hover')
SV = _viewer_pick('pk_sel')


def sel_of(n):
    """第 n 个卡槽是否被本 viewer 选中（1/0 表达式）。

    选中信息存在 uno_sel 的每 viewer 7 位里，值是「手牌槽 + 1」。卡槽 n 只有在属于手牌区
    （v.zN ∈ 1..4）时才可能被选中，因此要同时看 v.zN 与 v.sv。

    **必须整体加括号**：Molang 里 `?:` 优先级低于 `+`/`*`，本式会被当算术因子乘进
    `A - 1*sel*0.9016`。若不加括号，`A-1*cond?1:0*0.9016` 会被解析成
    `(A-1*cond) ? 1 : 0`（A 非 0 时恒为 1），整张牌的位置表达式全部塌掉。
    斗地主没踩这个坑是因为它的 `v.selN` 由 pre_animation 预算成变量，天然是原子项。
    """
    return '(((v.z%d>=1&&v.z%d<=4)&&v.sv==%d)?1:0)' % (n, n, HOVER_CARD_BASE + n)


# 行号 / 行内序号 / 该行张数 / 该行间距全部在 Molang 里现算（见 card_axes）。
# 旧版用 v.ra/v.rb/v.ras/v.rbs 只能表达两行，第三行起就没办法了。


def card_axes(n, j):
    """返回 (x, y, z) 表达式：手牌区 j 内第 n 张牌的位置。

    卡牌「上方向」= {@code -OUT*SG + y*OG}（朝桌心 + 向上，与水平面成 65°）。
    **选中抬升与换行位移都必须沿这个方向**，与 {@code UnoTableRay} 的矩形 V 轴严格一致；
    写成 +OUT 会让「点击已选中的牌」永远落空，也会让第二行跑到玩家这一侧去。
    """
    s = 'v.s%d' % n
    sel = sel_of(n)
    # 行号 = floor(s/ROW_SIZE)，行内序号 = s - ROW_SIZE*row。
    # 该行张数必须用**该座位手牌总数** v.h{j}c 减出来（min 到 ROW_SIZE），
    # 不能拿行内序号当张数 —— 末行只有 4 张时算出来的居中量会完全跑偏。
    # 内联算的好处：行数不写死，第三行、第四行……会自动长出来。
    row = 'math.floor(%s/%d)' % (s, ROW_SIZE)
    in_row = '(%s-%d*%s)' % (s, ROW_SIZE, row)
    cnt = 'math.min(%d,v.h%dc-%d*%s)' % (ROW_SIZE, j, ROW_SIZE, row)
    # 分母写成 math.max(1, cnt-1)：末行只有 1 张时 cnt-1=0，三元里也照样会算出 0/0，
    # 客户端 Molang 会静默给 0，但离线求值器会直接抛异常（verify_ray 新增的三行用例就是这样炸出来的）。
    # 顺带也不需要 cnt<=1 的判断了：cnt==1 时 in_row 必为 0，off 自然为 0。
    sp = 'math.min(2.8,35.2/math.max(1,(%s-1)))' % cnt
    off = '((%s-(%s-1)/2)*%s)' % (in_row, cnt, sp)
    # 所有数值常量一律走 r6() + %s：**不要用 %d 去格式化浮点常量**，
    # `'%d' % 1.8` 会静默截断成 `1`，导致动画与 UnoTableRay 差半个牌位
    # （这正是 verify_ray.py 对拍出来的那类"看得见但点不准"）。
    # 行位移 = -OUT*ROW_OUT（朝桌心）+ y*ROW_UP（向上），两者合成 65° 斜线。
    x = '%s+%d*(%s)+%d*%s*%s-%d*%s*%s' % (
        r6(HAND_X[j]), AX_X[j], off, -OUT_X[j], row, r6(ROW_OUT),
        OUT_X[j], sel, r6(RAISE_COS))
    # 逐张抬升用**行内序号**而不是全局序号：写全局会让每行相对上一行多抬 0.01*ROW_SIZE=0.2，
    # 行距就不再等于一个牌高（"恰好衔接"被破坏）。
    y = '%s+%s*%s+0.01*%s+%s*%s' % (r6(HAND_Y), row, r6(ROW_UP), in_row, sel, r6(RAISE_SIN))
    z = '%s+%d*(%s)+%d*%s*%s-%d*%s*%s' % (
        r6(HAND_Z[j]), AX_Z[j], off, -OUT_Z[j], row, r6(ROW_OUT),
        OUT_Z[j], sel, r6(RAISE_COS))
    return x, y, z


def nest(zone_var, mapping, default='0'):
    out = default
    for k in sorted(mapping, reverse=True):
        out = '(%s==%d?%s:%s)' % (zone_var, k, mapping[k], out)
    return out


def r6(v):
    return round(v, 6)


# ------------------------------------------------------------------ 托管机器人几何
# 数据逐条照抄斗地主插件 ddz table.geo.json 的 trusteeship_p*（躯干 + 双臂 + 双腿 6 块）
# 与 trusteeship_head_p*（头 + 鼻 2 块）。原模型单位是 1/16 方块的 3/16，
# 这里乘 BOT_SCALE；UV 用 uno_assets.robot_uv() 平移到本图集的机器人贴图块内
# （那张贴图正是从斗地主图集同一区域搬来的，所以 UV 值原样可用）。
_BOT_BODY = [
    ([-0.75, 0.9375, -0.375], [1.5, 0.75, 0.75],
     {'down': (1460, 12, 8, 4), 'up': (1468, 12, 8, 4), 'east': (1456, 16, 4, 4),
      'north': (1460, 16, 8, 4), 'west': (1468, 16, 4, 4), 'south': (1472, 16, 8, 4)}),
    ([-0.5625, 0.5625, -0.375], [1.125, 0.375, 0.75],
     {'down': (1460, 20, 6, 4), 'up': (1466, 20, 6, 4), 'east': (1456, 24, 4, 2),
      'north': (1460, 24, 6, 2), 'west': (1466, 24, 4, 2), 'south': (1470, 24, 6, 2)}),
    ([0.75, 0.0, -0.1875], [0.375, 1.6875, 0.375],
     {'down': (1482, 11, 2, 2), 'up': (1484, 11, 2, 2), 'east': (1480, 13, 2, 9),
      'north': (1482, 13, 2, 9), 'west': (1484, 13, 2, 9), 'south': (1486, 13, 2, 9)}),
    ([-1.125, 0.0, -0.1875], [0.375, 1.6875, 0.375],
     {'down': (1482, 0, 2, 2), 'up': (1484, 0, 2, 2), 'east': (1480, 2, 2, 9),
      'north': (1482, 2, 2, 9), 'west': (1484, 2, 2, 9), 'south': (1486, 2, 2, 9)}),
    ([0.1875, 0.0, -0.1875], [0.375, 0.5625, 0.375],
     {'down': (1466, 26, 2, 2), 'up': (1468, 26, 2, 2), 'east': (1464, 28, 2, 3),
      'north': (1466, 28, 2, 3), 'west': (1468, 28, 2, 3), 'south': (1470, 28, 2, 3)}),
    ([-0.5625, 0.0, -0.1875], [0.375, 0.5625, 0.375],
     {'down': (1458, 26, 2, 2), 'up': (1460, 26, 2, 2), 'east': (1456, 28, 2, 3),
      'north': (1458, 28, 2, 3), 'west': (1460, 28, 2, 3), 'south': (1462, 28, 2, 3)}),
]
_BOT_HEAD = [
    ([-0.5625, 1.6875, -0.5625], [1.125, 1.3125, 0.9375],
     {'down': (1461, 0, 6, 5), 'up': (1467, 0, 6, 5), 'east': (1456, 5, 5, 7),
      'north': (1461, 5, 6, 7), 'west': (1467, 5, 5, 7), 'south': (1472, 5, 6, 7)}),
    ([-0.1875, 1.6875, -0.75], [0.375, 0.5625, 0.1875],
     {'down': (1474, 1, 2, 1), 'up': (1476, 1, 2, 1), 'east': (1473, 2, 1, 3),
      'north': (1474, 2, 2, 3), 'west': (1476, 2, 1, 3), 'south': (1477, 2, 2, 3)}),
]
# 头骨骼的旋转轴心（原模型 [0, 1.6875, -0.15]，按 BOT_SCALE 放大）
BOT_HEAD_PIVOT = [0.0, round(1.6875 * BOT_SCALE, 6), round(-0.15 * BOT_SCALE, 6)]


def bot_cubes(part):
    """托管机器人的立方体：part='body' 或 'head'。"""
    out = []
    for origin, size, uvs in (_BOT_BODY if part == 'body' else _BOT_HEAD):
        uv = {}
        for face, (x, y, w, h) in uvs.items():
            nx, ny = A.robot_uv(x, y)
            uv[face] = rect((nx, ny), w, h)
        out.append({
            'origin': [r6(v * BOT_SCALE) for v in origin],
            'size': [r6(v * BOT_SCALE) for v in size],
            'uv': uv,
        })
    return out


def bot_center_expr(j):
    """机器人中心相对手牌横向中心的偏移变量名（表达式在 pre_animation 里算成 v.bo{j}）。"""
    return 'v.bo%d' % j


def build_geo():
    bones = [
        {'name': 'root', 'pivot': [0, 0, 0]},
        {'name': 'viewer_state', 'parent': 'root', 'pivot': [0, 0, 0]},
    ]
    # 108 张牌 + 各自的高亮框（作为子骨骼，跟随卡片）
    for n in range(CARD_SLOTS):
        bones.append({
            'name': 'card_%d' % n, 'parent': 'root', 'pivot': [0, 0, 0],
            'cubes': [{'origin': list(CARD_ORIGIN), 'size': list(CARD_SIZE),
                       'uv': card_uv(face_of(n))}],
        })
        bones.append({
            'name': 'highlight_%d' % n, 'parent': 'card_%d' % n, 'pivot': [0, 0, 0],
            'cubes': [{'origin': [-2.5, 0.155, -3.75], 'size': [5, 0.045, 7.5],
                       # 高亮框是「压在牌面上的镂空薄片」，四面必须透明（否则一圈白描边）
                       'uv': tile_uv(HILITE, A.CARD_W, A.CARD_H, clear_sides=True)}],
        })
    # 对手手牌（正反两面都是「?」未知牌面：别人的牌你看不到牌面）
    for s in range(4):
        bones.append({'name': 'fake_vis_%d' % s, 'parent': 'root', 'pivot': [0, 0, 0]})
        for i in range(FAKE_MAX):
            bones.append({
                'name': 'fake_%d_%d' % (s, i), 'parent': 'fake_vis_%d' % s, 'pivot': [0, 0, 0],
                'cubes': [{'origin': list(CARD_ORIGIN), 'size': list(CARD_SIZE),
                           'uv': opponent_uv()}],
            })
    # 定位器激光点（2026-10-15 用户：「做成像黑色框那样的，是在平面上的」）：
    # 一块 1.8×3.0 的**薄片**（厚 0.008，与按钮同量级），rotation/位置全部由 layout 按
    # 「命中的是手牌还是按钮」分支给出 —— 手牌态 rx=65 与牌面平行共面，按钮态同按钮片。
    # UV 用图集里那条**纯白长条**（CARD_SIDE_WHITE，与牌侧面同一来源），所以点永远是纯白。
    # 以前这里是粒子（朝向镜头的小方片），贴斜面有悬浮/穿模感，已退役。
    bones.append({
        'name': 'laser_dot', 'parent': 'root', 'pivot': [0, 0, 0],
        'cubes': [{'origin': [-0.9, 0, -1.5], 'size': [1.8, 0.008, 3.0],
                   'uv': tile_uv(A.card_side_white_uv(), 4, 4)}],
    })
    # 按钮
    bones.append({'name': 'buttons_visibility', 'parent': 'root', 'pivot': [0, 0, 0]})
    for k in range(4):
        bones.append({'name': 'button_slot%d' % k, 'parent': 'buttons_visibility',
                      'pivot': [0, 0, 0], 'cubes': []})
    for slot, act in A.SLOT_ACTION_PAIRS:
        for state, dy in (('label', 0.0), ('pressed', 0.010)):
            tile = A.btn_tile(act, 'normal' if state == 'label' else 'pressed')
            bones.append({
                'name': 'button_%s_slot%d_%s' % (state, slot, act),
                'parent': 'button_slot%d' % slot, 'pivot': [0, 0, 0],
                'cubes': [{'origin': [-BUTTON_W, round(dy, 6), -BUTTON_D],
                           'size': [BUTTON_W * 2, 0.008, BUTTON_D * 2],
                           # 按钮也是薄片：四面透明，只留正面的按钮图
                           'uv': tile_uv(tile, A.BTN_W, A.BTN_H, clear_sides=True)}],
            })
    # 中央抽牌堆（永远 5 张，平铺在台面上；朝上的面是**牌背**，不是 `?`）
    for p in range(5):
        bones.append({
            'name': 'pile_%d' % p, 'parent': 'root', 'pivot': [0, 0, 0],
            'cubes': [{'origin': list(CARD_ORIGIN), 'size': list(CARD_SIZE),
                       'uv': pile_uv()}],
        })
    # 桌面标记
    bones.append(plate('color_disc_0', 'root', 3.0, 3.0, A.COLOR_DISCS[0], A.DISC_SIZE, A.DISC_SIZE))
    bones.append(plate('color_disc_1', 'root', 3.0, 3.0, A.COLOR_DISCS[1], A.DISC_SIZE, A.DISC_SIZE))
    bones.append(plate('color_disc_2', 'root', 3.0, 3.0, A.COLOR_DISCS[2], A.DISC_SIZE, A.DISC_SIZE))
    bones.append(plate('color_disc_3', 'root', 3.0, 3.0, A.COLOR_DISCS[3], A.DISC_SIZE, A.DISC_SIZE))
    bones.append(plate('dir_cw', 'root', 4.0, 4.0, A.DIR_ARROWS[0], A.MARK_SIZE, A.MARK_SIZE))
    bones.append(plate('dir_ccw', 'root', 4.0, 4.0, A.DIR_ARROWS[1], A.MARK_SIZE, A.MARK_SIZE))
    for s in range(4):
        bones.append(plate('turn_%d' % s, 'root', 4.0, 4.0, A.TURN_ARROW,
                           A.MARK_SIZE, A.MARK_SIZE))
        bones.append(plate('dealer_%d' % s, 'root', 3.4, 3.4, A.DEALER_BADGE,
                           A.MARK_SIZE, A.MARK_SIZE))
    # 托管机器人（每座位一份：身体骨骼 + 头骨骼；默认 scale=0 隐藏，见 build_table 的布局动画）
    for j in range(4):
        bones.append({'name': 'bot_%d' % j, 'parent': 'root', 'pivot': [0, 0, 0],
                      'cubes': bot_cubes('body')})
        bones.append({'name': 'bot_head_%d' % j, 'parent': 'bot_%d' % j,
                      'pivot': list(BOT_HEAD_PIVOT), 'cubes': bot_cubes('head')})
    doc = {
        'format_version': '1.12.0',
        'minecraft:geometry': [{
            'description': {
                'identifier': 'geometry.tabletopgame.uno_table',
                'texture_width': A.ATLAS_W, 'texture_height': A.ATLAS_H,
                'visible_bounds_width': 8, 'visible_bounds_height': 4,
                'visible_bounds_offset': [0, 1.5, 0],
            },
            'bones': bones,
        }],
    }
    os.makedirs(os.path.dirname(GEO_OUT), exist_ok=True)
    with open(GEO_OUT, 'w', encoding='utf-8') as fh:
        json.dump(doc, fh, ensure_ascii=False, separators=(',', ':'))
    print('geo: %d bones -> %s' % (len(bones), GEO_OUT))
    build_clickbox_geo()
    return len(bones)


def build_clickbox_geo():
    """点击捕获框的几何体：一根空骨骼，永远不渲染任何东西。"""
    doc = {
        'format_version': '1.12.0',
        'minecraft:geometry': [{
            'description': {
                'identifier': 'geometry.tabletopgame.uno_clickbox',
                'texture_width': 16, 'texture_height': 16,
                'visible_bounds_width': 1, 'visible_bounds_height': 1,
                'visible_bounds_offset': [0, 0.5, 0],
            },
            'bones': [{'name': 'root', 'pivot': [0, 0, 0]}],
        }],
    }
    os.makedirs(os.path.dirname(CLICKBOX_GEO_OUT), exist_ok=True)
    with open(CLICKBOX_GEO_OUT, 'w', encoding='utf-8') as fh:
        json.dump(doc, fh, ensure_ascii=False, separators=(',', ':'))
    print('geo: clickbox -> %s' % os.path.basename(CLICKBOX_GEO_OUT))
