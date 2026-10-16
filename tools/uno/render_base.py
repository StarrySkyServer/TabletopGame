"""Scene evaluator + renderer for the Doudizhu card-table display.

Builds the exact 3D scene the client draws (table blocks + cards + buttons),
then renders (a) a side elevation cross-section and (b) a 3D player's view.
A `patch` dict can rewrite the layout molang so we can preview a fix.
"""
import json, math, re, os
from PIL import Image, ImageDraw, ImageFont, ImageChops

import os
BS = chr(92)
RP = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..",
                  "src/main/resources/assets/resource_pack")
GEO = json.load(open(os.path.join(RP, "models/entity/uno/uno_table.geo.json"),
                     encoding="utf-8"))["minecraft:geometry"][0]
LAYOUT_SRC = json.load(open(os.path.join(RP, "animations/uno/uno_table.animation.json"),
                            encoding="utf-8"))["animations"]["animation.tabletopgame.uno.layout"]["bones"]
ATLAS = Image.open(os.path.join(RP, "textures/tabletopgame/uno/uno_atlas.png")).convert("RGBA")
APX = ATLAS.load()
ATW, ATH = ATLAS.size

# ----------------------------------------------------------------- Molang eval
_TOK = re.compile(r"""
    \s*(?:
      (?P<num>\d+\.\d*|\.\d+|\d+)
    | (?P<id>[A-Za-z_][A-Za-z_0-9]*(?:\.[A-Za-z_][A-Za-z_0-9]*)*)
    | (?P<op><=|>=|==|!=|&&|\|\||[?():,+\-*/%<>!])
    )""", re.X)


def mod(a, b):
    return math.fmod(a, b) if b else 0.0


def _tokenize(s):
    out, i = [], 0
    while i < len(s):
        m = _TOK.match(s, i)
        if not m:
            raise ValueError("tokenize %r" % s[i:i + 30])
        i = m.end()
        if m.group('num'):
            out.append(('num', float(m.group('num'))))
        elif m.group('id'):
            out.append(('id', m.group('id')))
        else:
            out.append(('op', m.group('op')))
    return out


class _P:
    def __init__(self, toks, V):
        self.t, self.i, self.V = toks, 0, V

    def peek(self):
        return self.t[self.i] if self.i < len(self.t) else (None, None)

    def eat(self, v=None):
        k, val = self.peek()
        if v is not None and val != v:
            raise ValueError("want %r got %r" % (v, val))
        self.i += 1
        return val

    def expr(self):
        c = self.or_()
        if self.peek()[1] == '?':
            self.eat('?')
            a = self.expr()
            self.eat(':')
            b = self.expr()
            return a if c else b
        return c

    def or_(self):
        v = self.and_()
        while self.peek()[1] == '||':
            self.eat()
            r = self.and_()
            v = 1 if (v or r) else 0
        return v

    def and_(self):
        v = self.cmp_()
        while self.peek()[1] == '&&':
            self.eat()
            r = self.cmp_()
            v = 1 if (v and r) else 0
        return v

    def cmp_(self):
        v = self.add()
        if self.peek()[1] in ('==', '!=', '<=', '>=', '<', '>'):
            op = self.eat()
            r = self.add()
            v = 1 if {'==': v == r, '!=': v != r, '<=': v <= r,
                      '>=': v >= r, '<': v < r, '>': v > r}[op] else 0
        return v

    def add(self):
        v = self.mul()
        while self.peek()[1] in ('+', '-'):
            op = self.eat()
            r = self.mul()
            v = v + r if op == '+' else v - r
        return v

    def mul(self):
        v = self.unary()
        while self.peek()[1] in ('*', '/', '%'):
            op = self.eat()
            r = self.unary()
            if op == '*':
                v = v * r
            elif op == '/':
                # 与 Molang 对齐：**除数为 0 时静默取 0**（客户端不会崩，离线的求值器也不该崩）。
                # 真实用例：手牌只剩 1 张时 `35.2/(v.f0n-1)` 分母为 0，客户端一直这么跑。
                v = 0.0 if r == 0 else v / r
            else:
                v = mod(v, r)
        return v

    def unary(self):
        if self.peek()[1] == '-':
            self.eat()
            return -self.unary()
        if self.peek()[1] == '!':
            self.eat()
            return 0 if self.unary() else 1
        return self.primary()

    def primary(self):
        k, val = self.peek()
        if k == 'num':
            self.eat()
            return val
        if k == 'id':
            self.eat()
            name = val
            if self.peek()[1] == '(':
                self.eat('(')
                args = []
                if self.peek()[1] != ')':
                    args.append(self.expr())
                    while self.peek()[1] == ',':
                        self.eat(',')
                        args.append(self.expr())
                self.eat(')')
                fn = name.split('.')[-1]
                if fn == 'mod':
                    return mod(args[0], args[1])
                if fn == 'floor':
                    return math.floor(args[0])
                if fn == 'ceil':
                    return math.ceil(args[0])
                if fn == 'abs':
                    return abs(args[0])
                if fn == 'min':
                    return min(args)
                if fn == 'max':
                    return max(args)
                # Molang 的三角函数**吃角度**（math.sin(180) = 0），不是弧度 ——
                # 与 math.pi 无关，别按一般语言的习惯改成 radians。
                if fn == 'sin':
                    return math.sin(math.radians(args[0]))
                if fn == 'cos':
                    return math.cos(math.radians(args[0]))
                if fn == 'pow':
                    return args[0] ** args[1]
                if fn == 'clamp':
                    return max(args[1], min(args[2], args[0]))
                if fn == 'sqrt':
                    return math.sqrt(max(0.0, args[0]))
                if fn == 'round':
                    return float(round(args[0]))
                raise ValueError(fn)
            if name.startswith('v.'):
                return self.V[name[2:]]
            if name.startswith('q.'):
                return 0.0166
            return 1 if name == 'true' else 0
        if val == '(':
            self.eat('(')
            v = self.expr()
            self.eat(')')
            return v
        raise ValueError("token %r" % (val,))


