# -*- coding: utf-8 -*-
"""生成「定位器」（tabletopgame:locator）持握道具的全部资源。

需求（2026-10-15 用户）：
  「我能做一个物品，就是它右键使用，不会触发任何东西，但是能发信号到服务端……
    模型在这里（laser_pointer.geo.json / texture.png），注意这个东西取名叫**定位器**……
    开局，如果玩家背包没有这个东西自动发放，结束对局的话，自动回收。」
  后续三次修改（同日）：
  · 「把激光笔的模型贴图换成这个吧」→ 模型贴图改为**按 texture.png 的剖面烘焙**（见下）；
  · 「激光点换成白色的」→ 光点贴图改白；
  · 「不是那种闪烁……要常驻显示 / 会有拖影 / 显示不完整 / 有穿模那种感觉」→ 光点从粒子
    **彻底改成模型薄片骨骼 laser_dot**（挂在 uno_table.geo 上、与牌面共面，
    局部坐标由服务端经 uno_laser_u/v/s 三条实体属性广播）——本脚本不再产出任何粒子。

产出（全部落在插件内置资源包）：
  models/entity/uno/locator.geo.json          模型（几何照抄，**UV 的 v 按笔身高度重映射**）
  textures/tabletopgame/uno/locator.png       模型贴图 = 把 texture.png 的竖条剖面**横向延展**烘焙
  animations/uno/locator.animation.json       第一/第三人称持握姿态（照抄斗地主 cursor 的数值）
  attachables/uno/locator.json                手持时显示 3D 模型
  render_controllers/uno/locator.render_controllers.json
  textures/item_texture.json                  背包图标（= texture.png 原图）

⚠️ 为什么模型贴图是「烘焙」而不是直接复制：
  模型（照抄斗地主激光笔）的 UV 只取样**全高、约 1/16 宽的两条竖列**（u∈[0,1/16] 与 [15/16,1]），
  斗地主原配的 16x16 贴图就把「笔尖→笔身」的剖面画在第 0 列里；而用户那份 16x16
  （象棋/激光笔/laser_pointer.png）已几乎全黑（250/256 像素为纯黑），模型因此是一根黑棍。
  用户给的 `texture.png`（32x32）是一张**竖条剖面图**（灰头 → 白环 → 灰颈 → 黑身）。
  做法：把剖面的每一行**横向铺满整幅**（32 列同色、整幅不透明，mipmap 安全），
  并把 UV 的 v 重映射为 v = 1 - y/16 —— 于是模型表面直接显示剖面图的配色。

对照来源：斗地主插件的激光笔（`Doudizhu/.../attachables/cursor.json`、
`particles/laser_pointer_dot.particle.json`、`item/CursorItem.java`）。
"""
import io
import json
import os
import sys

from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import uno_assets as A

HERE = os.path.dirname(os.path.abspath(__file__))
RP = A.RP
DDZ = A.DDZ
# 模型几何：象棋/斗地主两份逐字节一致（md5 相同），取象棋那份；只在输出时改 identifier 与 UV。
SRC_GEO = 'D:/CodeProject/Gobang/象棋/激光笔/laser_pointer.geo.json'
# 剖面图（32x32，用户提供）：**既是背包图标，也是模型贴图的烘焙源**（见 bake_model_texture）。
# 注意：象棋/激光笔/laser_pointer.png（16x16）已几乎全黑，不再用作模型贴图。
SRC_ICON = os.path.join(DDZ, 'uno/资源/texture.png')

IDENT = 'tabletopgame:locator'
GEO_NAME = 'geometry.tabletopgame.locator'
TEX_PATH = 'textures/tabletopgame/uno/locator'
ICON_PATH = 'textures/tabletopgame/uno/locator_item'
ICON_KEY = 'tabletopgame_locator'
RC_NAME = 'controller.render.tabletopgame.locator'

# item_texture.json 的完整键表：定位器之外，还有四棋棋盘 + UNO 牌桌的背包图标。
# ⚠️ build_item_texture 曾「只写定位器」整个覆盖 item_texture.json，把其它物品图标全冲成空气
#   （2026-10-16 用户报：除定位器外所有物品都变成空气）。现在用这张表兜底补齐 + 合并、绝不覆盖。
ITEM_TEXTURE_BASE = {
    'tabletopgame_board_icon': 'textures/tabletopgame/gomoku/board_icon',
    'tabletopgame_xiangqi_board_icon': 'textures/tabletopgame/xiangqi/xiangqi_board_icon',
    'tabletopgame_othello_board_icon': 'textures/tabletopgame/othello/othello_board_icon',
    'tabletopgame_go_board_icon_9': 'textures/tabletopgame/go/go_board_9',
    'tabletopgame_go_board_icon_13': 'textures/tabletopgame/go/go_board_13',
    'tabletopgame_go_board_icon_19': 'textures/tabletopgame/go/go_board_19',
    'tabletopgame_uno_table_icon': 'textures/tabletopgame/uno/physical_table_item',
}


