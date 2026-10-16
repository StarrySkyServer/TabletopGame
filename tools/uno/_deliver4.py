# -*- coding: utf-8 -*-
"""本轮两项改动的交付核对图：
  ① _deliver_edge2.png —— 牌沿「一次颜色」：旧(插值/羽化) vs 新(整圈压平) 角部 10x 对照
  ② _deliver_laser2.png —— 定位器激光开关：蹲下 + 使用键 → 动作栏状态提示（机制示意）
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import uno_assets as A
from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
SZ = A.CARD_W, A.CARD_H
DECK = Image.open(A.DECK_SRC).convert('RGBA')


def old_fill(tile):
    """上一版（feather 版）的 fill，用于对照。"""
    w, h = tile.size
    out = tile.copy()
    px = out.load()
    mask = A.paper_mask(tile)
    ring = A.ring_color_of(tile, mask, 5)
    lr = A._lum(ring)
    for j in range(h):
        for i in range(w):
            if mask[j * w + i]:
                px[i, j] = (ring[0], ring[1], ring[2], 255)
    for j in range(h):
        for i in range(w):
            k = j * w + i
            if mask[k]:
                continue
            near = any(0 <= i + di < w and 0 <= j + dj < h and mask[(j + dj) * w + (i + di)]
                       for dj in range(-3, 4) for di in range(-3, 4))
            if not near:
                continue
            r, g, b, a = px[i, j]
            if a > 0 and A._lum((r, g, b)) > lr + 8:
                px[i, j] = (ring[0], ring[1], ring[2], a)
    return out


def cell_of(k):
    return DECK.crop(A.card_cell(k)).resize(SZ, Image.LANCZOS)


def corner_pair(k, box=26, z=10):
    old = old_fill(cell_of(k))
    new, ring = A.fill_paper_with_ring(cell_of(k))
    w = box * z
    img = Image.new('RGB', (w * 2 + 10, w), (16, 18, 24))
    for idx, im in enumerate((old, new)):
        c = im.convert('RGB').crop((0, 0, box, box)).resize((w, w), Image.NEAREST)
        img.paste(c, (idx * (w + 10), 0))
    return img, ring, new


def deliver_edge():
    ks = [(0, '红'), (13, '黄'), (54, '牌背')]
    pairs = [corner_pair(k) for k, _ in ks]
    pw = pairs[0][0].width      # 一对（旧+新）的宽度
    th = pairs[0][0].height     # 一对的高度
    f, fs = A.font(24), A.font(17)
    W = pw * 3 + 20 * 2 + 40
    H = 84 + th + 96
    img = Image.new('RGB', (W, H), (16, 18, 24))
    d = ImageDraw.Draw(img)
    d.text((20, 12), '牌沿「这些边缘都只用一种颜色」—— 整圈压平成牌环色', font=f, fill=(255, 220, 120))
    d.text((20, 46),
           '旧：只处理纸底 + 外沿 3px（框自身的深描边/亮倒角/过渡色都还在，角上是好几道红）    '
           '新：距纸底 9.5px 的整圈一律刷成环色（背面牌的白框线属于设计元素，保留）',
           font=fs, fill=(214, 220, 230))
    for i, ((k, tag), (pair, ring, new)) in enumerate(zip(ks, pairs)):
        x = 20 + i * (pw + 20)
        img.paste(pair, (x, 84))
        d.text((x + pw // 4, 84 + th + 4), '旧', font=fs, fill=(200, 206, 218))
        d.text((x + pw // 4 * 3, 84 + th + 4), '新', font=fs, fill=(140, 235, 160))
        d.text((x + 4, 84 + th + 30), 'tile %d（%s）  环色 %s' % (k, tag, ring), font=fs,
               fill=(190, 198, 210))
    # 左缘像素实测（新）
    new0 = pairs[0][2]
    seq = [new0.getpixel((x, SZ[1] // 2)) for x in range(10)]
    d.text((20, 84 + th + 58),
           '红牌左缘 x=0..9 实测：%s —— 10 个像素同一个色（旧版这里是 深描边→环→亮倒角→过渡 四层）'
           % (' '.join('%02X%02X%02X' % c[:3] for c in seq)),
           font=fs, fill=(255, 226, 150))
    img.save(os.path.join(HERE, '_deliver_edge2.png'))
    print('saved _deliver_edge2.png', img.size)


def deliver_laser():
    f, fs, fss = A.font(26), A.font(19), A.font(16)
    W, H = 1180, 560
    img = Image.new('RGB', (W, H), (16, 18, 24))
    d = ImageDraw.Draw(img)
    d.text((24, 16), '定位器激光开关：蹲下 + 使用键 → 只要没点到牌/按钮，就切换激光开关（动作栏提示）',
           font=f, fill=(255, 220, 120))

    # 流程块
    def box(x, y, w, h, title, lines, accent):
        d.rounded_rectangle([x, y, x + w, y + h], radius=10, outline=accent, width=2,
                            fill=(26, 30, 40))
        d.text((x + 14, y + 10), title, font=fs, fill=accent)
        yy = y + 40
        for t in lines:
            d.text((x + 14, yy), t, font=fss, fill=(216, 222, 232))
            yy += 26

    box(24, 70, 300, 210, '① 蹲下 + 右键使用', [
        '· 手持「定位器」时按下潜行',
        '· 点「使用」键（准星指哪儿都行）',
        '· 客户端一定把「使用物品」',
        '  事务发到服务端（不依赖方块）',
    ], (120, 200, 255))
    box(360, 70, 330, 210, '② 判定：是否点到棋盘元素', [
        '· 服务端对着桌子做射线判定',
        '· 点到手牌 / 按钮 → 出牌逻辑优先，',
        '  开关不生效（和平时一样玩）',
        '· 什么都没点到 → 切激光开关',
        '· 蹲下时点桌子不会弹菜单',
    ], (255, 208, 110))
    box(726, 70, 424, 210, '③ 动作栏提示（sendTip）', [
        '开启：「定位器激光 | 已开启」（绿）',
        '关闭：「定位器激光 | 已关闭」（灰）',
        '',
        '· 0.5 秒防抖：触屏按住「使用」键',
        '  不会来回翻转',
    ], (140, 235, 170))

    # 动作栏 mock
    y = 320
    d.text((24, y - 26), '屏幕下方实际效果（动作栏 = 物品栏上方那条字）', font=fs, fill=(200, 208, 220))
    bar = Image.new('RGB', (560, 66), (12, 14, 18))
    bd = ImageDraw.Draw(bar)
    bd.rounded_rectangle([0, 0, 559, 65], radius=10, outline=(70, 76, 90), width=2,
                         fill=(12, 14, 18))
    bd.text((22, 8), '定位器激光 | 已开启', font=A.font(24), fill=(120, 235, 150))
    bd.text((22, 38), '定位器激光 | 已关闭', font=A.font(24), fill=(150, 150, 158))
    img.paste(bar, (24, y))
    cnt = Image.new('RGB', (520, 66), (12, 14, 18))
    cd = ImageDraw.Draw(cnt)
    cd.rounded_rectangle([0, 0, 519, 65], radius=10, outline=(70, 76, 90), width=2,
                         fill=(12, 14, 18))
    cd.text((22, 6), '绿色光点也跟着开关走：', font=fss, fill=(216, 222, 232))
    cd.text((22, 30), '关掉后，瞄牌不再冒绿点；再开一下才回来（默认开）', font=fss,
            fill=(150, 156, 168))
    img.paste(cnt, (24 + 580, y))

    d.text((24, 512), '说明：开关是「每个人自己」的状态；重连后回到默认「开启」。', font=fss,
           fill=(140, 146, 158))
    img.save(os.path.join(HERE, '_deliver_laser2.png'))
    print('saved _deliver_laser2.png', img.size)


if __name__ == '__main__':
    deliver_edge()
    deliver_laser()
