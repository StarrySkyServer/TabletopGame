# -*- coding: utf-8 -*-
"""UNO 资源图集布局与素材来源（TabletopGamePlugin 内置资源包）。

图集 uno_atlas.png = 2048 x 2048 RGBA，分三个区：
  A. 牌面区   (0,0)-(1280,1680)：56 格 160x240，8 列 x 7 行
     0..12   红 0-9 / 跳过 / 反转 / +2
     13..25  黄
     26..38  绿
     39..51  蓝
     52      Wild
     53      Wild+4
     54      牌背（黑底圆环，抽牌堆朝上的面用它）
     55      "?"（未知牌面，对手手牌朝外的那一面用它）
  B. 标记区   (1280,0)-(2048,1680)：回合箭头、当前颜色圆盘、方向箭头、庄家徽记
  C. 按钮区   (0,1696)-(2048,2048)：11 个动作 x 常态/按下 = 22 张 220x74，9 列 x 4 行
"""
import math
import os
from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.normpath(os.path.join(HERE, '..', '..'))
RP = os.path.join(REPO, 'src/main/resources/assets/resource_pack')
OUT_ATLAS = os.path.join(RP, 'textures/tabletopgame/uno/uno_atlas.png')

DDZ = 'D:/CodeProject/Gobang/斗地主'
DECK_SRC = os.path.join(DDZ, 'uno/资源/preview_full_deck.png')
# 按钮素材：新版 spritesheet 在原有 7 键之后多出「红色/黄色/绿色/蓝色」4 个选色键，
# 前 7 键与旧图逐像素一致（已核对 maxdiff=0），所以整表直接换新版即可。
BTN_SRC = os.path.join(DDZ, 'uno/资源/buttons_spritesheet (1).png')

ATLAS_W = ATLAS_H = 2048

# ---- A. 牌面 ----
CARD_W, CARD_H = 160, 240
CARD_COLS, CARD_ROWS = 8, 7
CARD_COUNT = 56
FACE_RED, FACE_YELLOW, FACE_GREEN, FACE_BLUE = 0, 13, 26, 39
FACE_WILD, FACE_WILD4, FACE_BACK, FACE_HIDDEN = 52, 53, 54, 55

# ---- 源图网格 ----
SRC_CELL_W, SRC_CELL_H = 120, 180
SRC_PITCH_X, SRC_PITCH_Y = 130, 190
SRC_PAD = 10
SRC_COLS = 14


def card_cell(k):
    """源全景图中第 k 格的裁剪框。"""
    c, r = k % SRC_COLS, k // SRC_COLS
    x = SRC_PAD + c * SRC_PITCH_X
    y = SRC_PAD + r * SRC_PITCH_Y
    return (x, y, x + SRC_CELL_W, y + SRC_CELL_H)


def face_tile(k):
    """图集中第 k 张牌面的 (x, y)。"""
    c, r = k % CARD_COLS, k // CARD_COLS
    return (c * CARD_W, r * CARD_H)


# ---- B. 标记区 ----
MARK_X = 1300
TURN_ARROW = (MARK_X, 20)          # 64x64 当前回合箭头
COLOR_DISCS = [(MARK_X + i * 60, 120) for i in range(4)]   # 48x48 四色圆盘 R,Y,G,B
DIR_ARROWS = [(MARK_X, 200), (MARK_X + 80, 200)]           # 64x64 顺时针 / 逆时针
DEALER_BADGE = (MARK_X, 300)       # 64x64 庄家徽记
HILITE = (1450, 400)               # 160x240 选中/悬停黑框
DISC_SIZE = 48
MARK_SIZE = 64

# ---- C. 按钮 ----
BTN_W, BTN_H = 220, 74
BTN_X0, BTN_Y0 = 0, 1696
BTN_COLS = 9
BTN_PITCH_X, BTN_PITCH_Y = 224, 80

# 动作码（写入实体属性 controls 的 4 位槽，1..11，0 = 空）
ACTIONS = ['play', 'draw', 'skip', 'hint', 'cancel', 'next', 'exit',
           'c_red', 'c_yellow', 'c_green', 'c_blue']
CODE = {a: i + 1 for i, a in enumerate(ACTIONS)}

# 用户素材里的按钮列号（新版 spritesheet 共 11 列）
SHEET_INDEX = {'skip': 0, 'play': 1, 'draw': 2, 'hint': 3, 'next': 4, 'exit': 5, 'cancel': 6,
               'c_red': 7, 'c_yellow': 8, 'c_green': 9, 'c_blue': 10}