def write_json(path, doc):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with io.open(path, 'w', encoding='utf-8') as fh:
        json.dump(doc, fh, ensure_ascii=False, separators=(',', ':'))
    print('  ->', os.path.relpath(path, RP))


def copy_geo():
    """载入模型、改 identifier（不落盘 —— UV 重映射后再写，见 write_geo）。"""
    with io.open(SRC_GEO, encoding='utf-8') as fh:
        doc = json.load(fh)
    desc = doc['minecraft:geometry'][0]['description']
    old = desc['identifier']
    desc['identifier'] = GEO_NAME
    print('geo: %s -> %s' % (old, GEO_NAME))
    return doc


def write_geo(doc):
    write_json(os.path.join(RP, 'models/entity/uno/locator.geo.json'), doc)


def remap_uvs(doc):
    """把模型 UV 的 **v 按笔身高度**重映射：v = 1 - y/16。

    模型的 UV 是「同一列的不同 v」表达笔的每一段（斗地主原配贴图把剖面画在第 0 列）。
    我们改用竖向剖面图烘焙的贴图（每列相同），所以只需要把 v 对准剖面的行：
      · y = 15（笔尖一端）→ v = 0.0625 → 剖面顶部（灰头 / 白环）；
      · y =  1（笔尾一端）→ v = 0.9375 → 剖面底部（黑身）。
    y∈[1,15] 恰好铺满剖面行 2..30，每 1 单位 ≈ 2 行。u 保持原样（贴图每列都一样）。

    ⚠️ UV 索引会被多个顶点**共享**（原模型合批过），直接改同一个索引会让不同高度的
    顶点互相覆盖（实测 288 个引用里 6 个对不上）。所以这里给每个顶点引用**单独建 uv 条目**。
    """
    mesh = doc['minecraft:geometry'][0]['bones'][0]['poly_mesh']
    pos, uvs, polys = mesh['positions'], mesh['uvs'], mesh['polys']
    new_uvs = []
    for poly in polys:
        for vtx in poly:
            y = pos[vtx[0]][1]
            u = uvs[vtx[2]][0]              # 保留原 u（贴图整幅同色，u 随便取哪列都行）
            vtx[2] = len(new_uvs)
            new_uvs.append([u, round(1.0 - y / 16.0, 6)])
    mesh['uvs'] = new_uvs
    print('  UV v 重映射：v = 1 - y/16（%d 个顶点引用各自独立 uv；笔尖 y=15 → 剖面顶部）'
          % len(new_uvs))


def sample_colors(doc, tex):
    """抽样：每个面片的 UV 质心落在什么颜色 —— 用来离线确认模型"看得见、颜色对"。"""
    mesh = doc['minecraft:geometry'][0]['bones'][0]['poly_mesh']
    uvs, polys = mesh['uvs'], mesh['polys']
    tw, th = tex.size
    px = tex.load()
    seen = {}
    for poly in polys:
        us = [uvs[v[2]][0] for v in poly]
        vs = [uvs[v[2]][1] for v in poly]
        x = min(tw - 1, max(0, int(sum(us) / len(us) * tw)))
        y = min(th - 1, max(0, int(sum(vs) / len(vs) * th)))
        c = px[x, y]
        seen[c] = seen.get(c, 0) + 1
    print('  面片取色统计（颜色 -> 面片数）:', sorted(seen.items(), key=lambda kv: -kv[1])[:6])