def ev(e, V):
    return _P(_tokenize(e), V).expr()


class Vars(dict):
    """dict that yields 0 for undefined variables (and remembers which)."""
    missing = set()

    def __missing__(self, k):
        Vars.missing.add(k)
        return 0.0


# ----------------------------------------------------------------- scene build
def build_vars(viewer_mode, hands, plays, deck, sel_maps, hover=0):
    V = Vars({"viewer_mode": viewer_mode})
    zones = [0] * 54
    slot = 0
    for s in range(3):
        for _ in range(hands[s]):
            zones[slot] = 1 + s
            slot += 1
    for s in range(3):
        for _ in range(plays[s]):
            zones[slot] = 4 + s
            slot += 1
    for _ in range(deck):
        zones[slot] = 7
        slot += 1
    for i in range(54):
        V["z%d" % i] = zones[i]
    for i in range(54):
        V["sel%d" % i] = 0
    for i in range(54):
        V["fly_src%d" % i] = 0
    for i in range(54):
        V["hr%d" % i] = 0
    V["hr_zone0"] = 0
    V["pk_sel0"], V["pk_sel1"], V["pk_sel2"] = sel_maps
    V["pk_hover"] = hover
    V["pk_controls"] = 0

    p = [0, 0, 0]
    plays_c = [0, 0, 0]
    dc = 0
    for i in range(54):
        z = zones[i]
        V["s%d" % i] = {1: p[0], 2: p[1], 3: p[2], 4: plays_c[0], 5: plays_c[1],
                        6: plays_c[2], 7: dc}.get(z, 0)
        if 1 <= z <= 3:
            p[z - 1] += 1
        elif 4 <= z <= 6:
            plays_c[z - 4] += 1
        elif z == 7:
            dc += 1
    V["p0c"], V["p1c"], V["p2c"] = p
    V["c0c"], V["c1c"], V["c2c"] = plays_c
    V["dc"] = dc
    for k, c in zip(("p0sp", "p1sp", "p2sp"), p):
        V[k] = 0 if c <= 1 else min(2.8, 35.2 / (c - 1))
    for k, c in zip(("c0", "c1", "c2"), plays_c):
        r = math.ceil(c / 2) if c > 10 else (c if c > 0 else 1)
        V[k + "r"] = r
        V[k + "sp"] = 0 if r <= 1 else min(3.4, 30.0 / (r - 1))
    # hand rows spread
    for i in range(54):
        z = zones[i]
        if 1 <= z <= 3:
            V["hr%d" % i] = (V["s%d" % i] - (V["p%d" % (z - 1) + "c"] - 1) / 2.0) * V["p%dsp" % (z - 1)]
    V["button_0"] = 5
    V["button_1"] = 6
    V["button_2"] = 7
    V["button_3"] = 8
    n = 4
    acc = 0
    for k in range(4):
        V["button_offset_%d" % k] = (acc - (n - 1) / 2.0) * 6.6
        acc += 1
    V["button_count"] = n
    return V, zones


