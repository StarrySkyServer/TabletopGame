# -*- coding: utf-8 -*-
"""四棋「贴图网格线」与「模型格位」对拍。

用户（2026-10-16）：「前四种棋的所选格框、棋子落点还有点误差——正常（除黑白棋）
所选格框/落点应该在两条线的交叉点上，黑白棋在格子中心」。

对拍口径：
  · 贴图 256x256 铺满 2x2 方块 → 1 世界格 = 128 px；格/线世界偏移 = (px - 128) / 128。
  · 模型侧（棋子骨骼 / 标记骨骼）世界偏移 = 实体原点 + R(yaw) × anim_pos / 16；
    实体原点 = 棋盘区域中心（贴图 128px 处），故模型侧的贴图像素位 = 128 + anim_pos/16*128
    （yaw 旋转只换轴不换相位：本地 +x 与 -z 各对应一条贴图轴）。
  · 检测线位：贴图上网格线是暗色细线，按列/行统计暗像素占比找峰。
"""
import io, json, os, sys
from PIL import Image

RP = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                  '../src/main/resources/assets/resource_pack')


def detect_lines(path, dark=110, min_frac=0.5):
    """返回 (x_lines, y_lines)：按列/行统计暗像素占比 ≥ min_frac 的像素坐标。"""
    im = Image.open(path).convert('L')
    w, h = im.size
    px = im.load()
    xs, ys = [], []
    for x in range(w):
        cnt = sum(1 for y in range(h) if px[x, y] < dark)
        if cnt >= h * min_frac:
            xs.append(x)
    for y in range(h):
        cnt = sum(1 for x in range(w) if px[x, y] < dark)
        if cnt >= w * min_frac:
            ys.append(y)
    # 连续像素合并为一条线的中心
    def merge(v):
        out, cur = [], [v[0]]
        for a in v[1:]:
            if a == cur[-1] + 1:
                cur.append(a)
            else:
                out.append(sum(cur) / len(cur)); cur = [a]
        out.append(sum(cur) / len(cur))
        return out
    return (merge(xs) if xs else [], merge(ys) if ys else [])


def report(name, path, model_phase_px, model_step_px, n_cols, n_rows):
    """model_phase_px: col=0 的模型格位换算到贴图像素；model_step_px: 每格像素。"""
    xl, yl = detect_lines(path)
    print('==', name, path.split('/')[-1])
    print('   贴图实测竖线 %d 条: %s' % (len(xl), ['%.1f' % v for v in xl]))
    print('   贴图实测横线 %d 条: %s' % (len(yl), ['%.1f' % v for v in yl]))
    if xl and n_cols:
        exp = [model_phase_px + model_step_px * c for c in range(n_cols)]
        if len(xl) == n_cols:
            devs = [xl[i] - exp[i] for i in range(n_cols)]
            print('   列偏差(实测-模型): min=%.2f max=%.2f avg=%.2f px  → %.3f 格'
                  % (min(devs), max(devs), sum(devs) / len(devs),
                     sum(devs) / len(devs) / 128))
        else:
            print('   ⚠ 实测竖线 %d 条 ≠ 期望 %d 条' % (len(xl), n_cols))
    if yl and n_rows:
        exp = [model_phase_px + model_step_px * r for r in range(n_rows)]
        if len(yl) == n_rows:
            devs = [yl[i] - exp[i] for i in range(n_rows)]
            print('   行偏差(实测-模型): min=%.2f max=%.2f avg=%.2f px  → %.3f 格'
                  % (min(devs), max(devs), sum(devs) / len(devs),
                     sum(devs) / len(devs) / 128))
        else:
            print('   ⚠ 实测横线 %d 条 ≠ 期望 %d 条' % (len(yl), n_rows))


# ---- 五子棋：动画 hover 式 (mod-7)*1.25*[scale 1.6]，模型 px = 128 + pos/16*128
#      col=0 模型位 = -7*2 = -14 模型单位 → 贴图 px = 128 + (-14/16)*128 = 128-112 = 16
#      步长 = 2 模型单位 → 16 px
report('五子棋 15x15', os.path.join(RP, 'textures/tabletopgame/gomoku/board_surface.png'),
       16.0, 16.0, 15, 15)

# ---- 象棋：动画式 x = mod(col,9)*3.234375-13.125 → 模型 px 位 = 128 + x/16*128
#      col=0 → x=-13.125 → px = 128-105 = 23；步长 3.234375 → 25.875 px
#      行 z = 14.25-3.1667*row → row=0 → z=14.25 → px = 128 + 14.25/16*128 = 242（贴图 y 向下=模型 -z）
#      行步长 3.16667 → 25.333 px（行方向贴图 px 从 242 递减）
report('象棋 9列x10行', os.path.join(RP, 'textures/tabletopgame/xiangqi/xiangqi_board_surface.png'),
       23.0, 25.875, 9, 0)   # 列按 x=23 起
print('   （象棋行：模型 row=0 → 贴图 y=242；row=9 → y=14；步长 25.333 px）')

# ---- 围棋：GoBoard 动画（同五子棋架构，按各自 step/scale）——读动画文件确认
anim = json.load(open(os.path.join(RP, 'animations/go/tabletopgame_go_stone.animation.json'), encoding='utf-8'))
for k, v in anim['animations'].items():
    bones = v.get('bones', {})
    for bn, bv in bones.items():
        if 'hover' in bn or 'mark' in bn:
            print('围棋动画标记骨骼', bn, json.dumps(bv, ensure_ascii=False)[:200])
            break
    pos = bones.get('cell_0_0', {})
    print('围棋 cell_0_0:', json.dumps(pos, ensure_ascii=False)[:200])
    break
