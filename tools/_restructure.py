#!/usr/bin/env python3
"""一次性重构（可重复执行，幂等）：
1. 顶层包 top.tabletopgame -> com.tabletopgame（反向域名）
2. 横切按职责：uno/ 竖切包拆入 ai/board/entity/game/item/ui；xiangqi/ 引擎归入 ai/xiangqi
用法：python tools/_restructure.py
"""
import os, io, shutil

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASE = os.path.join(ROOT, 'src', 'main', 'java')

# ---------------------------------------------------------------------------
# 包名映射（点号版）。按长度降序应用，避免前缀误匹配。
# ---------------------------------------------------------------------------
PKG_MAP = [
    ('top.tabletopgame.xiangqi.pengjiu.searchengine', 'com.tabletopgame.ai.xiangqi.pengjiu.searchengine'),
    ('top.tabletopgame.xiangqi.pengjiu.zobrist',      'com.tabletopgame.ai.xiangqi.pengjiu.zobrist'),
    ('top.tabletopgame.xiangqi.pengjiu.chessparam',   'com.tabletopgame.ai.xiangqi.pengjiu.chessparam'),
    ('top.tabletopgame.xiangqi.pengjiu.chessmove',    'com.tabletopgame.ai.xiangqi.pengjiu.chessmove'),
    ('top.tabletopgame.xiangqi.pengjiu.evaluate',     'com.tabletopgame.ai.xiangqi.pengjiu.evaluate'),
    ('top.tabletopgame.xiangqi.pengjiu.history',      'com.tabletopgame.ai.xiangqi.pengjiu.history'),
    ('top.tabletopgame.xiangqi.pengjiu.movelist',     'com.tabletopgame.ai.xiangqi.pengjiu.movelist'),
    ('top.tabletopgame.xiangqi.pengjiu',              'com.tabletopgame.ai.xiangqi.pengjiu'),
    ('top.tabletopgame.xiangqi.engine',               'com.tabletopgame.ai.xiangqi'),
    ('top.tabletopgame.uno.entity',                   'com.tabletopgame.entity'),
    ('top.tabletopgame.uno.game',                     'com.tabletopgame.game'),
    ('top.tabletopgame.uno.item',                     'com.tabletopgame.item'),
    ('top.tabletopgame.uno.block',                    'com.tabletopgame.board'),
    ('top.tabletopgame.uno.ui',                       'com.tabletopgame.ui'),
    ('top.tabletopgame.uno.ai',                       'com.tabletopgame.ai'),
    ('top.tabletopgame.storage',                      'com.tabletopgame.storage'),
    ('top.tabletopgame.economy',                      'com.tabletopgame.economy'),
    ('top.tabletopgame.config',                       'com.tabletopgame.config'),
    ('top.tabletopgame.entity',                       'com.tabletopgame.entity'),
    ('top.tabletopgame.board',                        'com.tabletopgame.board'),
    ('top.tabletopgame.game',                         'com.tabletopgame.game'),
    ('top.tabletopgame.item',                         'com.tabletopgame.item'),
    ('top.tabletopgame.ui',                           'com.tabletopgame.ui'),
    ('top.tabletopgame.ai',                           'com.tabletopgame.ai'),
    ('top.tabletopgame',                              'com.tabletopgame'),
]
PKG_MAP.sort(key=lambda kv: -len(kv[0]))  # 长度降序（兜底裸包名最后）

# 路径版映射（斜杠），供 .py 脚本里的硬编码路径替换
PATH_MAP = [(o.replace('.', '/'), n.replace('.', '/')) for o, n in PKG_MAP]
PATH_MAP.sort(key=lambda kv: -len(kv[0]))


def replace_pkgs(text):
    for o, n in PKG_MAP:
        text = text.replace(o, n)
    return text


def replace_paths(text):
    for o, n in PATH_MAP:
        text = text.replace(o, n)
    return text


def log(msg):
    print(msg)


# ---------------------------------------------------------------------------
# 1. 备份 src/main/java（防误操作，可整体回滚）
# ---------------------------------------------------------------------------
bak = os.path.join(ROOT, '_restructure_backup_java')
if os.path.exists(bak):
    shutil.rmtree(bak)
shutil.copytree(BASE, bak)
log('已备份源码 -> _restructure_backup_java')

# ---------------------------------------------------------------------------
# 2. 移动顶层目录 top/tabletopgame -> com/tabletopgame
# ---------------------------------------------------------------------------
src_top = os.path.join(BASE, 'top', 'tabletopgame')
dst_top = os.path.join(BASE, 'com', 'tabletopgame')
if os.path.exists(src_top):
    os.makedirs(os.path.join(BASE, 'com'), exist_ok=True)
    if os.path.exists(dst_top):
        shutil.rmtree(dst_top)
    shutil.move(src_top, dst_top)
    log('顶层目录已移动: top/tabletopgame -> com/tabletopgame')
else:
    log('（跳过顶层移动：top/tabletopgame 不存在，可能已重构）')

