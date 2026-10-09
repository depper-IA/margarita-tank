"""Dynamic rig parts: squashed / leaning torsos, variable legs and shadows, registered on demand."""
import math
from svgbuild import *
from art import *
import rig
from rig import PARTS, DESCR, BD, LT, SH, LN, SP, EYE, WH, P, torso_grid, leg_grid


def reg(name, grid, descr):
    if name not in PARTS:
        PARTS[name] = grid
        DESCR[name] = descr
    return name


def sg(v):
    return ("m" if v < 0 else "p") + str(abs(v))


def _shaded_mask_grid(mask):
    """Outline + the torso light/shade rules applied to an arbitrary mask (used for leaning bodies)."""
    g = Grid()
    paint(g, mask, BD, LN)
    def dist(x, y, dx, dy):
        n = 0
        while (x + dx * (n + 1), y + dy * (n + 1)) in mask and g.p[(x + dx * (n + 1), y + dy * (n + 1))] != LN:
            n += 1
        return n
    out = {}
    for (x, y), c in list(g.p.items()):
        if c == LN:
            continue
        du, dd, dl, dr = dist(x, y, 0, -1), dist(x, y, 0, 1), dist(x, y, -1, 0), dist(x, y, 1, 0)
        # distance to the outline in each direction (the outline pixel itself is not counted)
        d_up, d_dn, d_l, d_r = du, dd, dl, dr
        if d_dn <= 1 or d_r == 0:
            out[(x, y)] = SH
        elif d_up == 0 or d_l == 0:
            out[(x, y)] = LT
    g.p.update(out)
    return g