SHEET_PITCH_X, SHEET_PAD = 340, 20
SHEET_CELL_W, SHEET_CELL_H = 320, 120
SHEET_Y_NORMAL, SHEET_Y_PRESSED = 20, 160

# 桌面按钮组。**数组下标 = `controls` 属性的 4 位槽下标，且下标 0 在屏幕上最左**。
#
# 左右关系的依据（不要凭直觉改符号）：按钮沿座位帧的 AX 轴排开，
#   AX = (-OUT_Z, OUT_X)，物理含义是「从入座玩家看过去的右手边」
#   （例：座位1=南，OUT=(0,-1) → AX=(1,0)=世界 +x；玩家面朝 -z，右手正是 +x）。
# 位置公式 offset = (可见序号 - 居中) * BUTTON_GAP，因此 **BUTTON_GAP 取正值**时
# 槽号越大越靠玩家的右手，槽 0 落在玩家左手边 —— 与下面数组「屏幕从左到右」的写法一致。
# （BUTTON_GAP 取负会把整排左右镜像：射线与动画仍自洽，只是排序反了。）
#   play   取消 提示 抽牌 出牌
#   drawn  出牌 跳过（抽牌后，可出则出、不可出则跳过）
#   settle 退出 下一局（一局结束后的结算按钮）
#   color  红 黄 绿 蓝（按牌面颜色顺序）
BUTTON_GROUPS = {
    'play':    ['cancel', 'hint', 'draw', 'play'],
    'drawn':   ['play', 'skip'],
    'settle':  ['exit', 'next'],
    'color':   ['c_red', 'c_yellow', 'c_green', 'c_blue'],
}
SLOT_ACTION_PAIRS = []
_seen = set()
for _g in ('play', 'drawn', 'settle', 'color'):
    for _s, _a in enumerate(BUTTON_GROUPS[_g]):
        if (_s, _a) not in _seen:
            _seen.add((_s, _a))
            SLOT_ACTION_PAIRS.append((_s, _a))

# UNO 四色（取自牌面素材的实心区域）
UNO_COLORS = {
    'c_red': (208, 46, 44, 255),
    'c_yellow': (240, 176, 28, 255),
    'c_green': (58, 152, 54, 255),
    'c_blue': (42, 92, 168, 255),
}
COLOR_ORDER = ['c_red', 'c_yellow', 'c_green', 'c_blue']

# 卡片立方体侧面用的取样点：**纸白色**（旧的「全局纸边」色块）。
#
# 2026-10-15 历史：用户先要求「留白边长方形」，后要求「白边直接用牌环色填充」
# （见下方 CARD_SIDE_* 与 fill_paper_with_ring）。现在卡片侧面走**每张牌自己的环色色块**，
# 这个全局纸白色块已不再被卡片引用，只留给"万一要回退"的场景（图集里照样画着）。
SWATCH = (2036, 2036)
SWATCH_SIZE = 8
# 纸张色（`preview_full_deck.png` 四角的底色）
PAPER = (250, 250, 252, 255)

# ---- 每张牌自己的「环色」侧面色块网格 ----
# 2026-10-15 用户口径：「牌面的那些白边……直接用那个牌边的颜色去填充，就是围在牌那一圈环的颜色」。
#
#  · 牌面：把素材自带的纸底（只在四角露出）填成**该牌外圈环的颜色**（见 fill_paper_with_ring），
#    牌就成了「长方形、四边是彩环」的观感；
#  · 牌侧：0.12 厚的四个侧面也必须是**同一环色**（否则一圈白边又露出来）。
#    环色每张牌都不同，没法共用一个取样点 —— 这里给 56 张牌各开一个 8x8 实心色块，
#    紧挨着排成 8 列 x 7 行（块与块之间不留缝：mipmap 混色时 alpha 仍是 1，
#    entity_alphatest 才不会把侧面判成透明）。取样点取块心（+2,+2, 4x4）。
CARD_SIDE_X, CARD_SIDE_Y = 1300, 1200        # 该区域在整张图集里四周 ≥40px 全空
CARD_SIDE_BLOCK = 8
CARD_SIDE_COLS = 8


def card_side_block(k):
    """第 k 张牌的侧面色块**左上角**（8x8 实心块，供 build_atlas 画色用）。"""
    c, r = k % CARD_SIDE_COLS, k // CARD_SIDE_COLS
    return (CARD_SIDE_X + c * CARD_SIDE_BLOCK, CARD_SIDE_Y + r * CARD_SIDE_BLOCK)


