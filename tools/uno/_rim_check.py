# -*- coding: utf-8 -*-
"""临时脚本：核对「牌沿只剩一种颜色」——统计纸底外圈还有多少"比环色亮"的像素。"""
import os
import sys

from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import uno_assets as A

HERE = os.path.dirname(os.path.abspath(__file__))


def lum(c):
    return 0.299 * c[0] + 0.587 * c[1] + 0.114 * c[2]


def main():
    deck = Image.open(A.DECK_SRC).convert('RGBA')
    worst = []
    for k in range(A.CARD_COUNT):
        cell = deck.crop(A.card_cell(k)).resize((A.CARD_W, A.CARD_H), Image.LANCZOS)
        tile, ring = A.fill_paper_with_ring(cell)
        mask = A.paper_mask(cell)
        w, h = tile.size
        px = tile.load()
        lr = lum(ring)
        bad = 0
        for j in range(h):
            for i in range(w):
                if mask[j * w + i]:
                    continue
                near = False
                for dj in range(-2, 3):
                    for di in range(-2, 3):
                        ni, nj = i + di, j + dj
                        if 0 <= ni < w and 0 <= nj < h and mask[nj * w + ni]:
                            near = True
                            break
                    if near:
                        break
                if not near:
                    continue
                c = px[i, j]
                if c[3] > 0 and lum(c) > lr + 12:
                    bad += 1
            worst.append((bad, k, ring))
    worst.sort(reverse=True)
    print('纸底外 2px 内"比环色亮"的像素数（应为 0）:')
    for bad, k, ring in worst[:8]:
        print('   tile %2d  bad=%d  ring=%s' % (k, bad, ring))
    print('总计 bad =', sum(w[0] for w in worst))


if __name__ == '__main__':
    main()