def bake_model_texture(icon):
    """把剖面图烘焙成模型贴图（返回烘焙图）：每一行 = 剖面该行的颜色，**横向铺满整幅**。

    · 剖面取图案 bbox 的**中列**（避开边缘的抗锯齿），逐行取平均；
    · 上下留白行**向两端夹取最近的剖面行** → 整幅 32x32 不透明
      （模型沿 u∈[0,1/16] 等窄列取样，mipmap 混色时不会混进透明）；
    · 行对行照抄（32 行不重采样），配合 remap_uvs 的 v = 1 - y/16 一一对应。
    """
    bb = icon.getbbox()                      # 非透明区域 (12, 2, 20, 31) 量级
    if not bb:
        raise ValueError('剖面图为空')
    x0, y0, x1, y1 = bb
    mid = (x0 + x1) // 2
    cls = [mid - 1, mid]                     # 中心两列（避开两侧抗锯齿灰边）
    src = icon.load()
    W, H = icon.size
    out = Image.new('RGBA', (W, H), (0, 0, 0, 0))
    px = out.load()
    for y in range(H):
        sy = min(max(y, y0), y1 - 1)                    # 越界的行夹到剖面两端
        r = g = b = a = 0
        for x in cls:
            c = src[x, sy]
            r += c[0]
            g += c[1]
            b += c[2]
            a += c[3]
        n = len(cls)
        col = (r // n, g // n, b // n, 255)             # 一律不透明
        for x in range(W):
            px[x, y] = col
    dst = os.path.join(RP, TEX_PATH + '.png')
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    out.save(dst)
    print('模型贴图（剖面烘焙）-> %s  %s  剖面 bbox=%s 中列=%s' % (
        os.path.basename(dst), out.size, bb, (cls[0], cls[-1])))
    return out


def copy_icon():
    """背包图标 = 剖面图原图（32x32）。"""
    icon = Image.open(SRC_ICON).convert('RGBA')
    dst = os.path.join(RP, ICON_PATH + '.png')
    icon.save(dst)
    print('背包图标: %s -> %s  %s' % (os.path.basename(SRC_ICON),
                                    os.path.basename(dst), icon.size))
    return icon


def build_attachable():
    doc = {'format_version': '1.20.30', 'minecraft:attachable': {'description': {
        'identifier': IDENT,
        # 只有"主人是玩家"时才挂模型（与斗地主 cursor.json 同写法）
        'item': {IDENT: "query.is_owner_identifier_any('minecraft:player')"},
        'materials': {'default': 'entity'},
        'textures': {'default': TEX_PATH},
        'geometry': {'default': GEO_NAME},
        'animations': {
            'hold_first_person': 'animation.tabletopgame.locator.first_person',
            'hold_third_person': 'animation.tabletopgame.locator.third_person',
        },
        'scripts': {'animate': [
            {'hold_first_person': 'context.is_first_person == 1.0'},
            {'hold_third_person': 'context.is_first_person == 0.0'},
        ]},
        'render_controllers': [RC_NAME],
    }}}
    write_json(os.path.join(RP, 'attachables/uno/locator.json'), doc)


def build_anim():
    # 持握姿态照抄斗地主激光笔（pointer 骨骼的 position/rotation/scale），只改动画名。
    doc = {'format_version': '1.8.0', 'animations': {
        'animation.tabletopgame.locator.first_person': {'loop': True, 'bones': {'pointer': {
            'rotation': [113.2953, -26.3747, 32.0877],
            'position': [-7.10577, 15.78604, -5.32049], 'scale': 0.6}}},
        'animation.tabletopgame.locator.third_person': {'loop': True, 'bones': {'pointer': {
            'rotation': [78, 0, 0],
            'position': [0, 15.21629, -5.95284], 'scale': 0.65}}},
    }}
    write_json(os.path.join(RP, 'animations/uno/locator.animation.json'), doc)


def build_rc():
    doc = {'format_version': '1.8.0', 'render_controllers': {RC_NAME: {
        'geometry': 'Geometry.default',
        'materials': [{'*': 'Material.default'}],
        'textures': ['Texture.default'],
    }}}
    write_json(os.path.join(RP, 'render_controllers/uno/locator.render_controllers.json'), doc)


def build_item_texture():
    """合并登记背包图标 —— **只增/改定位器键，绝不覆盖其它物品的图标**。

    教训（2026-10-16）：早前直接写死 `{ICON_KEY: ...}` 整个覆盖 item_texture.json，
    把四棋棋盘 / UNO 牌桌的图标键全冲掉 ⇒ 除定位器外所有物品在背包里变成"空气"。
    """
    p = os.path.join(RP, 'textures/item_texture.json')
    doc = None
    if os.path.isfile(p):
        with io.open(p, encoding='utf-8') as fh:
            try:
                doc = json.load(fh)
            except Exception:
                doc = None
    if doc is None:
        doc = {'resource_pack_name': 'TabletopGame', 'texture_name': 'atlas.items',
               'texture_data': {}}
    # 兜底补齐所有已知物品图标（防止文件损坏/丢失时其它物品再变空气）
    for k, v in ITEM_TEXTURE_BASE.items():
        doc['texture_data'][k] = {'textures': v}
    doc['texture_data'][ICON_KEY] = {'textures': ICON_PATH}
    write_json(p, doc)


def main():
    print('locator 资源：')
    doc = copy_geo()
    icon = copy_icon()
    baked = bake_model_texture(icon)
    remap_uvs(doc)
    write_geo(doc)
    sample_colors(doc, baked)
    build_anim()
    build_attachable()
    build_rc()
    build_item_texture()
    print('done')


if __name__ == '__main__':
    main()
