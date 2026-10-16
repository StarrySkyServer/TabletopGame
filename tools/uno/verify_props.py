# -*- coding: utf-8 -*-
"""契约校验：Java 侧（实体属性 / 按钮码）↔ 客户端 pre_animation ↔ 资源生成器。

这是本项目最容易出错、也最难在真机上定位的一类问题：Java 写属性、资源包读属性，
两边各写一遍编码规则，任何一侧改了位宽/基准/顺序，服务端不会报错，只是「牌不见 / 按钮点不动」。
本脚本把三处常量抽出来做等值断言，改坏了立刻红。

用法：python verify_props.py
"""
import io
import os
import re
import sys

from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import uno_assets as A
import render_base as R
import build_table as T

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.normpath(os.path.join(HERE, '..', '..'))
ENTITY_JAVA = os.path.join(REPO, 'src/main/java/com/tabletopgame/entity/UnoTableEntity.java')
ENT_JSON = os.path.join(R.RP, 'entity/uno/uno_table.entity.json')

problems = []
notes = []


def fail(msg):
    problems.append(msg)


def ok(cond, msg):
    if not cond:
        fail(msg)
    return cond


# ------------------------------------------------------------------ 客户端
with io.open(ENT_JSON, encoding='utf-8') as fh:
    import json
    DOC = json.load(fh)
DESC = DOC['minecraft:client_entity']['description']
PA = '\n'.join(DESC['scripts']['pre_animation'])
ANIM_JSON = os.path.join(R.RP, 'animations/uno/uno_table.animation.json')
with io.open(ANIM_JSON, encoding='utf-8') as fh:
    ANIM = json.load(fh)
# 动画里也会直接引用 v.pk_* 表达式，一并纳入读取集合
ANIM_TEXT = json.dumps(ANIM, ensure_ascii=False)

CLIENT_PROPS = set(re.findall(r"q\.property\('([^']+)'\)", PA))
ANIM_PROPS = set(re.findall(r"q\.property\('([^']+)'\)", ANIM_TEXT))

# ---- Java 侧
with io.open(ENTITY_JAVA, encoding='utf-8') as fh:
    JAVA = fh.read()

# Java 用常量名而不是字面量注册属性（P_SEL / VIEWER_PACKED_MAX / TABLE_MAX ...），
# 这里先把这层符号解析掉，才能真正比对数值区间。
STRS = dict(re.findall(r'public static final String ([A-Z_0-9]+) = "([^"]+)";', JAVA))
_RAW_INTS = dict(re.findall(r'public static final int ([A-Z_0-9]+) = ([^;]+);', JAVA))
_INTS = {}


def resolve_int(expr):
    e = expr.strip()
    if re.fullmatch(r'-?\d+', e):
        return int(e)
    if e in _INTS:
        return _INTS[e]
    if e in _RAW_INTS:
        e = _RAW_INTS[e]

    def sub(mo):
        n = mo.group(0)
        if n in _INT_NAMES:
            return str(resolve_int(_RAW_INTS[n]))
        if n in _STR_NAMES:
            return '0'
        return n

    body = re.sub(r'[A-Za-z_][A-Za-z0-9_]*', sub, e).replace('/', '//')
    try:
        return int(eval(body, {'__builtins__': {}}, {}))
    except Exception:                            # noqa: BLE001
        fail('无法解析 Java 整型常量：%s = %s' % (expr, body))
        return -1


_INT_NAMES = set(_RAW_INTS)
_STR_NAMES = set(STRS)
for _k in _INT_NAMES:
    _INTS[_k] = resolve_int(_k)


def resolve_name(tok):
    t = tok.strip()
    if t.startswith('"'):
        return t.strip('"')
    if t in STRS:
        return STRS[t]
    return None


REG = {}
for raw_name, raw_hi in re.findall(
        r'new IntEntityProperty\(\s*([^,]+?)\s*,\s*[^,]+?,\s*([^,]+?),\s*[^)]*\)', JAVA):
    nm = resolve_name(raw_name)
    if nm is None:
        continue                                  # cardsName(i) 单独处理
    REG[nm] = (0, resolve_int(raw_hi))
cards_props = set('tabletopgame:uno_cards_%d' % i for i in range(16))
if 'cardsName(i), 0, 2097151' in JAVA:
    for p in cards_props:
        REG[p] = (0, 2097151)
else:
    fail('Java 未注册 cards 属性（期望 0..2097151）')

JAVA_PROPS = set(REG.keys())

# ------------------------------------------------------------------ 1. 属性集合一致
missing = CLIENT_PROPS - JAVA_PROPS
extra = JAVA_PROPS - CLIENT_PROPS
ok(not missing, '客户端读了但 Java 没注册的属性：%s' % sorted(missing))
ok(not extra, 'Java 注册了但客户端从不读的属性：%s' % sorted(extra))
ok(not ANIM_PROPS, '动画里出现裸 q.property 引用（应统一走 pre_animation 变量）：%s' % sorted(ANIM_PROPS))