def card_side_uv(k):
    """第 k 张牌（图集格索引）的侧面取样块中心左上角（配 rect(..., 4, 4) 用）。"""
    x, y = card_side_block(k)
    return (x + 2, y + 2)


# ---- 所有牌共用的**纯白侧面**长条 ----
# 2026-10-15 用户最终口径：「侧面还有点瑕疵，你在那张大贴图上画一个白色(#ffffff)的长条，
# 然后把所有牌的侧面都框到那里去，亮牌的侧面是纯白色就行了」。
# 于是牌的四个侧面不再用各自的环色块，统一指向这里的一条纯白长条（横向铺满，mipmap 安全，
# 四周 ≥16px 无其他贴图）。牌面/牌背照旧，只有 0.12 厚的那一圈侧面变纯白。
CARD_SIDE_WHITE = (1300, 1272)          # 白色长条左上角（CARD_SIDE 区下方，四周留缝）
CARD_SIDE_WHITE_W = 64                  # 长条宽（8 块），高 = 8，横向一条
CARD_SIDE_WHITE_H = 8


def card_side_white_uv():
    """所有牌侧面共用的纯白取样点中心左上角（配 rect(..., 4, 4) 用）。"""
    return (CARD_SIDE_WHITE[0] + CARD_SIDE_WHITE_W // 2 - 2, CARD_SIDE_WHITE[1] + 2)

# 桌面标记（颜色圆盘 / 方向箭头 / 回合箭头 / 庄家徽记）与按钮、高亮框立方体**侧面**用的
# 全透明取样点：这些是「贴在台面上的薄片」，侧面一旦有颜色就是一圈描边（白边/黑边都难看）。
# 该点所在区域在整张图集里始终为空（四周 ≥20px 内没有任何贴图），所以 mipmap 采样
# 也不会被邻居污染；图集底色本身是 (0,0,0,0)，无需额外绘制。
SWATCH_CLEAR = (2032, 1960)


# ---- D. 托管机器人贴图 ----
# 「托管」用的机器人模型（见 build_model 的 BOT_* 骨骼）沿用**斗地主插件**那张模型：
# 它的贴图是一块标准 32x32 模型贴图，左上角位于斗地主图集的 (1456, 0)。
# 这里原样搬到本图集深处（周围 ≥20px 全空，避免 mipmap 采样到邻居），
# 几何体的 UV 用 robot_uv() 平移过去 —— 模型外观与斗地主插件逐像素一致。
DDZ_ATLAS = ('D:/CodeProject/Gobang/斗地主/Doudizhu/src/main/resources/'
             'assets/resource_pack/textures/ddz/table_atlas.png')
ROBOT_SRC = (1456, 0)
ROBOT_SIZE = 32
ROBOT_TEX = (1640, 400)


def robot_src_tile():
    """取出斗地主图集里的机器人贴图块（32x32）。"""
    im = Image.open(DDZ_ATLAS).convert('RGBA')
    x, y = ROBOT_SRC
    return im.crop((x, y, x + ROBOT_SIZE, y + ROBOT_SIZE))


def robot_uv(u, v):
    """斗地主图集 UV → 本图集 UV。"""
    return (u - ROBOT_SRC[0] + ROBOT_TEX[0], v - ROBOT_SRC[1] + ROBOT_TEX[1])


# ------------------------------------------------------------------ helpers
def btn_tile(action, state):
    """按钮贴图槽位 (x, y)。state: 'normal' / 'pressed'。"""
    idx = ACTIONS.index(action) * 2 + (0 if state == 'normal' else 1)
    c, r = idx % BTN_COLS, idx // BTN_COLS
    return (BTN_X0 + c * BTN_PITCH_X, BTN_Y0 + r * BTN_PITCH_Y)


def font(size):
    for p in ('C:/Windows/Fonts/msyhbd.ttc', 'C:/Windows/Fonts/msyh.ttc',
              'C:/Windows/Fonts/simhei.ttf'):
        if os.path.exists(p):
            try:
                from PIL import ImageFont
                return ImageFont.truetype(p, size)
            except Exception:
                pass
    from PIL import ImageFont
    return ImageFont.load_default()


def fit_tile(img, w, h):
    """等比缩放并居中到 w x h 的透明画布。"""
    bb = img.getbbox()
    if bb:
        img = img.crop(bb)
    s = min(w / img.width, h / img.height)
    nw, nh = max(1, round(img.width * s)), max(1, round(img.height * s))
    img = img.resize((nw, nh), Image.LANCZOS)
    tile = Image.new('RGBA', (w, h), (0, 0, 0, 0))
    tile.paste(img, ((w - nw) // 2, (h - nh) // 2), img)
    return tile


def sheet_button(action, state):
    """从用户按钮素材取一张（等比缩放居中），并抹掉素材自带的纯白高光描边。"""
    sheet = Image.open(BTN_SRC).convert('RGBA')
    c = SHEET_INDEX[action]
    y = SHEET_Y_NORMAL if state == 'normal' else SHEET_Y_PRESSED
    cell = sheet.crop((SHEET_PAD + c * SHEET_PITCH_X, y,
                       SHEET_PAD + c * SHEET_PITCH_X + SHEET_CELL_W, y + SHEET_CELL_H))
    return dewhite(fit_tile(cell, BTN_W, BTN_H))


def knockout_paper(tile, lum_min=196, sat_tol=46, band=3):
    """把「与图块边界连通的近白纸底」抠成透明，并把 1~2px 的抗锯齿亮边羽化 + 去晕。

    **为什么必须做这一步**：UNO 牌面素材（`preview_full_deck.png`）是画在**不透明白底**
    (250,250,252) 上的圆角矩形。牌桌实体用 `entity_alphatest`，白底是 opaque 的，
    贴上去就会在每个圆角四周露出一圈白色 —— 就是玩家反馈的「牌的边边有白色像素」。

    做法（逐像素、不依赖素材的具体配色）：
      1. 四连通洪泛，从图块四条边出发，把「近白且低饱和」的像素标为 *外部*；
      2. 偶数源的 BFS 距离变换，得到每个像素到外部的距离 d（单位：px）；
      3. d == 0 → 全透明；1 <= d < band → alpha = 255*d/band，并把颜色换成**最近的不透明牌体色**
         （避免残留一圈浅色晕 —— LANCZOS 缩放会把亮边摊成 2~3px 的浅色渐变）；
      4. d >= band → 原样保留。

    只在**最终尺寸**（160x240）上做：若先抠再缩放，PIL 的 RGBA 重采样会把透明区的 (0,0,0)
    混进牌边，反而转出一圈暗边。
    """
    w, h = tile.size
    px = tile.load()

    def is_paper(i, j):
        r, g, b, a = px[i, j]
        if a <= 240:
            return True
        mx, mn = max(r, g, b), min(r, g, b)
        return mn >= lum_min and (mx - mn) <= sat_tol

    outside = bytearray(w * h)
    stack = []
    for i in range(w):
        for j in (0, h - 1):
            if not outside[j * w + i] and is_paper(i, j):
                outside[j * w + i] = 1
                stack.append((i, j))
    for j in range(h):
        for i in (0, w - 1):
            if not outside[j * w + i] and is_paper(i, j):
                outside[j * w + i] = 1
                stack.append((i, j))
    while stack:
        i, j = stack.pop()
        for di, dj in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            ni, nj = i + di, j + dj
            if 0 <= ni < w and 0 <= nj < h:
                k = nj * w + ni
                if not outside[k] and is_paper(ni, nj):
                    outside[k] = 1
                    stack.append((ni, nj))

    INF = 1 << 20
    dist = [0 if outside[k] else INF for k in range(w * h)]
    frontier = [k for k in range(w * h) if outside[k]]
    while frontier:
        nxt = []
        for k in frontier:
            i, j = k % w, k // w
            for di, dj in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                ni, nj = i + di, j + dj
                if 0 <= ni < w and 0 <= nj < h:
                    nk = nj * w + ni
                    if dist[nk] > dist[k] + 1:
                        dist[nk] = dist[k] + 1
                        nxt.append(nk)
        frontier = nxt

    # 羽化带里需要的「牌体参考色」：取窗口内第一个 d >= band 的像素
    body = {}
    for j in range(h):
        for i in range(w):
            k = j * w + i
            if outside[k] or dist[k] >= band:
                continue
            ref = None
            for rad in range(band, band + 3):
                for dj in range(-rad, rad + 1):
                    for di in range(-rad, rad + 1):
                        ni, nj = i + di, j + dj
                        if 0 <= ni < w and 0 <= nj < h:
                            nk = nj * w + ni
                            if dist[nk] >= band and px[ni, nj][3] > 200:
                                ref = px[ni, nj]
                                break
                    if ref:
                        break
                if ref:
                    break
            body[k] = ref

    for j in range(h):
        for i in range(w):
            k = j * w + i
            d = dist[k]
            if d == 0:
                px[i, j] = (0, 0, 0, 0)
            elif d < band:
                a = int(round(255.0 * d / band))
                ref = body.get(k)
                if ref is None:
                    r, g, b, _ = px[i, j]
                else:
                    r, g, b = ref[0], ref[1], ref[2]
                px[i, j] = (r, g, b, a)
    return tile


def _is_paperish(r, g, b, a, lum_min, sat_tol):
    """近白纸底判据：够亮 + 够"灰"（纸底 (250,250,252)，饱和度极低）。"""
    if a <= 240:
        return True
    mx, mn = max(r, g, b), min(r, g, b)
    return mn >= lum_min and (mx - mn) <= sat_tol


def paper_mask(tile, lum_min=170, sat_tol=60):
    """从图块四条边四连通洪泛出「与边界连通的近白纸底」，返回 w*h 的 bytearray。

    阈值故意取得比 `knockout_paper` 宽（196/46 → 170/60）：纸底与牌环之间那 1~2px 的
    抗锯齿像素（例如 (163,98,97)）也要算进来，否则填色后会在牌的外沿留一圈**浅色晕**。
    牌体内部的白色（UNO 椭圆的 "UNO" 字、数字）不与图块边界连通，洪泛打不到，天然安全。
    """
    w, h = tile.size
    px = tile.load()
    out = bytearray(w * h)
    stack = []

    def seed(i, j):
        k = j * w + i
        if not out[k] and _is_paperish(*px[i, j], lum_min, sat_tol):
            out[k] = 1
            stack.append((i, j))

    for i in range(w):
        seed(i, 0)
        seed(i, h - 1)
    for j in range(h):
        seed(0, j)
        seed(w - 1, j)
    while stack:
        i, j = stack.pop()
        for di, dj in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            ni, nj = i + di, j + dj
            if 0 <= ni < w and 0 <= nj < h and not out[nj * w + ni] \
                    and _is_paperish(*px[ni, nj], lum_min, sat_tol):
                out[nj * w + ni] = 1
                stack.append((ni, nj))
    return out


def _lum(c):
    return 0.299 * c[0] + 0.587 * c[1] + 0.114 * c[2]


def ring_color_of(tile, mask, band=5):
    """环色 = 紧贴纸底 `band` 像素内、「非纸底且不透明」像素的中位色。

    取中位色而不是均值：环上可能压着 1px 更深的描边，中位数对它不敏感。
    """
    w, h = tile.size
    px = tile.load()
    samples = []
    for j in range(h):
        for i in range(w):
            if mask[j * w + i]:
                continue
            near = False
            for dj in range(-band, band + 1):
                for di in range(-band, band + 1):
                    ni, nj = i + di, j + dj
                    if 0 <= ni < w and 0 <= nj < h and mask[nj * w + ni]:
                        near = True
                        break
                if near:
                    break
            if near:
                r, g, b, a = px[i, j]
                if a >= 200:
                    samples.append((r, g, b))
    if not samples:
        return None
    samples.sort(key=lambda c: c[0] + c[1] + c[2])
    return samples[len(samples) // 2]


# 「边缘带」压平的参数（见 fill_paper_with_ring）
#
# 2026-10-15 三改（用户原话）：「这里还有一些其他的渐变红色，我要**这些边缘都只用一种颜色**」。
# 前两版只处理了"纸底 + 纸底外沿 3px"，而素材的卡框本身是多层描边：
#   深描边 (109,3,0) → 环带 (126,29,26) → 亮倒角 (163,38,34) → 过渡 (196,47,42) → 牌面
# 于是角落弧线上仍能看到好几道红。现改为：**距纸底 FLAT_D 以内的整圈像素一律刷成环色**。
#
# 两个例外门槛（都是"过亮像素"的处理，实测数据定出）：
#   · 距纸底 ≤ FLAT_CORE 的：**无条件压平**。这一圈是纸底与卡边的抗锯齿混色
#     （实测每张彩牌恰好有 ~32 个这样的亮像素，距离全部 = 1），不压就是一圈"淡边"。
#   · 距纸底 > FLAT_CORE 且比环色亮出 FLAT_LUM 以上的：保留。
#     那是背面牌的内嵌白框线之类的**设计元素**（背面白框在距离 8~9.5 处，亮度比环色高 100+），
#     压掉会改图案；彩牌的倒角（亮 17~58）与过渡色（亮 33）都远低于门槛，会一并压平。
FLAT_D = 9.5
FLAT_CORE = 3.0
FLAT_LUM = 80.0


def _chamfer_dist(mask, w, h):
    """纸底 mask 的距离场（两遍 chamfer，欧氏近似，误差 <5%）。

    只需要"距纸底几像素"这一个量，用 O(n) 的 chamfer 就够，不必上广度优先。
    8 邻域权重 1 / √2：正对边上的像素距离就是真实像素数。
    """
    INF = 1e9
    SQ2 = 1.41421356
    d = [0.0 if mask[k] else INF for k in range(w * h)]
    for y in range(h):
        base = y * w
        for x in range(w):
            i = base + x
            v = d[i]
            if x:
                t = d[i - 1] + 1.0
                if t < v:
                    v = t
            if y:
                t = d[i - w] + 1.0
                if t < v:
                    v = t
                if x:
                    t = d[i - w - 1] + SQ2
                    if t < v:
                        v = t
                if x + 1 < w:
                    t = d[i - w + 1] + SQ2
                    if t < v:
                        v = t
            d[i] = v
    for y in range(h - 1, -1, -1):
        base = y * w
        for x in range(w - 1, -1, -1):
            i = base + x
            v = d[i]
            if x + 1 < w:
                t = d[i + 1] + 1.0
                if t < v:
                    v = t
            if y + 1 < h:
                t = d[i + w] + 1.0
                if t < v:
                    v = t
                if x + 1 < w:
                    t = d[i + w + 1] + SQ2
                    if t < v:
                        v = t
                if x:
                    t = d[i + w - 1] + SQ2
                    if t < v:
                        v = t
            d[i] = v
    return d


def fill_paper_with_ring(tile, band=5, flat=FLAT_D, lum_gate=FLAT_LUM):
    """把「纸底 + 整圈边缘带」压成**这张牌的环色**（返回 (新图, 环色 RGB)）。

    需求原话（2026-10-15）：「牌面的那些白边能不能直接用，那个牌边的颜色去填充，
    就是围在牌那一圈环的颜色」→「处理得不是很好，还是有一些淡淡的边框，
    **外围全部只用这一种颜色**」→「这里还有一些其他的渐变红色，
    我要**这些边缘都只用一种颜色**」。

    做法：
      1. `paper_mask` 洪泛出纸底（只露在四角圆弧与 1px 外沿）；
      2. `ring_color_of` 取环色（紧贴纸底一圈的中位色，即素材里"围在牌那一圈"的深色环）；
      3. 纸底整片刷成环色 —— 四角的圆弧被填满，整张牌变成**长方形、四边是彩环**；
      4. **压平边缘带**：距纸底不超过 `flat` 像素的卡面像素一律刷成环色。
         卡框自带的那几层描边（深描边 / 亮倒角 / 抗锯齿过渡）全部并进这一种颜色，
         整圈只剩「环色 → 牌面」一次跳变；
      5. 例外：距纸底超过 {@link #FLAT_CORE} 像素、且**比环色亮出 `lum_gate` 以上**的像素
         保持原样 —— 那是背面牌的内嵌白框线之类的设计元素（实测只在距离 ≥8 处出现），
         压掉会改图案。贴边 3px 内的亮像素是纸底混色，**无条件压平**（见 FLAT_CORE 注释）。

    绝不能用"按亮度插值"处理交界像素 —— 插值会留下一圈「淡淡的边框」
    （比环色浅、比纸底深的中间色），那是用户两次反馈的老问题。
    """
    w, h = tile.size
    out = tile.copy()
    px = out.load()
    mask = paper_mask(tile)
    ring = ring_color_of(tile, mask, band)
    if ring is None:
        return out, None
    lum_ring = _lum(ring)
    # 1) 纸底填环色
    for j in range(h):
        for i in range(w):
            if mask[j * w + i]:
                px[i, j] = (ring[0], ring[1], ring[2], 255)
    # 2) 压平：距纸底 flat 像素内的卡面像素 → 环色（深处过亮的设计元素除外）
    dist = _chamfer_dist(mask, w, h)
    for j in range(h):
        base = j * w
        for i in range(w):
            k = base + i
            if mask[k] or dist[k] > flat:
                continue
            if dist[k] > FLAT_CORE:
                r, g, b, a = px[i, j]
                if a <= 0:
                    continue
                if _lum((r, g, b)) > lum_ring + lum_gate:
                    continue
            px[i, j] = (ring[0], ring[1], ring[2], px[i, j][3])
    return out, ring


def dewhite(tile, lum_min=238, sat_tol=14, radius=3, band=None):
    """把按钮贴图**外圈**的纯白高光描边抹成周围的浅灰底色（玩家反馈的「按钮白边」）。

    按钮素材（`buttons_spritesheet (1).png`）是「深色描边 + 一圈 (247,247,247) 高光 + 浅灰面」
    的拟物按钮。真机上那圈高光在深色台面上就成了一道白边。这里把近白像素替换成
    radius 邻域内**非白**像素的中位数色：按钮变成干净的浅灰圆角块，深色描边保持不变。

    **必须限定在 `band` 像素的外圈范围内**（默认取图块短边的 14%）：按下态（绿色）按钮的
    文字也是纯白，早期版本对全图做替换，把「出牌 / 取消 / 提示 / 抽牌」的白字一起污染成
    深浅不一的杂色（玩家反馈「选中之后那些文字很明显被污染过了，不是白色的字体」）。
    白高光只贴着深色外描边（距边缘 ~2~4px），白字在正中间，两者用一圈边界带就能干净分开。
    """
    w, h = tile.size
    if band is None:
        band = max(6, int(min(w, h) * 0.14))
    src = tile.load()
    out = tile.copy()
    dst = out.load()
    for j in range(h):
        edge_row = j < band or j >= h - band
        for i in range(w):
            # 只碰外圈那一圈边界带：中间的白色是按钮文字，绝不能动
            if not edge_row and band <= i < w - band:
                continue
            r, g, b, a = src[i, j]
            if a <= 0:
                continue
            mx, mn = max(r, g, b), min(r, g, b)
            if mn < lum_min or (mx - mn) > sat_tol:
                continue
            samples = []
            for dj in range(-radius, radius + 1):
                for di in range(-radius, radius + 1):
                    ni, nj = i + di, j + dj
                    if 0 <= ni < w and 0 <= nj < h:
                        sr, sg, sb, sa = src[ni, nj]
                        if sa <= 0:
                            continue
                        smx, smn = max(sr, sg, sb), min(sr, sg, sb)
                        if smn >= lum_min and (smx - smn) <= sat_tol:
                            continue
                        samples.append((sr, sg, sb))
            if not samples:
                continue
            samples.sort(key=lambda c: c[0] + c[1] + c[2])
            mr, mg, mb = samples[len(samples) // 2]
            dst[i, j] = (mr, mg, mb, a)
    return out


def black_frame(thick=3, radius=10, inset=2):
    """卡片选中/可出牌高亮：半透明黑框（内部透明）。"""
    SS = 4
    w, h = CARD_W * SS, CARD_H * SS
    img = Image.new('RGBA', (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([inset * SS, inset * SS, w - 1 - inset * SS, h - 1 - inset * SS],
                        radius=radius * SS, outline=(20, 20, 20, 235), width=thick * SS)
    return img.resize((CARD_W, CARD_H), Image.LANCZOS)


def gold_frame(thick=3, radius=10, inset=2):
    """可出牌提示：金色高亮框。"""
    SS = 4
    w, h = CARD_W * SS, CARD_H * SS
    img = Image.new('RGBA', (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([inset * SS, inset * SS, w - 1 - inset * SS, h - 1 - inset * SS],
                        radius=radius * SS, outline=(255, 214, 64, 240), width=thick * SS)
    return img.resize((CARD_W, CARD_H), Image.LANCZOS)


def turn_arrow(color=(255, 236, 120, 255)):
    """当前回合指示箭头（朝下）。"""
    SS = 4
    s = MARK_SIZE * SS
    img = Image.new('RGBA', (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    p = [(s * 0.5, s * 0.86), (s * 0.14, s * 0.30), (s * 0.86, s * 0.30)]
    d.polygon(p, fill=color, outline=(40, 30, 0, 255))
    return img.resize((MARK_SIZE, MARK_SIZE), Image.LANCZOS)


def color_disc(color):
    """当前颜色圆盘。

    **不要再垫一圈白色底圆**：白圈在深色台面上就是玩家看到的「白色边边」。
    轮廓改用同色系更深的描边（只压暗，不加亮），在深色台面上依然立得住。
    """
    SS = 4
    s = DISC_SIZE * SS
    inset = SS                       # 留 1px 透明边，避免 mipmap 采样到相邻图块
    img = Image.new('RGBA', (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    box = [inset, inset, s - 1 - inset, s - 1 - inset]
    d.ellipse(box, fill=color)
    rim = tuple(max(0, int(c * 0.55)) for c in color[:3]) + (255,)
    d.ellipse(box, outline=rim, width=2 * SS)
    return img.resize((DISC_SIZE, DISC_SIZE), Image.LANCZOS)


def _dir_arrow_cw():
    """顺时针出牌方向箭头（未缩放的 SS 倍画布，返回居中裁剪前的 RGBA）。

    画法：一条约 180° 的圆弧 + 末端一个**沿切线方向**的等腰三角箭头。
    三角底边中点落在弧线末端、底边宽度约为弧线粗细的 2.3 倍，并沿切线回收一点，
    所以三角把弧线的平口端面整个盖住，两者严丝合缝、看不出接缝。
    箭头朝向 = 弧线角度增大的方向（屏幕上即顺时针）。

    形状先画在独立的 L 通道 mask 上、再配一层纯白 RGB——
    这样缩放时透明区也是白色，**不会在边缘混出深色描边**（黑底透明区会被重采样拉灰）。
    """
    SS = 4
    s = MARK_SIZE * SS
    mask = Image.new('L', (s, s), 0)
    d = ImageDraw.Draw(mask)
    cx = cy = s / 2.0
    R = s * 0.34                    # 弧线中线半径
    w = 6 * SS                      # 弧线粗细
    a0, a1 = 135.0, 345.0           # 起止角（PIL：0°=右，顺时针为正，y 轴向下）
    d.arc([cx - R, cy - R, cx + R, cy + R], start=a0, end=a1, fill=255, width=w)

    t = math.radians(a1)
    tx, ty = -math.sin(t), math.cos(t)      # 切线（角度增大方向）——箭头指向
    nx, ny = math.cos(t), math.sin(t)       # 径向——三角底边方向
    L, hw = 13 * SS, 5 * SS                 # 箭头长 / 底边半宽（底宽 ≈ 1.7 倍弧粗）
    bx = cx + R * math.cos(t) + tx * (hw * 0.35)
    by = cy + R * math.sin(t) + ty * (hw * 0.35)
    d.polygon([(bx + tx * L, by + ty * L),
               (bx + nx * hw, by + ny * hw),
               (bx - nx * hw, by - ny * hw)], fill=255)

    img = Image.new('RGBA', (s, s), (250, 250, 250, 0))
    img.putalpha(mask)
    return img


def dir_arrow(clockwise):
    """出牌方向箭头（顺时针 / 逆时针），64x64。

    逆时针版本直接水平镜像顺时针版本，保证两者严格对称。
    最后按不透明区裁剪、等比缩放并居中：两个方向的箭头大小、位置完全一致，
    也不会因为画布留白不同而看起来一高一低。
    边缘不描白边：标记立方体侧面走 {@link SWATCH_CLEAR}（全透明），
    否则薄薄的四面会变成一圈近白描边。
    """
    img = _dir_arrow_cw()
    if not clockwise:
        img = img.transpose(Image.FLIP_LEFT_RIGHT)
    img = img.crop(img.getchannel('A').getbbox())
    scale = (MARK_SIZE * 0.94) / max(img.size)
    img = img.resize((max(1, int(round(img.width * scale))),
                      max(1, int(round(img.height * scale)))), Image.LANCZOS)
    tile = Image.new('RGBA', (MARK_SIZE, MARK_SIZE), (250, 250, 250, 0))
    tile.paste(img, ((MARK_SIZE - img.width) // 2, (MARK_SIZE - img.height) // 2))
    return tile


def dealer_badge():
    SS = 4
    s = MARK_SIZE * SS
    img = Image.new('RGBA', (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.ellipse([1 * SS, 1 * SS, s - 1 * SS, s - 1 * SS], fill=(238, 214, 120, 255),
              outline=(120, 90, 20, 255), width=2 * SS)
    f = font(26 * SS)
    d.text((s * 0.5, s * 0.5), 'D', font=f, fill=(90, 60, 10, 255), anchor='mm')
    return img.resize((MARK_SIZE, MARK_SIZE), Image.LANCZOS)
