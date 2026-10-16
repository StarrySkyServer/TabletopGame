# -*- coding: utf-8 -*-
"""从斗地主插件图集里裁出「托管机器人」贴图区，放大预览。"""
from PIL import Image

SRC = ('D:/CodeProject/Gobang/斗地主/Doudizhu/src/main/resources/'
       'assets/resource_pack/textures/ddz/table_atlas.png')
im = Image.open(SRC).convert('RGBA')
print('atlas', im.size)
box = (1450, 0, 1495, 34)
c = im.crop(box)
c.resize((c.width * 12, c.height * 12), Image.NEAREST).save(
    'D:/CodeProject/Gobang/TabletopGamePlugin/tools/uno/_ddz_robot_tex.png')
for name, b in [('a', (1924, 1900, 1928, 1904)), ('b', (1956, 1900, 1960, 1904))]:
    t = im.crop(b).resize((4 * 24, 4 * 24), Image.NEAREST)
    t.save('D:/CodeProject/Gobang/TabletopGamePlugin/tools/uno/_ddz_ico_%s.png' % name)
print('ok')