def apply_patches(patches):
    out = {}
    for name, entry in LAYOUT_SRC.items():
        if not isinstance(entry, dict):
            out[name] = entry
            continue
        e = json.loads(json.dumps(entry))
        for key in ("position", "rotation", "scale"):
            if key in e and isinstance(e[key], list):
                for i, v in enumerate(e[key]):
                    if isinstance(v, str):
                        for old, new in patches:
                            if old in v:
                                v = v.replace(old, new)
                        e[key][i] = v
            elif key in e and isinstance(e[key], str):
                v = e[key]
                for old, new in patches:
                    if old in v:
                        v = v.replace(old, new)
                e[key] = v
        out[name] = e
    return out


def bone_transform(anim, name, V):
    e = anim.get(name)
    if e is None:
        # 动画里没写这根骨骼 = 单位变换（客户端同样如此）：典型是 bot_head_N，
        # 它只跟着父骨骼 bot_N 走，自己不需要动画条目。
        return {"position": [0.0, 0.0, 0.0], "rotation": [0.0, 0.0, 0.0],
                "scale": [1.0, 1.0, 1.0]}
    res = {}
    for key, dflt in (("position", [0, 0, 0]), ("rotation", [0, 0, 0]), ("scale", [1, 1, 1])):
        if key not in e:
            res[key] = dflt
            continue
        raw = e[key]
        if not isinstance(raw, list):
            raw = [raw, raw, raw]
        res[key] = [ev(x, V) if isinstance(x, str) else float(x) for x in raw]
    return res


def rot_pt(p, R, P):
    rx, ry, rz = [math.radians(a) for a in R]
    x, y, z = p
    y, z = y * math.cos(rx) - z * math.sin(rx), y * math.sin(rx) + z * math.cos(rx)
    x, z = x * math.cos(ry) + z * math.sin(ry), -x * math.sin(ry) + z * math.cos(ry)
    x, y = x * math.cos(rz) - y * math.sin(rz), x * math.sin(rz) + y * math.cos(rz)
    return (x + P[0], y + P[1], -(z + P[2]))


CUBES = {b["name"]: b.get("cubes", []) for b in GEO["bones"]}


def eff_scale(anim, name, V):
    """骨骼的有效 scale = 自身 × 全部祖先（Bedrock 的骨骼 scale 会被子骨骼继承）。

    布局动画里 `fake_vis_N` / `buttons_visibility` 这类"开关骨骼"自己没有立方体，
    完全靠把 scale 打成 0 来隐藏整棵子树。只读自身 scale 会让被关掉的子树照画，
    表现是"自己座位的 `?` 牌背盖在真牌上面"——一度让人误以为牌面朝向反了。
    """
    s = 1.0
    cur = name
    while cur is not None:
        if cur in anim:
            s *= bone_transform(anim, cur, V)["scale"][0]
            if abs(s) < 1e-9:
                return 0.0
        cur = PARENT.get(cur)
    return s

FACE_DEF = [
    ("north", [(0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0)]),
    ("south", [(0, 0, 1), (1, 0, 1), (1, 1, 1), (0, 1, 1)]),
    ("west", [(0, 0, 0), (0, 0, 1), (0, 1, 1), (0, 1, 0)]),
    ("east", [(1, 0, 0), (1, 0, 1), (1, 1, 1), (1, 1, 0)]),
    # up：面内 (s,t) 的第 4 个分量对应贴图的 v（向下），实际客户端里 v 沿 **-z** 走。
    # 这里若写成 +z，按钮的中文会上下颠倒（用 tools/uno 里对按钮文字的经验对拍确定）。
    ("up", [(0, 1, 1), (1, 1, 1), (1, 1, 0), (0, 1, 0)]),
    ("down", [(0, 0, 0), (1, 0, 0), (1, 0, 1), (0, 0, 1)]),
]
NORMAL = {"north": (0, 0, -1), "south": (0, 0, 1), "west": (-1, 0, 0),
          "east": (1, 0, 0), "up": (0, 1, 0), "down": (0, -1, 0)}


