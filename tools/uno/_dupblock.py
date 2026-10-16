# -*- coding: utf-8 -*-
"""临时脚本：查找 Java 源码里连续重复的行块（"同一段改动被应用两次"的典型特征）。"""
import io
import os

FILES = [
    'src/main/java/com/tabletopgame/game/UnoTable.java',
    'src/main/java/com/tabletopgame/game/UnoManager.java',
    'src/main/java/com/tabletopgame/entity/UnoTableEntity.java',
    'src/main/java/com/tabletopgame/entity/UnoClickBoxEntity.java',
    'src/main/java/com/tabletopgame/TabletopGamePlugin.java',
]


def dup_blocks(path):
    lines = [l.rstrip() for l in io.open(path, encoding='utf-8').read().split('\n')]
    hits, i = [], 0
    while i < len(lines):
        for n in (4, 3, 2):
            if i + 2 * n <= len(lines):
                a = lines[i:i + n]
                b = lines[i + n:i + 2 * n]
                if a == b and any(x.strip() for x in a):
                    hits.append((i + 1, n, a[0].strip()[:80]))
                    i += 2 * n
                    break
        i += 1
    return hits


total = 0
for p in FILES:
    if not os.path.exists(p):
        continue
    h = dup_blocks(p)
    total += len(h)
    print('==', p, '重复行块:', len(h))
    for x in h[:10]:
        print('   line %d x%d: %s' % x)
print('total', total)