# ------------------------------------------------------------------ 2. cards 位宽
zlines = re.findall(r"v\.z(\d+)=math\.mod\(math\.floor\(v\.pk_c(\d+)/(\d+)\),8\)", PA)
ok(len(zlines) == 108, 'pre_animation 里 z 解码条数应为 108，实际 %d' % len(zlines))
for n, prop, div in zlines:
    n, prop, div = int(n), int(prop), int(div)
    ok(prop == n // 7, 'z%d 取自 pk_c%d（应为 %d）' % (n, prop, n // 7))
    ok(div == 8 ** (n % 7), 'z%d 除数 %d（应为 %d）' % (n, div, 8 ** (n % 7)))
ok(REG.get('tabletopgame:uno_cards_0') == (0, 2097151),
   'uno_cards_* 的区间应为 0..2097151（7 槽 × 3 bit）')

# ------------------------------------------------------------------ 3. hover / sel：每 viewer 7 bit，base 128
for label, var, prop in (('hover', 'HV', T.P_IF_HOVER if hasattr(T, 'P_IF_HOVER') else 'uno_hover'),
                         ('sel', 'SV', 'uno_sel')):
    expr = T.HV if label == 'hover' else T.SV
    divs = [int(x) for x in re.findall(r'/(\d+)\)', expr)]
    ok(divs == [128, 16384, 2097152],
       '%s 的 4 个 viewer 除数应为 [128, 16384, 2097152]（7 bit/viewer），实际 %s' % (label, divs))
    ok('math.mod(v.pk_%s,128)' % ('hover' if label == 'hover' else 'sel') in expr,
       '%s 的第 0 个 viewer 应从 pk_%s 取模 128' % (label, prop))
ok(REG.get('tabletopgame:uno_hover') == (0, 268435455),
   'uno_hover 区间应为 0..268435455（4 × 7 bit）')
ok(REG.get('tabletopgame:uno_sel') == (0, 268435455),
   'uno_sel 区间应为 0..268435455（4 × 7 bit）')

# ------------------------------------------------------------------ 4. hover 取值空间不重叠
CARD_BASE = T.HOVER_CARD_BASE
BTN_BASE = T.HOVER_BTN_BASE
ok(CARD_BASE == 1, 'HOVER_CARD_BASE 应为 1（值 = slot+1，与 highlight_N 对齐）')
card_hi = CARD_BASE + 107
btn_hi = BTN_BASE + 3
ok(card_hi < BTN_BASE, '手牌准星上限 %d 必须 < 按钮基准 %d（否则按钮与手牌撞值）' % (card_hi, BTN_BASE))
ok(btn_hi <= T.HOVER_MAX, '按钮准星上限 %d 超过 %d 位可表示范围 %d' % (btn_hi, T.HOVER_BITS, T.HOVER_MAX))
ok(card_hi <= T.HOVER_MAX, '手牌准星上限 %d 超过 %d 位范围' % (card_hi, T.HOVER_BITS))
ok(('v.hv=%s;' % T.HV) in PA, 'pre_animation 未解码 v.hv')
ok(('v.sv=%s;' % T.SV) in PA, 'pre_animation 未解码 v.sv')

# 高亮骨骼同时响应 hover 与 sel
LB = ANIM['animations']['animation.tabletopgame.uno.layout']['bones']
hl = [b for b in LB if b.startswith('highlight_')]
ok(len(hl) == 108, '高亮骨骼应为 108 根，实际 %d' % len(hl))
ok(all(T.HV in LB[b]['scale'] and T.SV in LB[b]['scale'] for b in hl),
   '高亮骨骼必须同时响应 v.hv（悬停）与 v.sv（选中）')
ok(any(T.SV in v['scale'] for k, v in LB.items() if isinstance(v, dict) and 'scale' in v),
   '动画没有任何骨骼使用选中值（选中就没有视觉反馈）')

# ------------------------------------------------------------------ 5. table 位域
for div, name, want_bit in ((512, 'acolor', 9), (2048, 'dir', 11)):
    ok('/%d)' % div in PA, 'pre_animation 未按 /%d 解码 %s' % (div, name))
ok(REG.get('tabletopgame:uno_table') == (0, 65535),
   'uno_table 区间应为 0..65535（16 位：位 12..14 = 弃牌堆顶的出牌座位，位 15 = 定庄展示态）')
ok(('v.btn_owner=math.mod(math.floor(v.pk_table/64),8);') in PA, '按钮归属未按 bits6-8 解码')
ok(('v.dealer=math.mod(v.pk_table,8);') in PA, '庄家未按 bits0-2 解码')
ok(('v.actor=math.mod(math.floor(v.pk_table/8),8);') in PA, '行动方未按 bits3-5 解码')
ok(("v.show_all=math.mod(math.floor(v.pk_table/32768),2);") in PA,
   'pre_animation 未按 bit15 解码定庄展示态 v.show_all')

# ------------------------------------------------------------------ 6. controls 位宽
ok('/4096)' in PA, 'pre_animation 未按 /4096 解码第 4 个按钮槽')
ok(REG.get('tabletopgame:uno_controls') == (0, 65535),
   'uno_controls 区间应为 0..65535（4 × 4 bit）')

# ------------------------------------------------------------------ 7. pile
ok('v.pile_n=math.min(v.pk_pile,5);' in PA, 'pre_animation 未把 pk_pile 钳到 5')
ok(REG.get('tabletopgame:uno_pile') == (0, 255), 'uno_pile 区间应为 0..255')
ok(REG.get('tabletopgame:uno_deal') == (0, 255),
   'uno_deal 区间应为 0..255（逐张发牌进度；255 = 全部可见）')

# ------------------------------------------------------------------ 7.1 托管座位（uno_seats）
# 每座 2 位：0 正常 / 1 托管 / 2 离线托管，控制 bot_N 骨骼显隐。
ok(REG.get('tabletopgame:uno_seats') == (0, 255),
   'uno_seats 区间应为 0..255（4 座 × 2 bit）')
ok("v.seats=q.property('tabletopgame:uno_seats');" in PA,
   'pre_animation 未解码 v.seats（托管机器人不会显示）')
GEO_JSON = os.path.join(R.RP, 'models/entity/uno/uno_table.geo.json')
with io.open(GEO_JSON, encoding='utf-8') as fh:
    BONE_MAP = {b['name']: b for b in json.load(fh)['minecraft:geometry'][0]['bones']}
for _s in range(4):
    _b = 'bot_%d' % _s
    _h = 'bot_head_%d' % _s
    ok(_b in LB, '布局动画缺少 %s 骨骼（托管机器人画不出来）' % _b)
    if _b in LB:
        ok('v.seats' in LB[_b]['scale'],
           '%s 的显隐必须由 v.seats 驱动，实际 %s' % (_b, LB[_b]['scale']))
        ok('/%d)' % (4 ** _s) in LB[_b]['scale'] or 'v.seats' in LB[_b]['scale'],
           '%s 未按第 %d 座取位（4^%d）' % (_b, _s, _s))
    ok(_b in BONE_MAP and BONE_MAP[_b].get('cubes'),
       '几何体缺少 %s 的立方体' % _b)
    ok(BONE_MAP.get(_h, {}).get('parent') == _b,
       '%s 必须挂在 %s 下' % (_h, _b))

# ------------------------------------------------------------------ 7.2 出牌飞行（uno_fly）
# 服务端只翻 bit1 表示"新的一次飞行"；客户端在 pre_animation 里算飞行位姿，layout 的
# card_N 在 v.fgo==1 且本卡在弃牌区时直接吃 v.fx/fy/fz/frx。整条链缺一环 = 牌不飞或飞歪。
ok(REG.get('tabletopgame:uno_fly') == (0, 3),
   'uno_fly 区间应为 0..3（bit0 = 来源 手牌/牌堆，bit1 = 翻转位）')
ok("v.pk_fly=q.property('tabletopgame:uno_fly');" in PA,
   'pre_animation 未读取 uno_fly（出牌飞行动画不会触发）')
ok('v.fnew=' in PA and 'v.fprev' in PA,
   'pre_animation 未做"值变化"检测（v.fnew/v.fprev）：连续出牌时第二张不会飞')
ok('v.ft=v.fnew?0:math.min(1,v.ft+q.delta_time/' in PA,
   'pre_animation 未用 q.delta_time 推进飞行进度（斗地主的选择弹跳也是这么做的）')
ok('math.sin(180*v.ft)' in PA,
   '飞行弧线未用 Molang 角度制（math.sin 吃角度，写 3.14159*v.ft 会得到一条直线）')
ok('v.fgo=' in PA, 'pre_animation 未算出"正在飞"标志 v.fgo')
ok('v.frx=' in PA, 'pre_animation 未算出飞行姿态 v.frx')
for _ch in ('fx', 'fy', 'fz'):
    ok(('v.%s=' % _ch) in PA, 'pre_animation 未算出飞行位置 v.%s' % _ch)
ok('v.fgo==1' in LB['card_0']['position'][0],
   'card_N 的位置没接飞行变量（出牌时牌不会从手牌飞出来）')
ok('v.frx' in LB['card_0']['rotation'][0],
   'card_N 的朝向没接飞行变量（牌不会边飞边放平）')
_INIT = json.load(io.open(os.path.join(R.RP, 'entity/uno/uno_table.entity.json'),
                          encoding='utf-8'))['minecraft:client_entity']['description'] \
    ['scripts']['initialize']
ok(any('v.fprev=-1' in l for l in _INIT),
   'initialize 未把 v.fprev 置 -1（进场时弃牌区那张会凭空飞一次）')
ok(any('v.ft=1' in l for l in _INIT), 'initialize 未把 v.ft 置 1（初始应视为"已飞完"）')

# ------------------------------------------------------------------ 7.3 定庄展示（bit15 / v.show_all）
# 展示期间四张比大小的牌挂在各自座位的手牌区，客户端要把它们摆到「该座位自己的出牌区」。
ok('v.show_all' in LB['card_0']['position'][0],
   'card_N 的位置未处理定庄展示态（四张比大小牌会全挤在错误的位置）')
ok('v.show_all' in LB['card_0']['position'][1],
   'card_N 的高度未处理定庄展示态（应平铺在台面上）')
ok('v.show_all' in LB['card_0']['rotation'][1],
   'card_N 的朝向未处理定庄展示态（应平放并朝向观众）')
ok('v.show_all' in LB['card_0']['scale'],
   'card_N 的显隐未处理定庄展示态（展示时应让所有人可见）')
ok('v.show_all' in LB['fake_vis_0']['scale'],
   '定庄展示期间应隐藏对手的 “?” 牌背（fake_vis_N）')
# 发牌动画结束前不显示弃牌堆顶（= 起始牌，需求：发完 7 张后才翻出这张）
ok('v.deal_n>=255' in LB['card_0']['scale'],
   'card_N 的 scale 未按 v.deal_n>=255 限制弃牌堆顶的出现时机（起始牌会提前出现）')

# ------------------------------------------------------------------ 7.3 点击捕获框实体
# Java 的 UnoClickBoxEntity.IDENTIFIER ↔ 资源包 entity/uno/uno_clickbox.entity.json ↔ 几何体，
# 三者对不上时客户端认不出这个实体，准星就找不到"可交互目标"（点悬浮手牌没反应）。
BOX_JAVA = os.path.join(REPO, 'src/main/java/com/tabletopgame/entity/UnoClickBoxEntity.java')
with io.open(BOX_JAVA, encoding='utf-8') as fh:
    BOX_SRC = fh.read()
_box_id = re.search(r'IDENTIFIER = "([^"]+)"', BOX_SRC)
ok(_box_id is not None, 'UnoClickBoxEntity 未定义 IDENTIFIER')
if _box_id:
    _bid = _box_id.group(1)
    _ent_path = os.path.join(R.RP, 'entity/uno/uno_clickbox.entity.json')
    ok(os.path.isfile(_ent_path), '缺少 entity/uno/uno_clickbox.entity.json')
    if os.path.isfile(_ent_path):
        with io.open(_ent_path, encoding='utf-8') as fh:
            _bdoc = json.load(fh)['minecraft:client_entity']['description']
        ok(_bdoc['identifier'] == _bid,
           '捕获框实体 identifier 不一致：Java=%s 资源=%s' % (_bid, _bdoc['identifier']))
        _geo = _bdoc['geometry']['default']
        _geo_path = os.path.join(R.RP, 'models/entity/uno/uno_clickbox.geo.json')
        ok(os.path.isfile(_geo_path), '缺少 models/entity/uno/uno_clickbox.geo.json')
        if os.path.isfile(_geo_path):
            with io.open(_geo_path, encoding='utf-8') as fh:
                _gdoc = json.load(fh)['minecraft:geometry'][0]
            ok(_gdoc['description']['identifier'] == _geo,
               '捕获框几何体名不一致：entity=%s geo=%s' % (_geo, _gdoc['description']['identifier']))
            _cubes = sum(len(b.get('cubes', [])) for b in _gdoc['bones'])
            ok(_cubes == 0, '捕获框几何体必须一根 cube 都没有（它不该渲染任何东西），实际 %d' % _cubes)
    ok('UnoClickBoxEntity.DEF' in io.open(
        os.path.join(REPO, 'src/main/java/com/tabletopgame/TabletopGamePlugin.java'),
        encoding='utf-8').read(), '插件未注册捕获框实体定义')
# 「碰撞箱恢复原样」的断言在 7.8b（那里才加载了 UnoTable 源码）

# ------------------------------------------------------------------ 7.4 悬浮倒计时（固定在方块上方）
# 用户口径：「是那种悬浮窗显示在方块上面（位置永远固定在方块上），不是屏幕提示」。
# 落地 = 同一个空实体的第二个实例 + name tag 文字（世界坐标，永远挂在牌桌上方）。
ok('setFloatingText' in BOX_SRC, 'UnoClickBoxEntity 缺少悬浮文字接口 setFloatingText')
ok('setNameTagAlwaysVisible' in BOX_SRC,
   '悬浮文字必须开 always-visible（否则要盯着实体才显示）')
ok('setDataProperty' in BOX_SRC and 'DATA_COLLISION_BOX' in BOX_SRC,
   '悬浮牌子实体的碰撞箱未压到 0.001（会挡住牌桌点击）')
TABLE_JAVA = os.path.join(REPO, 'src/main/java/com/tabletopgame/game/UnoTable.java')
with io.open(TABLE_JAVA, encoding='utf-8') as fh:
    TABLE_SRC = fh.read()
ok('COUNTDOWN_LIFT' in TABLE_SRC and 'spawnCountdown' in TABLE_SRC,
   'UnoTable 没有生成悬浮倒计时牌子（spawnCountdown / COUNTDOWN_LIFT 缺失）')
ok('setCountdownText' in TABLE_SRC and 'tickCountdown' in TABLE_SRC,
   'UnoTable 没有更新悬浮倒计时（tickCountdown / setCountdownText 缺失）')
ok('sendTip' not in TABLE_SRC.split('private void tickCountdown')[1][:900],
   '倒计时又退回成屏幕提示了（tickCountdown 里不应再出现 sendTip）')
ok('countdown.close()' in TABLE_SRC, '销毁牌桌时没有回收悬浮倒计时实体')

# ------------------------------------------------------------------ 8. 按钮码与按钮组三方一致
ACT2JAVA = {
    'play': 'PLAY', 'draw': 'DRAW', 'skip': 'SKIP', 'hint': 'HINT',
    'cancel': 'CANCEL_SELECT', 'next': 'NEXT', 'exit': 'EXIT',
    'c_red': 'C_RED', 'c_yellow': 'C_YELLOW', 'c_green': 'C_GREEN', 'c_blue': 'C_BLUE',
}
JAVA_CODE = {k: int(v) for k, v in re.findall(
    r'public static final int ([A-Z_]+) = (\d+);', JAVA)}
NAMES = {'PLAY': 'play', 'DRAW': 'draw', 'SKIP': 'skip', 'HINT': 'hint',
         'CANCEL_SELECT': 'cancel', 'NEXT': 'next', 'EXIT': 'exit',
         'C_RED': 'c_red', 'C_YELLOW': 'c_yellow', 'C_GREEN': 'c_green', 'C_BLUE': 'c_blue'}
for jname, jval in JAVA_CODE.items():
    act = NAMES.get(jname)
    if act is None:
        continue
    ok(A.CODE[act] == jval, 'Java %s=%d 与资源 CODE[%s]=%d 不一致' % (jname, jval, act, A.CODE[act]))

GROUP_JAVA = {'play': 'BTN_PLAY', 'drawn': 'BTN_DRAWN', 'settle': 'BTN_SETTLE', 'color': 'BTN_COLOR'}
for gname, jname in GROUP_JAVA.items():
    m = re.search(re.escape(jname) + r'\s*=\s*\{([^}]*)\}', JAVA)
    if not ok(m is not None, 'Java 未找到按钮组 %s' % jname):
        continue
    java_actions = [NAMES[x.strip().replace('Controls.', '')]
                    for x in m.group(1).split(',') if x.strip()]
    ok(java_actions == A.BUTTON_GROUPS[gname],
       '%s 顺序不一致：Java=%s，资源=%s' % (jname, java_actions, A.BUTTON_GROUPS[gname]))
    for slot, act in enumerate(java_actions):
        ok(slot <= 3, '%s 槽位越界' % jname)

# 对照组：0xfriendly 打包结果应与探针脚本验证过的常量一致
PLAY = JavaPack = None
m = re.search(r'BTN_PLAY\s*=\s*\{([^}]*)\}', JAVA)
if m:
    codes = [JAVA_CODE[x.strip().replace('Controls.', '')] for x in m.group(1).split(',') if x.strip()]
    packed = 0
    for s, c in enumerate(codes):
        packed |= (c & 15) << (4 * s)
    ok(packed == 0x1245, '正常出牌按钮组打包值应为 0x1245（取消/提示/抽牌/出牌），实际 0x%X' % packed)

# ------------------------------------------------------------------ 7.9 插件启动期：实体定义只许注册一次
# 2026-10-15 真机事故：TabletopGamePlugin.onLoad 里 `registerDefinition(UnoClickBoxEntity.DEF)`
# 被同一段改动**重复插入**了两次，插件加载直接 FATAL：
#   IllegalArgumentException: Custom entity tabletopgame:uno_clickbox was already registered
# （编译期毫无征兆 —— 重复注册是运行期才炸的）。这里把「每个 DEF 恰好注册一次 + 不留重复 import」
# 变成离线断言，改坏了立刻红，不用等开服。
PLUGIN_JAVA = os.path.join(REPO, 'src/main/java/com/tabletopgame/TabletopGamePlugin.java')
with io.open(PLUGIN_JAVA, encoding='utf-8') as fh:
    PLUGIN_SRC = fh.read()
_regs = re.findall(r'registerDefinition\(\s*([A-Za-z_0-9]+)\.DEF\s*\)', PLUGIN_SRC)
seen = {}
for _r in _regs:
    seen[_r] = seen.get(_r, 0) + 1
for _name, _cnt in sorted(seen.items()):
    ok(_cnt == 1, '%s.DEF 注册了 %d 次（重复注册会让插件 onLoad 直接 FATAL）' % (_name, _cnt))
ok('UnoTableEntity' in seen, '没有注册 UnoTableEntity.DEF')
ok('UnoClickBoxEntity' in seen,
   '没有注册 UnoClickBoxEntity.DEF（点击捕获框，悬空手牌会点不动）')
_imp = [l.strip() for l in PLUGIN_SRC.split('\n') if l.strip().startswith('import ')]
for _k, _v in sorted({k: _imp.count(k) for k in set(_imp)}.items()):
    ok(_v == 1, 'TabletopGamePlugin 重复 import（同一段改动被重复应用的痕迹）：%s' % _k)
_pr = re.findall(r'([A-Za-z_0-9]+)\.registerProperties\(\)', PLUGIN_SRC)
ok(len(_pr) == len(set(_pr)), 'registerProperties() 被重复调用：%s' % _pr)
# 整个插件源码树：重复 import 一律视为"同一段改动被应用了两次"的痕迹（无害也要清掉）
for _dir, _, _files in os.walk(os.path.join(REPO, 'src/main/java/com/tabletopgame')):
    for _f in _files:
        if not _f.endswith('.java'):
            continue
        _p = os.path.join(_dir, _f)
        with io.open(_p, encoding='utf-8') as _fh:
            _lines = [l.strip() for l in _fh.read().split('\n') if l.strip().startswith('import ')]
        _dups = sorted({k for k in _lines if _lines.count(k) > 1})
        ok(not _dups, '%s 重复 import：%s' % (_f, _dups))

# ------------------------------------------------------------------ 7.5 「定位器」持握道具
# 需求：手持道具右键 → 客户端一定会把"使用物品"事务发给服务端 → 服务端拿到信号做射线判定。
# 这条链上任何一环名字对不上（Java ID ↔ attachable ↔ geo ↔ 贴图/动画/RC ↔ 粒子），
# 客户端就只是"手里有把看不见的东西"或者不显示光点，服务端不报任何错。
LOC_JAVA = os.path.join(REPO, 'src/main/java/com/tabletopgame/item/LocatorItem.java')
ok(os.path.isfile(LOC_JAVA), '缺少 LocatorItem.java（定位器道具）')
_loc_id, _loc_icon = None, None
if os.path.isfile(LOC_JAVA):
    with io.open(LOC_JAVA, encoding='utf-8') as fh:
        LOC_SRC = fh.read()
    _lid = re.search(r'IDENTIFIER = "([^"]+)"', LOC_SRC)
    _licon = re.search(r'ICON = "([^"]+)"', LOC_SRC)
    _loc_id = _lid.group(1) if _lid else None
    _loc_icon = _licon.group(1) if _licon else None
    ok(_loc_id == 'tabletopgame:locator', '定位器 identifier 应为 tabletopgame:locator，实际 %s' % _loc_id)
    _att = os.path.join(R.RP, 'attachables/uno/locator.json')
    ok(os.path.isfile(_att), '缺少 attachables/uno/locator.json（手持时不显示模型）')
    if os.path.isfile(_att):
        with io.open(_att, encoding='utf-8') as fh:
            _adoc = json.load(fh)['minecraft:attachable']['description']
        ok(_adoc['identifier'] == _loc_id,
           'attachable identifier 与 Java 不一致：%s vs %s' % (_adoc['identifier'], _loc_id))
        _geo_ref = _adoc['geometry']['default']
        _tex_ref = _adoc['textures']['default']
        ok(os.path.isfile(os.path.join(R.RP, _tex_ref + '.png')),
           'attachable 引用的贴图不存在：%s.png' % _tex_ref)
        _lg = os.path.join(R.RP, 'models/entity/uno/locator.geo.json')
        ok(os.path.isfile(_lg), '缺少 models/entity/uno/locator.geo.json')
        if os.path.isfile(_lg):
            with io.open(_lg, encoding='utf-8') as fh:
                _gdoc = json.load(fh)['minecraft:geometry'][0]
            ok(_gdoc['description']['identifier'] == _geo_ref,
               '几何体名与 attachable 对不上：%s vs %s'
               % (_gdoc['description']['identifier'], _geo_ref))
        _anims = _adoc['animations']
        _af = os.path.join(R.RP, 'animations/uno/locator.animation.json')
        ok(os.path.isfile(_af), '缺少 locator.animation.json（持握姿态）')
        if os.path.isfile(_af):
            with io.open(_af, encoding='utf-8') as fh:
                _adoc2 = json.load(fh)['animations']
            for _k, _v in _anims.items():
                ok(_v in _adoc2, 'attachable 引用的动画 %s 不存在于 locator.animation.json' % _v)
        _rcs = os.path.join(R.RP, 'render_controllers/uno/locator.render_controllers.json')
        ok(os.path.isfile(_rcs), '缺少 locator 渲染控制器')
        if os.path.isfile(_rcs):
            with io.open(_rcs, encoding='utf-8') as fh:
                _rc_doc = json.load(fh)['render_controllers']
            for _rc in _adoc['render_controllers']:
                ok(_rc in _rc_doc, 'attachable 引用的渲染控制器 %s 不存在' % _rc)
    # 背包图标
    _itf = os.path.join(R.RP, 'textures/item_texture.json')
    ok(os.path.isfile(_itf), '缺少 textures/item_texture.json（背包图标没处查）')
    if os.path.isfile(_itf):
        with io.open(_itf, encoding='utf-8') as fh:
            _it = json.load(fh)['texture_data']
        ok(_loc_icon in _it, 'item_texture.json 缺少图标键 %s' % _loc_icon)
        if _loc_icon in _it:
            ok(os.path.isfile(os.path.join(R.RP, _it[_loc_icon]['textures'] + '.png')),
               '图标贴图不存在：%s.png' % _it[_loc_icon]['textures'])
        # 2026-10-16 事故：build_locator 曾「只写定位器」覆盖 item_texture.json，
        # 把四棋棋盘 / UNO 牌桌的图标键全冲掉 ⇒ 除定位器外所有物品在背包里变"空气"。
        # 防回归：全部物品图标键必须在、且贴图文件都得存在。
        for _k in ('tabletopgame_board_icon', 'tabletopgame_xiangqi_board_icon',
                   'tabletopgame_othello_board_icon', 'tabletopgame_go_board_icon_9',
                   'tabletopgame_go_board_icon_13', 'tabletopgame_go_board_icon_19',
                   'tabletopgame_uno_table_icon'):
            ok(_k in _it, 'item_texture.json 缺少物品图标键 %s（该物品会变空气）' % _k)
            if _k in _it:
                ok(os.path.isfile(os.path.join(R.RP, _it[_k]['textures'] + '.png')),
                   '物品图标贴图不存在：%s.png' % _it[_k]['textures'])
    # 表单精简（2026-10-16）：只留座位状态 / 倍数 / 桌主，去掉免费局说明、余额、开局要求。
    _st = TABLE_SRC.split('public String statusText', 1)[1].split('public String seatOccupantLabel', 1)[0]
    for _need in ('座位状态', '当前倍数', '当前桌主', '东侧'):
        ok(_need in _st, 'statusText 缺少「%s」（表单精简后必须保留）' % _need)
    for _gone in ('你的余额', '满足开局要求', '还需至少'):
        ok(_gone not in _st, 'statusText 仍残留「%s」（用户要求只留座位/倍数/桌主）' % _gone)
    # 2026-10-15 第四改：「有穿模那种感觉，做成像黑色框那样的，是在平面上的」
    # → 光点从粒子**彻底退役**，改成 uno_table.geo 上的薄片骨骼 laser_dot：
    #   服务端把命中点的牌面局部坐标 (u, v) 与区内展示序号经三条实体属性广播，
    #   客户端用手牌同一套布局表达式摆放 → 与牌面严格共面，不再穿模/拖影/闪烁。
    # 粒子文件必须不存在（防止旧粒子被任何代码重新引用）。
    ok(not os.path.isfile(os.path.join(R.RP, 'particles/uno/locator_dot.particle.json')),
       'locator_dot.particle.json 仍存在（光点已改模型薄片 laser_dot，粒子应彻底退役）')
    # 模型里有薄片骨骼 laser_dot
    _tg_geo = os.path.join(R.RP, 'models/entity/uno/uno_table.geo.json')
    ok(os.path.isfile(_tg_geo), '缺少 uno_table.geo.json')
    if os.path.isfile(_tg_geo):
        with io.open(_tg_geo, encoding='utf-8') as fh:
            _bones = json.load(fh)['minecraft:geometry'][0]['bones']
        ok(any(_b.get('name') == 'laser_dot' for _b in _bones),
           'uno_table.geo.json 缺少激光薄片骨骼 laser_dot')
    # Java 侧广播链：三条属性注册 + 偏移常量 + 量化函数 + 每 tick 写入
    with io.open(os.path.join(REPO, 'src/main/java/com/tabletopgame/entity/UnoTableEntity.java'),
                 encoding='utf-8') as fh:
        _te_src = fh.read()
    for _pid in ('P_LASER_U', 'P_LASER_V', 'P_LASER_S'):
        ok(_pid in _te_src, 'UnoTableEntity 缺少激光属性 %s（客户端拿不到坐标就不显示光点）' % _pid)
    for _cst in ('LASER_U_OFFSET', 'LASER_V_OFFSET', 'LASER_NONE'):
        ok(_cst in _te_src, 'UnoTableEntity 缺少常量 %s' % _cst)
    ok('quantizeLaser' in TABLE_SRC, 'UnoTable 缺少 quantizeLaser（牌面局部坐标量化广播）')
    ok('setLaserU' in TABLE_SRC and 'setLaserV' in TABLE_SRC and 'setLaserS' in TABLE_SRC,
       'UnoTable.tickLocatorDots 没把激光坐标写入实体属性')
    # 性能优化（2026-10-16）：激光/观众刷新的「空桌跳过」+ 属性写「缓存去重」。
    # 防止未来退回「每 tick / 每秒全量空转」。
    ok('laserUCache' in _te_src and 'laserVCache' in _te_src and 'laserSCache' in _te_src,
       'UnoTableEntity 缺激光缓存字段（setLaserU/V/S 会失去"值不变不发包"的去重）')
    ok('无人持定位器' in TABLE_SRC and '没有观战者需要同步' in TABLE_SRC,
       'UnoTable 的 tickLocatorDots / refreshViewers 缺空桌跳过（空桌会每 tick/每秒空转）')
    # 资源包解码段与常量对齐（偏移改了必须两端同步，否则光点整体偏移）
    with io.open(os.path.join(REPO, 'tools/uno/build_table.py'), encoding='utf-8') as fh:
        _bt_src = fh.read()
    _uv_off = re.search(r'LASER_U_OFFSET\s*=\s*([0-9.]+)', _te_src)
    _vv_off = re.search(r'LASER_V_OFFSET\s*=\s*([0-9.]+)', _te_src)
    ok(_uv_off is not None and ('%.1f' % float(_uv_off.group(1))) in _bt_src,
       'LASER_U_OFFSET 与客户端解码偏移不一致')
    ok(_vv_off is not None and ('%.1f' % float(_vv_off.group(1))) in _bt_src,
       'LASER_V_OFFSET 与客户端解码偏移不一致（含选中牌 RAISE 折算）')
    ok('instanceof LocatorItem' in TABLE_SRC,
       'UnoTable 没判断"手持定位器"（不会放光点）')
    ok(os.path.isfile(os.path.join(REPO, 'tools/uno/build_locator.py')),
       '缺少 tools/uno/build_locator.py（定位器资源生成器）')
    # 2026-10-15 三改：模型贴图 = 剖面烘焙 + UV 的 v 重映射（v = 1 - y/16）；光点改白。
    # 第四改（同日）：光点退役粒子、改模型薄片 laser_dot（见上）。逐一断言，防止再退化。
    _lg2 = os.path.join(R.RP, 'models/entity/uno/locator.geo.json')
    if os.path.isfile(_lg2):
        with io.open(_lg2, encoding='utf-8') as fh:
            _mesh = json.load(fh)['minecraft:geometry'][0]['bones'][0]['poly_mesh']
        _pos, _uvs, _polys = _mesh['positions'], _mesh['uvs'], _mesh['polys']
        _bad = 0
        for _poly in _polys:
            for _vtx in _poly:
                _y = _pos[_vtx[0]][1]
                if abs(_uvs[_vtx[2]][1] - (1.0 - _y / 16.0)) > 1e-3:
                    _bad += 1
        ok(_bad == 0,
           '定位器 UV 未按 v = 1 - y/16 重映射（%d 个顶点引用对不上，模型会显示错色）' % _bad)
    _btex = os.path.join(R.RP, 'textures/tabletopgame/uno/locator.png')
    if os.path.isfile(_btex):
        _im = Image.open(_btex).convert('RGBA')
        _op = sum(1 for _p in _im.getdata() if _p[3] < 250)
        ok(_op == 0, '定位器模型贴图有 %d 个半透明像素（mipmap 会把透明混进来）' % _op)
    # 光点贴图随粒子一起退役（激光点 = 模型薄片，直接取图集白色长条 CARD_SIDE_WHITE）
    ok(not os.path.isfile(os.path.join(R.RP, 'textures/tabletopgame/uno/locator_dot.png')),
       'locator_dot.png 仍存在（粒子已退役，光点贴图应删除）')

# ------------------------------------------------------------------ 7.6 定位器的发放 / 回收
with io.open(os.path.join(REPO, 'src/main/java/com/tabletopgame/game/UnoManager.java'),
             encoding='utf-8') as fh:
    MGR_SRC = fh.read()
ok('public void ensureLocator(' in MGR_SRC, 'UnoManager 缺少 ensureLocator（开局发放）')
ok('public void takeLocator(' in MGR_SRC, 'UnoManager 缺少 takeLocator（回收）')
ok('manager.ensureLocator(' in TABLE_SRC, '开局没有发放定位器')
ok('manager.takeLocator(' in TABLE_SRC, '离桌/拆桌没有回收定位器')
ok('registerCustomItem(LocatorItem.class)' in PLUGIN_SRC, '插件没有注册定位器道具')

# ------------------------------------------------------------------ 7.7 牌沿压平（一次颜色）
# 用户三轮反馈的最终口径：「这里还有一些其他的渐变红色，我要这些边缘都只用一种颜色」。
# 行为契约：距纸底 FLAT_D 以内的每个像素，要么 = 环色，要么是"距纸底超过 FLAT_CORE 且
# 比环色亮 FLAT_LUM 以上"的设计元素（实测只有背面牌的内嵌白框线符合）。
# 抽样 7 张代表牌（四色 / 野牌 / 背面 / 问号）全量检查 —— 任何一层残留的中间色都会被点出来。
_edge_bad = []
_edge_plan = []
for _k in (0, 13, 26, 39, 52, 54, 55):
    _cell = Image.open(A.DECK_SRC).convert('RGBA').crop(A.card_cell(_k)) \
        .resize((A.CARD_W, A.CARD_H), Image.LANCZOS)
    _out, _ring = A.fill_paper_with_ring(_cell)
    if _ring is None:
        _edge_bad.append('tile %d 取不到环色' % _k)
        continue
    _mask = A.paper_mask(_cell)
    _dist = A._chamfer_dist(_mask, A.CARD_W, A.CARD_H)
    _lr = A._lum(_ring)
    _px = _out.load()
    _bad = _gate = 0
    for _j in range(A.CARD_H):
        _base = _j * A.CARD_W
        for _i in range(A.CARD_W):
            _kk = _base + _i
            if _mask[_kk] or _dist[_kk] > A.FLAT_D:
                continue
            _c = _px[_i, _j]
            if _c[:3] == _ring:
                continue
            if _dist[_kk] > A.FLAT_CORE and A._lum(_c) > _lr + A.FLAT_LUM:
                _gate += 1
                continue
            _bad += 1
    _edge_plan.append((_k, _gate))
    if _bad:
        _edge_bad.append('tile %d 压平后仍残留 %d px 杂色' % (_k, _bad))
ok(not _edge_bad, '牌沿压平不彻底：%s' % ('; '.join(_edge_bad) if _edge_bad else ''))
# 彩牌（非背面）不该有任何"被门槛保留"的像素 —— 门槛只服务背面白框线那一类设计元素
for _k, _g in _edge_plan:
    if _k != 54:
        ok(_g == 0, 'tile %d 边缘带里有被亮度门槛放过的亮像素（会残留"淡边"）x%d' % (_k, _g))
ok(all(_k == 54 for _k, _g in _edge_plan if _g > 0),
   '除背面牌外还有牌保留了边缘亮像素：%s' % _edge_plan)

# ------------------------------------------------------------------ 7.8 激光开关（蹲下 + 使用键）
# 需求：「玩家蹲下的时候点使用键，只要没触发那些uno棋盘的东西，就变成激光的开关控制
#       （用broadcastActionBar显示）」——开关本身 + 光点受控 + 三个交互入口都接入。
ok('public boolean isLaserOn(' in MGR_SRC, 'UnoManager 缺少 isLaserOn（激光开关状态）')
ok('private static boolean laserMode(' in MGR_SRC, 'UnoManager 缺少 laserMode（蹲下 + 手持定位器判定）')
ok('player.isSneaking()' in MGR_SRC, '激光模式未检查「蹲下」')
ok('private void toggleLaser(' in MGR_SRC, 'UnoManager 缺少 toggleLaser（开关切换）')
if 'private void toggleLaser(' in MGR_SRC:
    _tl = MGR_SRC.split('private void toggleLaser(')[-1].split('\n    private ')[0]
    ok('sendTip' in _tl, '激光开关没有用动作栏（sendTip）回报状态')
ok(MGR_SRC.count('laserMode(player)') >= 3,
   '三个交互入口（方块 / 空中 / 实体）没有全部接入激光模式，实际 %d 处'
   % MGR_SRC.count('laserMode(player)'))
ok(MGR_SRC.count('useBoard(player, false)') >= 2,
   '激光模式下判定「是否点到牌/按钮」没走无菜单版 useBoard')
ok('manager.isLaserOn(p)' in TABLE_SRC, 'UnoTable 的绿色光点没有受激光开关控制')

# ------------------------------------------------------------------ 7.8b 绿点常驻（不闪）
# 需求：「激光笔不是那种闪烁的那种效果，是要常驻显示」。做法 = 每 tick 补一颗粒子（寿命 0.18 秒）。
ok(MGR_SRC.count('tickLocatorDots') >= 2,
   'UnoManager 缺少 tickLocatorDots（绿点常驻刷新入口）')
ok('void tickLocatorDots()' in TABLE_SRC, 'UnoTable 缺少 tickLocatorDots（每 tick 补绿点）')
ok('unoManager::tickLocatorDots' in PLUGIN_SRC,
   '插件没有按 tick 调度 tickLocatorDots（绿点会闪）')
# 用户 2026-10-15 要求「把放大的实体碰撞箱恢复原样」：牌桌不得再调用放大入口，
# 实体保持 initEntity() 里的默认 0.001 箱子（手牌点击改由「定位器」持握道具承担）。
ok('.configureClickHitbox(' not in TABLE_SRC,
   '牌桌又调用了 configureClickHitbox（用户要求捕获框保持默认 0.001，不要再放大）')
# 2026-10-15 第四改：光点退役粒子、改模型薄片 laser_dot。防止粒子路径回归：
ok('SpawnParticleEffectPacket' not in TABLE_SRC,
   'UnoTable 又出现 SpawnParticleEffectPacket（光点已改模型薄片，粒子不得回归）')

# ------------------------------------------------------------------ 输出
print('客户端读取属性 : %d 个' % len(CLIENT_PROPS))
print('Java 注册属性   : %d 个' % len(JAVA_PROPS))
print('按钮组          : %s' % ', '.join('%s=%s' % (k, '/'.join(v)) for k, v in A.BUTTON_GROUPS.items()))
for n in notes:
    print('note: ' + n)
print('total problems : %d' % len(problems))
for p in problems:
    print('  FAIL ' + p)
sys.exit(1 if problems else 0)