def face_color(uvdef, fallback=(200, 200, 200, 255)):
    if not isinstance(uvdef, dict):
        return fallback
    u, v = uvdef.get("uv", [0, 0])
    uw, uh = uvdef.get("uv_size", [1, 1])
    u = max(0, min(ATW - 1, int(u)))
    v = max(0, min(ATH - 1, int(v)))
    uw = max(1, min(ATW - u, int(abs(uw))))
    uh = max(1, min(ATH - v, int(abs(uh))))
    sub = ATLAS.crop((u, v, u + uw, v + uh))
    px = list(sub.resize((4, 4)).getdata())
    opaque = [p for p in px if p[3] > 10]
    if not opaque:
        return fallback
    r = sum(p[0] for p in opaque) // len(opaque)
    g = sum(p[1] for p in opaque) // len(opaque)
    b = sum(p[2] for p in opaque) // len(opaque)
    return (r, g, b, 255)


def box_uv(c, s):
    """Expand a cube's box-UV [u,v] into per-face uv dicts (Bedrock layout)."""
    uv = c.get("uv")
    if not isinstance(uv, list) or len(uv) < 2:
        return c.get("uv") if isinstance(c.get("uv"), dict) else {}
    u, v = uv
    w, h, d = abs(s[0]), abs(s[1]), abs(s[2])
    k = c.get("uv_size")
    if isinstance(k, list) and len(k) >= 2 and (abs(k[0]) < 1 or abs(k[1]) < 1):
        w, h, d = w * abs(k[0]), h * abs(k[1]), d * abs(k[0])
    return {
        "north": {"uv": [u + d, v + d], "uv_size": [w, h]},
        "east": {"uv": [u, v + d], "uv_size": [d, h]},
        "south": {"uv": [u + d + w, v + d], "uv_size": [w, h]},
        "west": {"uv": [u + d + w + d, v + d], "uv_size": [d, h]},
        "up": {"uv": [u + d, v], "uv_size": [w, d]},
        "down": {"uv": [u + d + w, v], "uv_size": [w, d]},
    }


def collect_scene(anim, V):
    """-> (faces, 0.0, add_cube)。每个面是 (pts, col, n, uvq)，uvq 供贴图渲染用。"""
    faces = []
    cache = {}

    def add_cube(name, visible=True, color_override=None):
        if not visible:
            return
        M = world_of(anim, name, V, cache)
        S = bone_transform(anim, name, V)["scale"]
        for c in CUBES.get(name, []):
            o, s = c["origin"], c["size"]
            uv = box_uv(c, s) if not isinstance(c.get("uv"), dict) else c.get("uv", {})
            for fname, idx in FACE_DEF:
                pts = []
                for (ix, iy, iz) in idx:
                    p = ((o[0] + s[0] * ix) * S[0], (o[1] + s[1] * iy) * S[1],
                         (o[2] + s[2] * iz) * S[2])
                    pts.append(apex(M, p))
                col = color_override or face_color(uv.get(fname))
                n = dir_of(M, NORMAL[fname])
                faces.append((pts, col, n, tex_quad(uv.get(fname))))
    return faces, 0.0, add_cube