# ---------------------------------------------------------------------------
# 3. uno/ 竖切分发到横切包
# ---------------------------------------------------------------------------
UNO_MOVES = [
    ('uno/ai/UnoAi.java',                      'ai/UnoAi.java'),
    ('uno/block/UnoTableBlocks.java',          'board/UnoTableBlocks.java'),
    ('uno/entity/UnoClickBoxEntity.java',      'entity/UnoClickBoxEntity.java'),
    ('uno/entity/UnoTableEntity.java',         'entity/UnoTableEntity.java'),
    ('uno/game/UnoDeck.java',                  'game/UnoDeck.java'),
    ('uno/game/UnoGame.java',                  'game/UnoGame.java'),
    ('uno/game/UnoManager.java',               'game/UnoManager.java'),
    ('uno/game/UnoTable.java',                 'game/UnoTable.java'),
    ('uno/game/UnoTableRay.java',              'game/UnoTableRay.java'),
    ('uno/item/LocatorItem.java',              'item/LocatorItem.java'),
    ('uno/item/UnoTableItem.java',             'item/UnoTableItem.java'),
    ('uno/item/UnoTableRecipe.java',           'item/UnoTableRecipe.java'),
    ('uno/ui/UnoMenu.java',                    'ui/UnoMenu.java'),
]
for rel, dst_rel in UNO_MOVES:
    s = os.path.join(dst_top, rel)
    d = os.path.join(dst_top, dst_rel)
    if os.path.exists(s):
        os.makedirs(os.path.dirname(d), exist_ok=True)
        shutil.move(s, d)
        log('uno 分发: %s -> %s' % (rel, dst_rel))

# ---------------------------------------------------------------------------
# 4. xiangqi/ 引擎归入 ai/xiangqi
# ---------------------------------------------------------------------------
for f in ('Position.java', 'Search.java', 'Util.java'):
    s = os.path.join(dst_top, 'xiangqi', 'engine', f)
    d = os.path.join(dst_top, 'ai', 'xiangqi', f)
    if os.path.exists(s):
        os.makedirs(os.path.dirname(d), exist_ok=True)
        shutil.move(s, d)
        log('xqwlight 引擎: xiangqi/engine/%s -> ai/xiangqi/%s' % (f, f))

peng_src = os.path.join(dst_top, 'xiangqi', 'pengjiu')
peng_dst = os.path.join(dst_top, 'ai', 'xiangqi', 'pengjiu')
if os.path.exists(peng_src):
    os.makedirs(os.path.dirname(peng_dst), exist_ok=True)
    if os.path.exists(peng_dst):
        shutil.rmtree(peng_dst)
    shutil.move(peng_src, peng_dst)
    log('pengjiu 引擎: xiangqi/pengjiu -> ai/xiangqi/pengjiu')

# 清理空目录 uno/ xiangqi/
for empty in ('uno', 'xiangqi'):
    p = os.path.join(dst_top, empty)
    if os.path.isdir(p) and not os.listdir(p):
        shutil.rmtree(p)
        log('清理空目录: %s/' % empty)

# ---------------------------------------------------------------------------
# 5. 替换所有 .java 文件的 package/import（src + tools 离线工具）
# ---------------------------------------------------------------------------
java_files = []
for dp, dn, fn in os.walk(os.path.join(BASE, 'com')):
    for f in fn:
        if f.endswith('.java'):
            java_files.append(os.path.join(dp, f))
# tools/uno 下的离线校验/模拟 Java
tools_java_dir = os.path.join(ROOT, 'tools', 'uno')
if os.path.isdir(tools_java_dir):
    java_files += [os.path.join(tools_java_dir, f) for f in os.listdir(tools_java_dir) if f.endswith('.java')]

for p in java_files:
    with io.open(p, encoding='utf-8') as fh:
        txt = fh.read()
    new = replace_pkgs(txt)
    if new != txt:
        with io.open(p, 'w', encoding='utf-8', newline='') as fh:
            fh.write(new)

log('已替换 %d 个 Java 文件的 package/import' % len(java_files))

# ---------------------------------------------------------------------------
# 6. plugin.yml / pom.xml
# ---------------------------------------------------------------------------
yml = os.path.join(ROOT, 'src', 'main', 'resources', 'plugin.yml')
with io.open(yml, encoding='utf-8') as fh:
    t = fh.read()
with io.open(yml, 'w', encoding='utf-8', newline='') as fh:
    fh.write(replace_pkgs(t))
log('plugin.yml 已替换')

pom = os.path.join(ROOT, 'pom.xml')
with io.open(pom, encoding='utf-8') as fh:
    t = fh.read()
with io.open(pom, 'w', encoding='utf-8', newline='') as fh:
    fh.write(replace_pkgs(t))
log('pom.xml 已替换（groupId + 注释）')

# ---------------------------------------------------------------------------
# 7. tools/uno 下的 .py 校验脚本（硬编码路径 + 可能的包名注释）
# ---------------------------------------------------------------------------
for py in ('verify_props.py', 'verify_ray.py', '_dupblock.py', '_grid_check.py'):
    p = os.path.join(tools_java_dir, py)
    if os.path.isfile(p):
        with io.open(p, encoding='utf-8') as fh:
            t = fh.read()
        new = replace_paths(replace_pkgs(t))
        if new != t:
            with io.open(p, 'w', encoding='utf-8', newline='') as fh:
                fh.write(new)
            log('校验脚本已替换: tools/uno/%s' % py)

log('完成。')
