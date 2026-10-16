# -*- coding: utf-8 -*-
"""生成 uno_atlas.png（2048x2048）。"""
import os
import sys
from PIL import Image, ImageDraw

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import uno_assets as A

HERE = os.path.dirname(os.path.abspath(__file__))


def main():
    atlas = Image.new('RGBA', (A.ATLAS_W, A.ATLAS_H), (0, 0, 0, 0))

    # ---- A. 56 张牌面 ----
    # 用户 2026-10-15 三次迭代的最终口径：「牌面的那些白边……直接用那个牌边的颜色去填充，
    # 就是围在牌那一圈环的颜色」→「外围全部只用这一种颜色」→「这里还有一些其他的渐变红色，
    # 我要这些边缘都只用一种颜色」。`fill_paper_with_ring` 现在做两件事：
    #   ① 素材自带的白纸底（只在四角圆弧与 1px 外沿露出）填成**该牌外圈环的颜色**；
    #   ② 距纸底 9.5px 以内的**整圈卡框**（深描边 / 亮倒角 / 抗锯齿过渡）一并压平成同一个环色，
    #      只有背面牌内嵌的白框线这类"亮于环色 80+"的设计元素保留。
    # 每张牌在图集里还有一个 8x8 的环色块，供几何体的**四个侧面**取样（侧面同色，任何角度无白边）。
    deck = Image.open(A.DECK_SRC).convert('RGBA')
    for k in range(A.CARD_COUNT):
        tile = deck.crop(A.card_cell(k)).resize((A.CARD_W, A.CARD_H), Image.LANCZOS)
        tile, ring = A.fill_paper_with_ring(tile)
        atlas.paste(tile, A.face_tile(k), tile)
        blk = Image.new('RGBA', (A.CARD_SIDE_BLOCK, A.CARD_SIDE_BLOCK),
                        (ring + (255,)) if ring else A.PAPER)
        atlas.paste(blk, A.card_side_block(k))
    print('cards: %d（纸底+边缘带已压成牌环色 + 每牌环色侧面块）' % A.CARD_COUNT)

    # ---- B. 标记区 ----
    atlas.paste(A.turn_arrow(), A.TURN_ARROW, A.turn_arrow())
    for i, a in enumerate(A.COLOR_ORDER):
        atlas.paste(A.color_disc(A.UNO_COLORS[a]), A.COLOR_DISCS[i])
    atlas.paste(A.dir_arrow(True), A.DIR_ARROWS[0])
    atlas.paste(A.dir_arrow(False), A.DIR_ARROWS[1])
    atlas.paste(A.dealer_badge(), A.DEALER_BADGE)
    # 选中/悬停黑框（内部透明，露出下面卡面）
    atlas.paste(Image.new('RGBA', (A.CARD_W, A.CARD_H), (0, 0, 0, 0)), A.HILITE)
    atlas.paste(A.black_frame(), A.HILITE, A.black_frame())
    # 旧的「全局纸白侧面」取样点：卡片已改用各自的环色块（见上面 A 区），
    # 这个色块留着只为「万一要回退成白边」时 `_side_uv` 还能取到颜色。
    sw = Image.new('RGBA', (A.SWATCH_SIZE, A.SWATCH_SIZE), A.PAPER)
    atlas.paste(sw, A.SWATCH, sw)
    # 所有牌侧面共用的**纯白 (#ffffff) 长条**（2026-10-15 最终口径：亮牌侧面 = 纯白）。
    # 横向一条 64x8，mipmap 安全，四周留缝不与相邻贴图混色。
    white_bar = Image.new('RGBA', (A.CARD_SIDE_WHITE_W, A.CARD_SIDE_WHITE_H), (255, 255, 255, 255))
    atlas.paste(white_bar, A.CARD_SIDE_WHITE, white_bar)
    # 托管机器人贴图（斗地主插件那张 32x32 模型贴图，原样搬过来）
    robot = A.robot_src_tile()
    atlas.paste(robot, A.ROBOT_TEX, robot)
    print('marks: arrow/discs/dirs/badge/hilite/swatch/robot')

    # ---- C. 按钮 ----
    for a in A.ACTIONS:
        for state in ('normal', 'pressed'):
            t = A.sheet_button(a, state)
            atlas.paste(t, A.btn_tile(a, state), t)
    print('buttons: %d actions x2' % len(A.ACTIONS))

    os.makedirs(os.path.dirname(A.OUT_ATLAS), exist_ok=True)
    atlas.save(A.OUT_ATLAS)
    print('saved', A.OUT_ATLAS, atlas.size)

    # ---- 预览小图，便于肉眼核对 ----
    prev = atlas.resize((512, 512), Image.LANCZOS).convert('RGB')
    prev.save(os.path.join(HERE, '_atlas_preview.png'))


if __name__ == '__main__':
    main()
