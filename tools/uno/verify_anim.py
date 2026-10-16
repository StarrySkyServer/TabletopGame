# -*- coding: utf-8 -*-
"""离线校验 UNO 资源里全部 Molang 表达式能否解析并求值，并审计运算符优先级陷阱。

不开服务器、不看客户端，用 render_base 自带的 Molang 求值器（与 Bedrock 语义对齐）把
`uno_table.animation.json` 的每根骨骼表达式、`uno_table.entity.json` 的每条
pre_animation 语句逐一求值，任何解析失败/求值异常都会列出文件与骨骼名。

额外做一件求值本身查不出来的事：**优先级审计**。Molang 里 `?:` 的优先级低于 `+`/`*`，
所以 `A - 1*(cond?1:0)*0.9` 一旦漏掉那双括号，就会变成 `(A-1*cond) ? 1 : 0`（A≠0 时恒为 1）。
这种写法语法完全合法、求值也不报错，但整根骨骼会塌到常数上，是最难查的一类"影子 bug"。
审计规则：任一三元的**条件**里若含顶层（不去看括号内部）算术运算符，即判为可疑并报错。
斗地主没这个风险，是因为它的 `v.selN` 由 pre_animation 预先算成变量，用起来天然是原子项。

用法：python verify_anim.py
"""
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import render_base as R

HERE = os.path.dirname(os.path.abspath(__file__))
ANIM = os.path.join(R.RP, 'animations/uno/uno_table.animation.json')
ENT = os.path.join(R.RP, 'entity/uno/uno_table.entity.json')

bad = []
prec = []

# 求值器不支持字符串实参（q.property('name')），统一折叠成常量：本脚本只关心语法与求值是否成功，
# 属性真值由 verify_props.py 单独核对。顺带把赋值语句的左侧剥掉。
_PROP = re.compile(r"q\.property\(\s*'[^']*'\s*\)")
_ASSIGN = re.compile(r"^\s*(?:v\.[A-Za-z_][A-Za-z0-9_]*\s*=|return\s+)")
_ARITH = ('+', '-', '*', '/', '%')


def audit_prec(stmt, where):
    """报告「三元条件里含顶层算术运算符」的可疑写法。

    做法：按括号深度分桶，每桶记下"当前分支里已出现的顶层算术运算符"。
    - 进 `(`  → 新深度，运算符列表清空；
    - 出 `)`  → 回到父深度，**父深度的运算符列表保留**（这是关键：`A-1*(c)?1:0`
      的条件以 `)` 收尾，若在 `)` 处清空就会漏判）；
    - `?`     → 检查当前深度是否残留过算术运算符，有则判可疑，然后清空；
    - `:` `,` `;` → 清空当前深度（进入新分支）。
    """
    try:
        toks = R._tokenize(stmt)
    except Exception:                            # noqa: BLE001
        return                                   # 语法错误由 check() 单独报告
    start = {0: 0}
    ops = {0: []}
    depth = 0
    for i, (kind, val) in enumerate(toks):
        if val == '(':
            depth += 1
            start[depth], ops[depth] = i + 1, []
        elif val == ')':
            # 只回父深度，**不清** start/ops：`A-1*(c)?1:0` 的条件以 `)` 收尾，
            # 若在此处重置，条件里的 `-`/`*` 会被抹掉，正好漏判目标模式。
            if depth > 0:
                depth -= 1
        elif val in (':', ',', ';'):
            start[depth], ops[depth] = i + 1, []
        elif val == '?':
            if ops[depth]:
                txt = ' '.join(str(t) for _, t in toks[start[depth]:i])
                prec.append((where, txt[:160]))
            start[depth], ops[depth] = i + 1, []
        elif kind == 'op' and val in _ARITH:
            ops[depth].append(val)


def check(expr, where):
    if not isinstance(expr, str):
        return
    e = _PROP.sub('0', expr).strip()
    if not e:
        return
    for stmt in e.split(';'):
        stmt = _ASSIGN.sub('', stmt).strip().rstrip(';')
        if not stmt:
            continue
        try:
            R.ev(stmt, R.Vars({}))
        except Exception as exc:                # noqa: BLE001
            bad.append((where, stmt, '%s: %s' % (type(exc).__name__, exc)))
        audit_prec(stmt, where)


def walk(node, where):
    if isinstance(node, dict):
        for k, v in node.items():
            walk(v, where + '/' + str(k))
    elif isinstance(node, list):
        for i, v in enumerate(node):
            walk(v, where + '[%d]' % i)
    else:
        check(node, where)


def main():
    with open(ANIM, encoding='utf-8') as fh:
        doc = json.load(fh)
    total_anim = 0
    for anim_name, anim in doc['animations'].items():
        for bone, spec in anim.get('bones', {}).items():
            total_anim += 1
            walk(spec, '%s/%s' % (anim_name, bone))

    with open(ENT, encoding='utf-8') as fh:
        ent = json.load(fh)
    desc = ent['minecraft:client_entity']['description']
    pa = desc['scripts']['pre_animation']
    total_pa = 0
    for i, line in enumerate(pa):
        for stmt in line.split(';'):
            if stmt.strip():
                total_pa += 1
        check(line, 'pre_animation[%d]' % i)
    # animate / initialize 里的表达式也过一遍
    for key in ('initialize', 'animate'):
        for i, v in enumerate(desc['scripts'].get(key, [])):
            if isinstance(v, dict):
                walk(v, 'scripts.%s[%d]' % (key, i))
            else:
                check(v, 'scripts.%s[%d]' % (key, i))

    print('animation bones checked : %d' % total_anim)
    print('pre_animation statements : %d' % total_pa)
    print('total bad : %d' % len(bad))
    for where, expr, err in bad[:40]:
        print('  BAD %s\n      %s\n      %s' % (where, expr[:160], err))
    print('ternary precedence suspects : %d' % len(prec))
    for where, txt in prec[:20]:
        print('  SUSPECT %s\n      %s' % (where, txt))
    return 1 if (bad or prec) else 0


if __name__ == '__main__':
    sys.exit(main())