def tex_quad(uvdef):
    """把某个面的 uv 定义转成 (裁剪框 (x,y,w,h), 四个角的图块内坐标)。

    FACE_DEF 里每个面的 4 个角在面内一律是 (0,0)(1,0)(1,1)(0,1)，
    因此这里只需给出对应的图块像素坐标；uv_size 允许为负（Bedrock 用它做翻转），
    负值会被自然吸收进「角坐标 → 裁剪框」的换算里。
    """
    if not isinstance(uvdef, dict):
        return None
    u, v = uvdef.get("uv", [0, 0])
    uw, vh = uvdef.get("uv_size", [1, 1])
    if uw == 0 or vh == 0:
        return None
    x0, x1 = u, u + uw
    y0, y1 = v, v + vh
    cx, cy = min(x0, x1), min(y0, y1)
    cw, ch = abs(uw), abs(vh)
    if cw < 1 or ch < 1:
        return None
    if cx < 0 or cy < 0 or cx + cw > ATW or cy + ch > ATH:
        return None
    # 面内 (s,t) -> 图块内坐标（相对裁剪框左上角）
    return ((cx, cy, cw, ch),
            [(x0 + s * (x1 - x0) - cx, y0 + t * (y1 - y0) - cy)
             for (s, t) in ((0, 0), (1, 0), (1, 1), (0, 1))])


def render_perspective(faces, eye, target, W=1120, H=720, fov=62):
    ex, ey, ez = eye
    tx, ty, tz = target
    fwd = (tx - ex, ty - ey, tz - ez)
    fl = math.sqrt(sum(c * c for c in fwd))
    fwd = tuple(c / fl for c in fwd)
    up0 = (0, 1, 0)
    right = (fwd[1] * up0[2] - fwd[2] * up0[1], fwd[2] * up0[0] - fwd[0] * up0[2],
             fwd[0] * up0[1] - fwd[1] * up0[0])
    rl = math.sqrt(sum(c * c for c in right)) or 1
    right = tuple(c / rl for c in right)
    up = (right[1] * fwd[2] - right[2] * fwd[1], right[2] * fwd[0] - right[0] * fwd[2],
          right[0] * fwd[1] - right[1] * fwd[0])
    f = 1.0 / math.tan(math.radians(fov) / 2)

    def proj(p):
        d = (p[0] - ex, p[1] - ey, p[2] - ez)
        z = sum(d[i] * fwd[i] for i in range(3))
        if z < 0.05:
            return None
        x = sum(d[i] * right[i] for i in range(3))
        y = sum(d[i] * up[i] for i in range(3))
        sx = W / 2 + (x / z) * f * (H / 2)
        sy = H / 2 - (y / z) * f * (H / 2)
        return (sx, sy, z)

    img = Image.new("RGB", (W, H), (16, 18, 24))
    dr = ImageDraw.Draw(img)
    work = []
    for f in faces:
        pts, col, n = f[0], f[1], f[2]
        pp = [proj(p) for p in pts]
        if any(v is None for v in pp):
            continue
        zc = sum(v[2] for v in pp) / 4
        # backface cull
        cx = sum(p[0] for p in pts) / 4 - ex
        cy = sum(p[1] for p in pts) / 4 - ey
        cz = sum(p[2] for p in pts) / 4 - ez
        if n[0] * cx + n[1] * cy + n[2] * cz > 0:
            continue
        light = max(0.35, min(1.0, 0.55 + 0.45 * (n[1] * 0.8 + 0.2)))
        c = tuple(int(min(255, ch * light)) for ch in col[:3])
        work.append((zc, [v[:2] for v in pp], c))
    work.sort(key=lambda t: -t[0])
    for _, poly, c in work:
        dr.polygon(poly, fill=c)
    return img


# ------------------------------------------------------------------ 贴图渲染
def _solve8(A, b):
    """8 元线性方程组的高斯消元（带部分选主元）。"""
    n = 8
    M = [list(A[i]) + [b[i]] for i in range(n)]
    for col in range(n):
        p = max(range(col, n), key=lambda r: abs(M[r][col]))
        if abs(M[p][col]) < 1e-12:
            return None
        M[col], M[p] = M[p], M[col]
        pv = M[col][col]
        M[col] = [v / pv for v in M[col]]
        for r in range(n):
            if r != col and M[r][col] != 0.0:
                f = M[r][col]
                M[r] = [M[r][k] - f * M[col][k] for k in range(n + 1)]
    return [M[i][n] for i in range(n)]


