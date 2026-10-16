# -*- coding: utf-8 -*-
"""把斗地主 3x3 物理牌桌方块资源移植为 UNO 版本。

只做两件事：
  1) 9 个 geo.json —— 把 geometry.ddz.physical_table_* 改名为
     geometry.tabletopgame.uno_physical_table_*（几何体内容一字不改，
     沿用「方块几何体 X 预镜像」这条已被验证过的约定）。
  2) 2 张贴图 —— physical_table_block.png / physical_table_item.png 复制到
     textures/tabletopgame/uno/ 下。

输出 JSON 保持压缩（无多余空白），与原文件字节风格一致。
"""
import json
import os
import shutil

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, '..', '..'))
DDZ_RP = 'D:/CodeProject/Gobang/斗地主/Doudizhu/src/main/resources/assets/resource_pack'
RP = os.path.join(REPO, 'src', 'main', 'resources', 'assets', 'resource_pack')

SRC_MODELS = os.path.join(DDZ_RP, 'models', 'blocks')
DST_MODELS = os.path.join(RP, 'models', 'blocks', 'uno')
SRC_TEX = os.path.join(DDZ_RP, 'textures', 'ddz')
DST_TEX = os.path.join(RP, 'textures', 'tabletopgame', 'uno')

OLD_PREFIX = 'geometry.ddz.physical_table_'
NEW_PREFIX = 'geometry.tabletopgame.uno_physical_table_'


def main():
    os.makedirs(DST_MODELS, exist_ok=True)
    os.makedirs(DST_TEX, exist_ok=True)

    names = sorted(n for n in os.listdir(SRC_MODELS)
                   if n.startswith('ddz_physical_table_') and n.endswith('.geo.json'))
    written = 0
    for name in names:
        with open(os.path.join(SRC_MODELS, name), 'r', encoding='utf-8') as fh:
            raw = fh.read()
        if OLD_PREFIX not in raw:
            raise SystemExit('未找到旧 identifier：' + name)
        raw = raw.replace(OLD_PREFIX, NEW_PREFIX)
        # 校验仍是合法 JSON
        json.loads(raw)
        out_name = name.replace('ddz_physical_table_', 'uno_physical_table_')
        with open(os.path.join(DST_MODELS, out_name), 'w', encoding='utf-8', newline='') as fh:
            fh.write(raw)
        written += 1
        print('geo  ->', out_name)

    for tex in ('physical_table_block.png', 'physical_table_item.png'):
        shutil.copyfile(os.path.join(SRC_TEX, tex), os.path.join(DST_TEX, tex))
        print('tex  ->', tex)

    print('done: %d geo, 2 textures' % written)


if __name__ == '__main__':
    main()