def torso_part(w, h, sa=0, sb=0, sc=0):
    """Torso w x h (top at row 12, centred on x = 15). sa / sb / sc: horizontal shift of the top 3 rows, the
    middle rows (where the pincers sit) and the bottom 3 rows, to fake a lean without rotating."""
    if sa == sb == sc == 0:
        name = f"torso-{w}x{h}" if (w, h) != (22, 14) else "torso"
        x0 = 15 - w // 2
        return reg(name, torso_grid((x0, 12, w, h)), f"body {w}x{h}")
    name = f"torso-{w}x{h}-l{sg(sa)}{sg(sb)}{sg(sc)}"
    if name in PARTS:
        return name
    x0 = 15 - w // 2
    nA = min(3, max(1, h // 4)); nC = min(3, max(1, h // 4))
    mask = set()
    for r in range(h):
        s = sa if r < nA else (sc if r >= h - nC else sb)
        for x in range(x0 + s, x0 + s + w):
            mask.add((x, 12 + r))
    g = _shaded_mask_grid(mask)
    # specular 2x1 on the first light row, 2 px from the left outline
    ry = 12 + 1
    row = sorted(x for (x, y) in mask if y == ry)
    if len(row) > 4:
        g.p[(row[1], ry + 1)] = SP if (row[1], ry + 1) in g.p and g.p[(row[1], ry + 1)] != LN else g.p.get((row[1], ry + 1))
        g.p[(row[2], ry + 1)] = SP if (row[2], ry + 1) in g.p and g.p[(row[2], ry + 1)] != LN else g.p.get((row[2], ry + 1))
    return reg(name, g, f"leaning body {w}x{h}")


def torso_edges(w, h, sa=0, sb=0, sc=0, dx=0):
    """(left outline col, right outline col) of the middle rows."""
    x0 = 15 - w // 2 + sb + dx
    return x0, x0 + w - 1


def leg_part(i, n):
    if n >= 12:
        return f"leg{i}"
    x = rig.LEG_X[i - 1]
    g = Grid()
    top = 30 - n
    g.R(x, top, 1, n, SH); g.R(x + 1, top, 1, n, LN); g.R(x, 29, 2, 1, LN)
    return reg(f"leg{i}-n{n}", g, f"leg {i}, {n} px long")


def shadow_part(w, strong=0.3, soft=0.15):
    g = Grid()
    x0 = 15 - w // 2
    g.R(x0, 30, w, 1, f"#000000@{strong}")
    if w > 6:
        g.R(x0 + 3, 31, w - 6, 1, f"#000000@{soft}")
    return reg(f"shadow-w{w}" + ("" if strong == 0.3 else f"-s{int(strong*100)}"), g, f"ground shadow {w} wide")


def var_el(a, tag, key_fn, part_fn):
    """Show exactly the part part_fn(key) for key = key_fn(k) on each frame (None hides)."""
    keys = []
    for k in range(a.n):
        key = key_fn(k)
        if key is not None and key not in keys:
            keys.append(key)
    parts = []
    for i, key in enumerate(keys):
        parts.append(a.vwrap(f"{tag}{i}", lambda k, key=key: key_fn(k) == key, use(part_fn(key))))
    return "\n".join(p for p in parts if p)


def legs_dyn(a, foot_fn, bot_fn, dx_fn=None, tag="lg", lift_fn=None):
    """Four legs; foot_fn(k) = foot row (29 = on the ground), bot_fn(k) = bottom edge of the torso (exclusive).
    lift_fn(k) -> per-leg extra lift list. Legs hidden behind the body are skipped."""
    out = []
    for i in range(1, 5):
        def foot(k, i=i):
            f = foot_fn(k)
            if lift_fn:
                f -= lift_fn(k)[i - 1]
            return f
        def n_of(k, i=i):
            f = foot(k)
            n = f - (bot_fn(k) - 3) + 1
            if f < bot_fn(k) or n < 1:
                return None
            return min(n, 12)
        keys = sorted({n_of(k) for k in range(a.n) if n_of(k)})
        for n in keys:
            part = leg_part(i, n)
            def mv(k, n=n, i=i):
                return ((dx_fn(k) if dx_fn else 0), foot(k) - 29)
            inner = use(part)
            vis = lambda k, n=n: n_of(k) == n
            moved = a.wrap(f"{tag}{i}m{n}", lambda k, mv=mv, vis=vis: mv(k) if vis(k) else (0, 0), inner)
            out.append(a.vwrap(f"{tag}{i}v{n}", vis, moved))
    return "\n".join(o for o in out if o)


def eyes_move(a, tag, state_fn, dx_fn=None, dy_fn=None):
    """Eye variants + one move wrapper. dy is relative to the default eye rows (16..19)."""
    inner = []
    states = []
    for k in range(a.n):
        s = state_fn(k)
        if s is not None and s not in states:
            states.append(s)
    for s in states:
        inner.append(a.vwrap(f"{tag}-{s}", lambda k, s=s: state_fn(k) == s, use(s)))
    el = "\n".join(i for i in inner if i)
    if dx_fn or dy_fn:
        el = a.wrap(f"{tag}-mv", lambda k: ((dx_fn(k) if dx_fn else 0), (dy_fn(k) if dy_fn else 0)), el)
    return el


# ---- extra eye / face parts used by the batch-A animations ----
def _eye_parts():
    g = Grid(); g.R(7, 19, 4, 1, EYE); g.R(19, 19, 4, 1, EYE)
    reg("eyes-slit", g, "eyes as flat 4 px slits")
    g = Grid()
    for x in (7, 19):
        g.R(x, 16, 4, 4, EYE); g.S(x, 16, WH)
    reg("eyes-blob", g, "eyes wide open, 4x4")
    g = Grid(); g.R(8, 18, 2, 1, EYE); g.R(20, 18, 2, 1, EYE)
    reg("eyes-shut-hi", g, "eyes shut, line at mid height")
    # x eyes
    g = Grid()
    for cx in (9, 21):
        for d in (-2, -1, 0, 1, 2):
            g.S(cx + d, 17 + d, EYE); g.S(cx + d, 17 - d, EYE)
    reg("eyes-x", g, "dizzy x eyes, 5x5")
    g = Grid(); g.R(8, 17, 2, 3, EYE); g.S(8, 17, WH); g.R(20, 17, 2, 3, EYE); g.S(20, 17, WH)
    reg("eyes-3", g, "eyes 2x3")
    g = Grid(); g.R(8, 18, 2, 2, EYE); g.R(20, 16, 2, 4, EYE); g.S(20, 16, WH)
    reg("eyes-focus", g, "eyes: left narrowed, right open (focused)")
    g = Grid(); g.R(8, 15, 2, 5, EYE); g.S(8, 15, WH); g.R(20, 15, 2, 5, EYE); g.S(20, 15, WH)
    reg("eyes-tall", g, "eyes 2x5 (same as eyes-wide)")


_eye_parts()


def rotate_grid(g, deg, cx, cy):
    """Nearest-neighbour rotation of a pixel grid (clockwise on screen) about (cx, cy); pixel centres, no blending."""
    if deg == 0:
        return g
    t = math.radians(deg)
    c, s = math.cos(t), math.sin(t)
    xs = [k[0] for k in g.p]; ys = [k[1] for k in g.p]
    r = int(max(max(xs) - min(xs), max(ys) - min(ys)) * 1.2) + 4
    out = Grid()
    for y in range(int(cy) - r, int(cy) + r):
        for x in range(int(cx) - r, int(cx) + r):
            dx, dy = x + .5 - cx, y + .5 - cy
            sx = cx + dx * c + dy * s          # inverse rotation
            sy = cy - dx * s + dy * c
            p = (int(math.floor(sx)), int(math.floor(sy)))
            if p in g.p:
                out.p[p and (x, y)] = g.p[p]
    return out