def perspective_coeffs(dst, src):
    """PIL Image.PERSPECTIVE 的 8 个系数：把输出像素坐标映射回源图坐标。

    dst = 屏幕上这个面的 4 个角，src = 对应角在贴图里的像素坐标。
    """
    A, b = [], []
    for (x, y), (u, v) in zip(dst, src):
        A.append([x, y, 1, 0, 0, 0, -u * x, -u * y])
        b.append(u)
        A.append([0, 0, 0, x, y, 1, -v * x, -v * y])
        b.append(v)
    return _solve8(A, b)


def render_textured(faces, eye, target, W=1120, H=720, fov=62, bg=(16, 18, 24),
                    cull=True):
    """带真实贴图采样的透视渲染（画家算法，从远到近贴）。

    与 render_perspective 的区别：不再用平均色填充，而是把图集里的图块按
    透视变换贴到每个面上，因此能看到牌面花色、牌背花纹、按钮文字。
    """
    ex, ey, ez = eye
    tx, ty, tz = target
    fwd = (tx - ex, ty - ey, tz - ez)
    fl = math.sqrt(sum(c * c for c in fwd))
    fwd = tuple(c / fl for c in fwd)
    up0 = (0, 1, 0)
    right = (fwd[1] * up0[2] - fwd[2] * up0[1], fwd[2] * up0[0] - fwd[0] * up0[2],
             fwd[0] * up0[1] - fwd[1] * up0[0])
    rl = math.sqrt(sum(c * c for c in right)) or 1
    right = tuple(c / rl for c in right)
    up = (right[1] * fwd[2] - right[2] * fwd[1], right[2] * fwd[0] - right[0] * fwd[2],
          right[0] * fwd[1] - right[1] * fwd[0])
    f = 1.0 / math.tan(math.radians(fov) / 2)

    def proj(p):
        d = (p[0] - ex, p[1] - ey, p[2] - ez)
        z = sum(d[i] * fwd[i] for i in range(3))
        if z < 0.06:
            return None
        x = sum(d[i] * right[i] for i in range(3))
        y = sum(d[i] * up[i] for i in range(3))
        return (W / 2 + (x / z) * f * (H / 2), H / 2 - (y / z) * f * (H / 2), z)

    img = Image.new("RGB", (W, H), bg)
    painter = []
    for fa in faces:
        pts, n, uvq = fa[0], fa[2], (fa[3] if len(fa) > 3 else None)
        if uvq is None:
            continue
        pp = [proj(p) for p in pts]
        if any(v is None for v in pp):
            continue
        cx = sum(p[0] for p in pts) / 4 - ex
        cy = sum(p[1] for p in pts) / 4 - ey
        cz = sum(p[2] for p in pts) / 4 - ez
        if cull and n[0] * cx + n[1] * cy + n[2] * cz > 0:
            continue
        xs = [v[0] for v in pp]
        ys = [v[1] for v in pp]
        x0, x1 = max(0, int(math.floor(min(xs)))), min(W, int(math.ceil(max(xs))) + 1)
        y0, y1 = max(0, int(math.floor(min(ys)))), min(H, int(math.ceil(max(ys))) + 1)
        if x1 - x0 < 1 or y1 - y0 < 1:
            continue
        light = max(0.35, min(1.0, 0.55 + 0.45 * (n[1] * 0.8 + 0.2)))
        painter.append((sum(v[2] for v in pp) / 4, pp, uvq, light, (x0, y0, x1, y1)))
    painter.sort(key=lambda t: -t[0])

    for _, pp, uvq, light, (x0, y0, x1, y1) in painter:
        rect, src = uvq
        dst = [(v[0] - x0, v[1] - y0) for v in pp]
        co = perspective_coeffs(dst, src)
        if co is None:
            continue
        tile = ATLAS.crop((rect[0], rect[1], rect[0] + rect[2], rect[1] + rect[3]))
        bw, bh = x1 - x0, y1 - y0
        try:
            warped = tile.transform((bw, bh), Image.PERSPECTIVE, co, resample=Image.BILINEAR)
        except (ValueError, ZeroDivisionError):
            continue
        # 面内掩码（四边形内）+ 贴图自带 alpha
        mv = Image.new("L", (bw, bh), 0)
        ImageDraw.Draw(mv).polygon([(v[0] - x0, v[1] - y0) for v in pp], fill=255)
        alpha = warped.getchannel("A").point(lambda v: 255 if v > 24 else 0)
        alpha = ImageChops.multiply(alpha, mv)
        if light < 0.999:
            lut = [min(255, int(i * light)) for i in range(256)]
            r, g, b, a = warped.split()
            warped = Image.merge("RGBA", (r.point(lut), g.point(lut), b.point(lut), a))
        img.paste(warped.convert("RGB"), (x0, y0), alpha)
    return img


def _clip_axis(poly, axis, bound, keep_less):
    """Sutherland-Hodgman clip of a 3D polygon against axis <= bound (or >=)."""
    out = []

    def inside(p):
        return p[axis] <= bound if keep_less else p[axis] >= bound

    n = len(poly)
    for i in range(n):
        a, b = poly[i], poly[(i + 1) % n]
        ia, ib = inside(a), inside(b)
        if ia:
            out.append(a)
        if ia != ib:
            t = (bound - a[axis]) / (b[axis] - a[axis])
            out.append(tuple(a[k] + (b[k] - a[k]) * t for k in range(3)))
    return out


def render_elevation(faces, W=1080, H=600, zr=(-31, 7), yr=(-17, 14), slab=4.0):
    """side cross-section: clip to |x| <= slab, project onto the Y-Z plane."""
    z0, z1 = zr
    y0, y1 = yr
    sc = min((W - 90) / (z1 - z0), (H - 70) / (y1 - y0))
    ox = 60
    oy = 40

    def proj(p):
        return (ox + (p[2] - z0) * sc, H - oy - (p[1] - y0) * sc)

    img = Image.new("RGB", (W, H), (20, 22, 28))
    dr = ImageDraw.Draw(img)
    for z in range(z0, z1 + 1):
        if z % 5 == 0:
            x = proj((0, 0, z))[0]
            dr.line([x, 0, x, H], fill=(38, 42, 52))
    for y in range(y0, y1 + 1):
        if y % 5 == 0:
            yy = proj((0, y, 0))[1]
            dr.line([0, yy, W, yy], fill=(38, 42, 52))

    sel = []
    for f in faces:
        pts, col = f[0], f[1]
        poly = _clip_axis(pts, 0, slab, True)
        poly = _clip_axis(poly, 0, -slab, False) if poly else []
        if len(poly) < 3:
            continue
        d = sum(p[0] for p in poly) / len(poly)
        sel.append((d, poly, col))
    sel.sort(key=lambda t: -t[0])
    for _, poly, col in sel:
        dr.polygon([proj(p) for p in poly], fill=col[:3], outline=(16, 18, 24))
    return img, proj, sc


def rot_mat(R):
    # **俯仰角取负**：客户端对 pitch 的旋转方向与本文件的 Rx 定义相反。
    # 依据：把 ddz/UNO 的手牌长轴与它们各自 TableRay.cardUp 对拍，只有 Rx(-pitch)
    # 能让两者精确重合、且牌面法线指向该座位玩家（= 生产环境确实可见牌面）。
    # 取 Rx(+pitch) 会把整个场景沿俯仰方向镜像，渲染出"牌背朝玩家"的假象。
    rx, ry, rz = [-math.radians(R[0]), math.radians(R[1]), math.radians(R[2])]
    cx, sx = math.cos(rx), math.sin(rx)
    cy, sy = math.cos(ry), math.sin(ry)
    cz, sz = math.cos(rz), math.sin(rz)
    Rx = [[1, 0, 0], [0, cx, -sx], [0, sx, cx]]
    Ry = [[cy, 0, sy], [0, 1, 0], [-sy, 0, cy]]
    Rz = [[cz, -sz, 0], [sz, cz, 0], [0, 0, 1]]

    def mm(A, B):
        return [[sum(A[i][k] * B[k][j] for k in range(3)) for j in range(3)] for i in range(3)]
    return mm(Rz, mm(Ry, Rx))


def mat_mul(A, B):
    R1, T1 = A
    R2, T2 = B
    R = [[sum(R1[i][k] * R2[k][j] for k in range(3)) for j in range(3)] for i in range(3)]
    T = [sum(R1[i][k] * T2[k] for k in range(3)) + T1[i] for i in range(3)]
    return (R, T)


PARENT = {b["name"]: b.get("parent") for b in GEO["bones"]}


def world_of(anim, name, V, cache):
    if name in cache:
        return cache[name]
    t = bone_transform(anim, name, V)
    local = (rot_mat(t["rotation"]), list(t["position"]))
    p = PARENT.get(name)
    res = local if (p is None or p not in anim) else mat_mul(world_of(anim, p, V, cache), local)
    cache[name] = res
    return res


def apex(M, p):
    """模型空间点 -> 世界点。实体局部 z = 世界 -z（yaw=0，见 TableRay.java）。"""
    R, T = M
    x = sum(R[0][k] * p[k] for k in range(3)) + T[0]
    y = sum(R[1][k] * p[k] for k in range(3)) + T[1]
    z = sum(R[2][k] * p[k] for k in range(3)) + T[2]
    return (x, y, -z)


def dir_of(M, v):
    """Direction transform: rotation only, **but z must be mirrored like apex does**.

    apex() 把模型空间 z 取反后才得到世界坐标，所以方向向量也必须取反，
    否则这里返回的是"模型空间法线"，却拿去和"世界空间"的 (面心-眼睛) 比，
    背面剔除会在两个坐标系之间混用，渲染出错误的面。
    """
    R = M[0]
    x, y, z = (sum(R[i][k] * v[k] for k in range(3)) for i in range(3))
    return (x, y, -z)


def bone_aabb(anim, name, V, cache=None):
    cache = {} if cache is None else cache
    M = world_of(anim, name, V, cache)
    t = bone_transform(anim, name, V)
    S = t["scale"]
    pts = []
    for c in CUBES.get(name, []):
        o, s = c["origin"], c["size"]
        for ix in (0, 1):
            for iy in (0, 1):
                for iz in (0, 1):
                    p = ((o[0] + s[0] * ix) * S[0], (o[1] + s[1] * iy) * S[1], (o[2] + s[2] * iz) * S[2])
                    pts.append(apex(M, p))
    if not pts:
        return None
    return ([min(p[i] for p in pts) for i in range(3)],
            [max(p[i] for p in pts) for i in range(3)])




def annotate_elevation(img, proj, sc, texts):
    dr = ImageDraw.Draw(img)
    try:
        f = ImageFont.truetype("C:/Windows/Fonts/msyh.ttc", 15)
        fb = ImageFont.truetype("C:/Windows/Fonts/msyh.ttc", 19)
    except Exception:
        f = fb = ImageFont.load_default()
    W, H = img.size

    def hline(y, col, txt, dash=True):
        yy = proj((0, y, 0))[1]
        if dash:
            x = 60
            while x < W:
                dr.line([x, yy, min(W, x + 9), yy], fill=col, width=1)
                x += 17
        else:
            dr.line([60, yy, W - 40, yy], fill=col, width=2)
        dr.text((W - 250, yy - 20), txt, font=f, fill=col)

    def vline(z, col, txt):
        xx = proj((0, 0, z))[0]
        y = 40
        while y < H - 40:
            dr.line([xx, y, xx, min(H - 40, y + 8)], fill=col, width=1)
            y += 15
        dr.text((xx + 4, H - 34), txt, font=f, fill=col)

    hline(0, (120, 220, 140), "Y = 0  绒布台面（桌面顶）")
    hline(1, (230, 180, 100), "Y = +1  木框顶面")
    hline(-15, (110, 115, 130), "Y = -15  方块底面", dash=False)
    vline(-21, (120, 220, 140), "绒布/木框分界 z=-21")
    vline(-24, (235, 120, 120), "桌沿 z=-24（方块外缘）")
    for i, (t, col) in enumerate(texts):
        dr.text((14, 8 + i * 24), t, font=fb, fill=col)
    return img



def label(img, texts, x=14, y=10, size=20):
    dr = ImageDraw.Draw(img)
    try:
        f = ImageFont.truetype("C:/Windows/Fonts/msyh.ttc", size)
    except Exception:
        f = ImageFont.load_default()
    for i, (t, col) in enumerate(texts):
        dr.text((x, y + i * (size + 6)), t, font=f, fill=col)
    return img
