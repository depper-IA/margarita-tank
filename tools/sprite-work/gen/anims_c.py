"""Batch A: wake, low_battery, hat_mishap, confused, dizzy, sweeping, alert (v2 redraws on the shared rig)."""
import math
from svgbuild import *
from props import *
from pose import *
from anims_a import u2a


def even(v, lo=16, hi=30):
    v = int(round(v / 2.0)) * 2
    return max(lo, min(hi, v))


def body_geom(k_top, k_bot, w, sa=0, sb=0, sc=0, dx=0):
    h = k_bot - k_top
    return (torso_edges(w, h, sa, sb, sc, dx), h)


def claw_pos(side, eL, eR, top, h, dxc=0, dyc=0, bottom_cap=29):
    """Offset from the rest spot for a pincer sitting centred on the body side (clamped above the ground)."""
    ct = top + (h - 8) // 2 + dyc
    ct = min(ct, bottom_cap - 7)
    if side == "L":
        return (eL - 4 + dxc, ct - 15)
    return (eR - 25 + dxc, ct - 15)


def lean_of(rot_deg, top):
    return math.sin(math.radians(rot_deg)) * (30 - top)


def lean_split(L):
    return rhu(L), rhu(L * 0.6), rhu(L * 0.2)


# ---------------------------------------------------------------- wake
def build_wake():
    FPS, N = 8, 12
    a = Anim(FPS, N)
    pc = lambda k: 100.0 * k / N
    LIN = LINEAR
    bm = kf([(0, (0, 1, 1, 0)), (6.667, (.35, 1.03, .96, 0)), (20, (-2.6, .98, 1.04, -6)), (33.333, (-4.1, .9, 1.22, 2)),
             (46.667, (-2, .95, 1.11, 0)), (54, (-.55, 1.02, .98, -4)), (60, (-.2, .99, 1.02, 2.5)), (66.667, (0, 1, 1, 0)), (100, (0, 1, 1, 0))])
    tsh = kf([(0, (-1, 4)), (8, (-.82, 3.4)), (20, (0, 0)), (100, (0, 0))], ease=LIN)
    tsp = kf([(0, (1.1818, .7143)), (8, (1.14, .76)), (20, (1, 1)), (100, (1, 1))], ease=LIN)
    esh = kf([(0, (-.5, 4.5)), (6.667, (-.5, 4.15)), (10, (-.2, 1)), (14, (-.06, .2)), (20, (0, 0)), (54, (0, 0)), (58, (0, .5)), (62, (0, 0)), (100, (0, 0))], ease=LIN)
    esp = kf([(0, (2, .2)), (6.667, (2.12, .12)), (10, (1.45, 1.8)), (14, (.92, 1.08)), (20, (1, 1)), (54, (1, 1)), (58, (1, .08)), (62, (1, 1.08)),
              (66.667, (1, 1)), (100, (1, 1))], ease=LIN)
    lsh = kf([(0, -2), (8, -1.5), (20, 0), (100, 0)], ease=LIN)
    lgr = kf([(0, .25), (8, .45), (20, 1), (100, 1)], ease=LIN)
    shd = kf([(0, 1), (20, .56), (33.333, .42), (46.667, .48), (56, .56), (66.667, .5294), (100, .5294)], ease=LIN)

    P_ = []
    for k in range(N):
        p = pc(k)
        ty, bsx, bsy, rot = bm(p)
        ssx, ssy = tsp(p); sx_, sy_ = tsh(p)
        top_u = 6 + sy_; bot_u = top_u + 7 * ssy
        l_u = 2 + sx_; r_u = l_u + 11 * ssx
        Y = lambda y: 15 + (y - 15) * bsy + ty
        X = lambda x: 7.5 + (x - 7.5) * bsx
        top = rhu(2 * Y(top_u)); bot = min(30, rhu(2 * Y(bot_u)))
        w = even(2 * (X(r_u) - X(l_u)), 18, 28)
        h = max(8, bot - top); top = bot - h
        sa, sb, sc = lean_split(lean_of(rot, top)) if abs(rot) >= 1.5 else (0, 0, 0)
        # eyes
        exs, eys = esp(p); ex, ey = esh(p)
        ew = 2 * exs; eh = 4 * eys
        e_top = rhu(2 * Y(8 + ey))
        if ew >= 3.2 and eh <= 2.2:
            st, dtop = "eyes-slit", 19
        elif ew >= 3.2 and eh >= 3.3:
            st, dtop = "eyes-blob", 16
        elif eh <= 1.6:
            st, dtop = "eyes-shut-hi", 18
        elif eh >= 4.8:
            st, dtop = "eyes-wide", 15
        else:
            st, dtop = "eyes-open", 16
        # for open / blob eyes keep them at a fixed place relative to the top of the body
        if st in ("eyes-open", "eyes-wide", "eyes-blob"):
            e_top = top + 4 - (1 if st == "eyes-wide" else 0)
        elif st == "eyes-slit":
            e_top = bot - 5 if h <= 12 else top + 7
        elif st == "eyes-shut-hi":
            e_top = top + 6
        # legs
        lt_u = 11 + lsh(p); lb_u = lt_u + 4 * lgr(p)
        foot = min(29, rhu(2 * Y(lb_u)) - 1)
        P_.append(dict(top=top, bot=bot, w=w, sa=sa, sb=sb, sc=sc, st=st, e_dy=e_top - dtop, e_dx=sb, foot=foot,
                       sh=even(34 * shd(p), 12, 34)))
    T = lambda k: P_[k]
    tor = var_el(a, "tv", lambda k: (T(k)["w"], T(k)["bot"] - T(k)["top"], T(k)["sa"], T(k)["sb"], T(k)["sc"]),
                 lambda key: torso_part(*key))
    tor = a.wrap("tmv", lambda k: (0, T(k)["top"] - 12), tor)
    def bodyfn(k):
        t = T(k); eL, eR = torso_edges(t["w"], t["bot"] - t["top"], t["sa"], t["sb"], t["sc"])
        return (eL, eR, t["top"], t["bot"] - t["top"])
    def cpos(side):
        def f(k):
            eL, eR, top, h = bodyfn(k)
            return claw_pos(side, eL, eR, top, h)
        return f
    shadow = var_el(a, "shw", lambda k: T(k)["sh"], lambda n: shadow_part(n))
    legs = legs_dyn(a, lambda k: T(k)["foot"], lambda k: T(k)["bot"])
    eyes = eyes_move(a, "wey", lambda k: T(k)["st"], lambda k: T(k)["e_dx"], lambda k: T(k)["e_dy"])
    scene = "\n".join([shadow, legs, tor, arm_el(a, "L", cpos("L"), "ar-l", bodyfn), arm_el(a, "R", cpos("R"), "ar-r", bodyfn), eyes])
    c = "  <!-- Clawd v2 wake: 1.5 s one-shot at 8 fps (12 frames). Same beats as clawd-wake.svg: flat on the ground (the sleeping sploot pose), pop up with a stretch and wide eyes, settle with a squash, one blink. -->"
    return assemble(c, "-15 -25 45 45", a.css(), scene)


# ---------------------------------------------------------------- low battery
def build_low_battery():
    FPS, N = 6, 48
    a = Anim(FPS, N)
    def phase(k):
        t = (k / FPS) % 4.0 / 4.0
        u = t * 2 if t < .5 else 2 - t * 2
        return EASE_IO(u)
    def bot(k):
        return min(30, rhu(2 * (13 + 1 + 0.8 * phase(k))))
    H = 13
    top = lambda k: bot(k) - H
    W = 24
    def eyes_state(k):
        p = 100.0 * k / N
        if p <= 65: return "eyes-shut-hi"
        if p < 72: return "eyes-shut-hi" if p < 68 else "eyes-squint"
        if p <= 80: return "eyes-squint"
        if p < 88: return "eyes-squint" if p < 85 else "eyes-shut-hi"
        return "eyes-shut-hi"
    def e_dy(k):
        st = eyes_state(k)
        row = top(k) + (5 if st == "eyes-shut-hi" else 5)     # shut line at mid-face
        return row - (18 if st == "eyes-shut-hi" else 17)
    eL, eR = torso_edges(W, H)
    bodyfn = lambda k: (eL, eR, top(k), H)
    def cpos(side):
        return lambda k: claw_pos(side, eL, eR, top(k), H, 0, 2)
    tor = a.wrap("tmv", lambda k: (0, top(k) - 12), use(torso_part(W, H)))
    shadow = use("shadow")
    legs = legs_dyn(a, lambda k: 29, bot)
    eyes = eyes_move(a, "ley", eyes_state, None, e_dy)
    # battery warning icon above the head
    BATT_L = "#FF4444"; BATT_D = "#7A1F1F"; BATT_I = "#2A1E1A"
    bg = Grid()
    shell = rect_mask(6, 1, 20, 9) 
    for c in ((6, 1), (25, 1), (6, 9), (25, 9)): shell.discard(c)
    term = rect_mask(26, 3, 2, 5)
    paint(bg, shell | term, BATT_L, BATT_D)
    for (x, y) in shell:
        if (x, y) in bg.p and bg.p[(x, y)] == BATT_L and 7 <= x <= 24 and 2 <= y <= 8:
            bg.p[(x, y)] = BATT_I
    for j in range(2, 9):                      # one red rim pixel row inside the dark outline
        pass
    # red shell: re-draw the 1 px red rim between the dark outline and the dark interior
    bg2 = Grid()
    paint(bg2, shell | term, BATT_L, BATT_D)
    inner = rect_mask(8, 3, 16, 5)
    for pt in inner: bg2.p[pt] = BATT_I
    bar = Grid().R(9, 4, 3, 3, "#FF4444")
    extra = "\n".join([prop("battery", bg2), prop("battery-bar", bar)])
    lvl = lambda k: ["#FF4444", "#A93434", "#5E2A2A"][0 if ((k / FPS - 0.2) % 4) / 4 < .15 or ((k / FPS - 0.2) % 4) / 4 > .85 else 1 if abs((((k / FPS - 0.2) % 4) / 4) - .5) > .2 else 2]
    a.fill("bar", lvl)
    batt = "\n".join([use("battery"), '<g class="bar">' + use("battery-bar") + '</g>'])
    scene = "\n".join([shadow, legs, batt, tor, arm_el(a, "L", cpos("L"), "ar-l", bodyfn), arm_el(a, "R", cpos("R"), "ar-r", bodyfn), eyes])
    c = "  <!-- Clawd v2 low battery: 8 s loop at 6 fps (48 frames). Same beats as clawd-idle-low-battery.svg: dozing body that sinks and rises over a 4 s breath, drooping pincers, eyes slit shut with one half-open peek, red battery warning whose last bar pulses. -->"
    return assemble(c, "-15 -25 45 45", a.css(), scene, extra)


BUILDERS = {
    "clawd-wake-v2": build_wake,
    "clawd-idle-low-battery-v2": build_low_battery,
}


# ---------------------------------------------------------------- hat mishap
HAT_FILL = "#5865C8"; HAT_LIGHT = "#7F8BE8"; HAT_SHADE = "#404CB0"; HAT_LINE = "#232A66"
HAT_BAND = "#2C2557"; HAT_BAND_L = "#473F96"; HAT_BRIM = "#6A70D8"; HAT_BRIM_L = "#8E94F0"


def wizard_hat_grid(stars=True):
    """Wizard hat in body-local art px (torso top at row 12): cone rows -3..8, band rows 9..12, brim rows 13..15."""
    widths = [4, 6, 6, 8, 10, 10, 12, 14, 16, 18, 20, 22]
    bend = [-3, -3, -2, -2, -1, -1, 0, 0, 0, 0, 0, 0]
    cone = set(); rows = {}
    for i, (w, b) in enumerate(zip(widths, bend)):
        y = -3 + i
        x0 = 15 - w // 2 + b
        rows[y] = (x0, x0 + w - 1)
        for x in range(x0, x0 + w): cone.add((x, y))
    band = rect_mask(3, 9, 24, 4)
    brim = rect_mask(0, 13, 30, 3)
    for c in ((0, 13), (29, 13), (0, 15), (29, 15)): brim.discard(c)
    allm = cone | band | brim
    g = Grid()
    paint(g, allm, HAT_FILL, HAT_LINE)
    for (x, y) in allm:
        if g.p[(x, y)] == HAT_LINE:
            continue
        if (x, y) in brim:
            g.p[(x, y)] = HAT_BRIM_L if x < 15 else HAT_BRIM
        elif (x, y) in band:
            g.p[(x, y)] = HAT_BAND_L if y == 10 else HAT_BAND
        else:
            x0, x1 = rows[y]
            g.p[(x, y)] = HAT_SHADE if x >= x1 - 1 else HAT_LIGHT if x <= x0 + 1 and y > -5 else HAT_FILL
    # band keeps a light row; brim band joint gets a dark line
    if stars:
        for (x, y) in ((13, -1), (10, 2), (17, 3), (20, 6), (9, 6), (14, 5)):
            if g.p.get((x, y)) in (HAT_FILL, HAT_LIGHT, HAT_SHADE):
                g.p[(x, y)] = "#FFFFFF"
    return g


def hat_part(key):
    tilt10, stars = key
    name = f"hat-t{sg(tilt10)}" + ("" if stars else "-ns")
    g = rotate_grid(wizard_hat_grid(stars), tilt10 / 10.0, 15, 13)
    return reg(name, g, f"wizard hat tilted {tilt10/10:g} deg" + ("" if stars else " (stars dark)"))


def spark_part(kind, color):
    g = Grid()
    if kind == "dot":
        g.R(0, 0, 2, 2, color)
    else:
        g.S(1, 0, color); g.R(0, 1, 3, 1, color); g.S(1, 2, color)
    return reg(f"spk-{kind}-{color[1:]}", g, "sparkle")


def build_hat_mishap():
    FPS, N = 6, 42
    a = Anim(FPS, N)
    pc = lambda k: 100.0 * k / N
    bx_k = kf([(0, -4), (14, 6), (28, 0), (72, 0), (87, -6), (100, -4)])
    bdx = lambda k: rhu(bx_k(pc(k)))
    HY = 2
    # legs: two alternating pairs step while the crab walks
    lift1 = {3, 9, 33, 39}; lift2 = {2, 7, 32, 38}
    lift_fn = lambda k: [1 if k in lift1 else 0, 1 if k in lift2 else 0, 1 if k in lift1 else 0, 1 if k in lift2 else 0]
    legs = legs_dyn(a, lambda k: 29, lambda k: 26 + HY, bdx, lift_fn=lift_fn)
    shadow = a.wrap("shm", lambda k: (bdx(k), 0), use(shadow_part(18)))
    tor = use(torso_part(22, 14, 1, 0, 0))
    # eyes
    look = kf([(0, 2), (28, 2), (32, 0), (70, 0), (73, 0), (78, -1), (82, 1), (88, 2), (100, 2)])
    def estate(k):
        p = pc(k)
        if 68 <= p < 70.5: return "eyes-shut-hi" if False else "eyes-shut"
        if 70.5 <= p < 73: return "eyes-squint"
        if 65 <= p < 68: return "eyes-wide"
        return "eyes-open"
    eyes = eyes_move(a, "hey", estate, lambda k: rhu(look(pc(k))), lambda k: -1 if 61 <= pc(k) < 68 else 0)
    # hat: slide, tilt, snap back
    hdx = kf([(0, 0), (28, 0), (35, .84), (42, 1.4), (55, 1.4), (58, .63), (63, .21), (67, 0), (70, 0), (100, 0)])
    hdy = kf([(0, 0), (28, 0), (35, 2), (42, 4), (55, 4), (58, 2.4), (63, .7), (67, -.7), (70, .3), (72, 0), (100, 0)])
    htl = kf([(0, 0), (28, 0), (35, 3.15), (42, 7.5), (55, 7.5), (58, -3), (63, 2.1), (67, -1), (70, .5), (72, 0), (100, 0)])
    stars_on = lambda k: not (k in (23, 26))
    hat_key = lambda k: (rhu(htl(pc(k)) * 10 / 2.5) * 2.5 if False else int(round(htl(pc(k)) * 2)) * 5, stars_on(k))
    hat = var_el(a, "hv", hat_key, hat_part)
    hat = a.wrap("hmv", lambda k: (rhu(hdx(pc(k))), rhu(hdy(pc(k)))), hat)
    # right pincer lifted to fix the hat
    arm_k = kf([(0, (0, 0)), (38, (0, 0)), (45, (-5, -7)), (55, (-5, -8)), (58, (-5, -6)), (62, (-5, -7)), (67, (0, 0)), (100, (0, 0))])
    def armr(k):
        v = arm_k(pc(k)); return (rhu(v[0]), rhu(v[1]))
    # sparkles
    specs = [
        ("dot", "#FFF3A8", (26, 6), [(47, (0, 0), 0), (50, (0, 0), 1), (58, (-3, -4), 1), (66, (-5, -7), 0)]),
        ("plus", "#FFFFFF", (29, 8), [(50, (0, 0), 0), (54, (0, 0), 1), (62, (3, -4), 1), (70, (6, -6), 0)]),
        ("dot", "#DCC5FF", (18, 6), [(52, (0, 0), 0), (56, (0, 0), 1), (64, (-2, -6), .8), (72, (-2, -8), 0)]),
        ("dot", "#FFF3A8", (31, 12), [(53, (0, 0), 0), (58, (0, 0), 1), (66, (4, -2), .7), (72, (7, -4), 0)]),
        ("dot", "#FFFFFF", (4, 9), [(56, (0, 0), 0), (60, (0, 0), 1), (68, (-3, 2), .8), (74, (-5, 2), 0)]),
    ]
    sp = []
    for i, (kind, col, (ox, oy), pts) in enumerate(specs):
        part = spark_part(kind, col)
        pos = kf([(p, v) for p, v, o in pts] + [(100, pts[-1][1])])
        alp = kf([(p, o) for p, v, o in pts] + [(100, 0)], ease=LINEAR)
        vis = lambda k, alp=alp: alp(pc(k)) >= .5
        def mv(k, pos=pos, ox=ox, oy=oy, vis=vis):
            v = pos(pc(k)); return (ox + rhu(v[0]), oy + rhu(v[1])) if vis(k) else (0, 0)
        inner = a.wrap(f"spm{i}", lambda k, mv=mv: mv(k), use(part))
        sp.append(a.vwrap(f"spv{i}", vis, inner))
    upper = "\n".join([tor, arm_el(a, "L", lambda k: (0, 0), "ar-l"), eyes, hat, arm_el(a, "R", armr, "ar-r"), "\n".join(sp)])
    body = a.wrap("hunch", lambda k: (bdx(k), HY), upper)
    scene = "\n".join([shadow, legs, body])
    c = "  <!-- Clawd v2 hat mishap: 7 s loop at 6 fps (42 frames). Same beats as clawd-hat-mishap.svg: hunched walk right and back, the wizard hat slides and tilts, the right pincer lifts to fix it, the hat snaps back in a burst of sparkles, eyes look around and blink. -->"
    return assemble(c, "-15 -25 45 45", a.css(), scene)


BUILDERS["clawd-hat-mishap-v2"] = build_hat_mishap


# ---------------------------------------------------------------- shared scene builder
def std_scene(a, P, tag="s"):
    """P[k]: top, bot, w, sa, sb, sc, dx, foot, sh=(w, strong, soft), es, edx, edy, cl=((dxc,dyc) left, (dxc,dyc) right)."""
    T = lambda k: P[k]
    key = lambda k: (T(k)["w"], T(k)["bot"] - T(k)["top"], T(k).get("sa", 0), T(k).get("sb", 0), T(k).get("sc", 0))
    tor = a.wrap(f"{tag}tm", lambda k: (T(k).get("dx", 0), T(k)["top"] - 12), var_el(a, f"{tag}tv", key, lambda kk: torso_part(*kk)))
    def edges(k):
        t = T(k); h = t["bot"] - t["top"]
        eL, eR = torso_edges(t["w"], h, t.get("sa", 0), t.get("sb", 0), t.get("sc", 0), t.get("dx", 0))
        return eL, eR, t["top"], h
    def cpos(side):
        i = 0 if side == "L" else 1
        def f(k):
            eL, eR, top, h = edges(k)
            dxc, dyc = T(k).get("cl", ((0, 0), (0, 0)))[i]
            return claw_pos(side, eL, eR, top, h, dxc, dyc)
        return f
    shadow = a.wrap(f"{tag}shm", lambda k: (T(k).get("shdx", T(k).get("dx", 0)), 0),
                    var_el(a, f"{tag}shv", lambda k: T(k)["sh"], lambda sh: shadow_part(*sh)))
    legs = legs_dyn(a, lambda k: T(k)["foot"], lambda k: T(k)["bot"], lambda k: T(k).get("ldx", T(k).get("dx", 0)), tag=f"{tag}lg")
    eyes = eyes_move(a, f"{tag}ey", lambda k: T(k)["es"], lambda k: T(k).get("edx", 0) + T(k).get("dx", 0) + T(k).get("sb", 0),
                     lambda k: T(k).get("edy", 0) + (T(k)["top"] - 12))
    arms = "\n".join([arm_el(a, "L", cpos("L"), f"{tag}al", edges), arm_el(a, "R", cpos("R"), f"{tag}ar", edges)])
    return shadow, legs, tor, arms, eyes


def QUESTION(small=False):
    g = Grid()
    if small:
        for (x, y) in ((1, 0), (2, 0), (0, 1), (3, 1), (3, 2), (2, 3), (1, 4), (1, 6)):
            g.S(x, y, "#FFFFFF")
        return g
    for (x, y, w, h) in ((1, 0, 4, 2), (0, 2, 2, 2), (4, 2, 2, 2), (4, 4, 2, 1), (3, 5, 2, 2), (2, 7, 2, 2), (2, 10, 2, 2)):
        g.R(x, y, w, h, "#FFFFFF")
    return g


def recolor(g, color):
    o = Grid()
    for pt in g.p: o.p[pt] = color
    return o


# ---------------------------------------------------------------- confused
def build_confused():
    FPS, N = 8, 48
    a = Anim(FPS, N)
    pc = lambda k: 100.0 * k / N
    bx = kf([(0, 0), (10, 0), (15, -4), (35, -4), (40, 0), (45, 0), (50, 4), (70, 4), (75, 0), (100, 0)])
    ex = kf([(0, 0), (10, 0), (15, -2), (35, -2), (40, 0), (45, 0), (50, 2), (70, 2), (75, 0), (100, 0)])
    P = []
    for k in range(N):
        d = rhu(bx(pc(k)))
        P.append(dict(top=12, bot=26, w=22, dx=d, sa=(-1 if d < -1 else 1 if d > 1 else 0), foot=29, ldx=int(d / 2), sh=(24, .3, .15),
                      es="eyes-shut" if k in (7, 24, 39) else "eyes-open", edx=rhu(ex(pc(k))), edy=0,
                      cl=((0, -7), (0, 0))))
    shadow, legs, tor, arms, eyes = std_scene(a, P)
    # question marks
    qcols = {"L": "#40C4FF", "R": "#FFC107"}
    q_states = {"L": {8: ("s", 10), 9: ("n", 6), 10: ("n", 0), 11: ("n", 0), 12: ("n", 0), 13: ("n", 0), 14: ("n", 0), 15: ("n", -2), 16: ("s", -8)},
                "R": {25: ("s", 10), 26: ("n", 6), 27: ("n", 0), 28: ("n", 0), 29: ("n", 0), 30: ("n", 0), 31: ("n", 0), 32: ("n", -2), 33: ("s", -8)}}
    qx = {"L": -8, "R": 15}
    extra, qs = [], []
    for side in "LR":
        for kind, small in (("n", False), ("s", True)):
            extra.append(prop(f"q{side}-{kind}", recolor(QUESTION(small), qcols[side])))
        for kind in ("n", "s"):
            vis = lambda k, side=side, kind=kind: (q_states[side].get(k) or (None,))[0] == kind
            mv = lambda k, side=side, kind=kind: (qx[side] + (1 if kind == "s" else 0), -1 + (q_states[side].get(k) or (0, 0))[1] + (3 if kind == "s" else 0)) if vis(k) else (0, 0)
            qs.append(a.vwrap(f"qv{side}{kind}", vis, a.wrap(f"qm{side}{kind}", mv, use(f"q{side}-{kind}"))))
    scene = "\n".join([shadow, legs, tor, arms, eyes, "\n".join(qs)])
    c = "  <!-- Clawd v2 confused: 6 s loop at 8 fps (48 frames). Same beats as clawd-working-confused.svg: left pincer scratching the head, the body and eyes look left then right, three blinks, a cyan ? pops on the left and an amber ? on the right. -->"
    return assemble(c, "-15 -25 45 45", a.css(), scene, "\n".join(extra))


# ---------------------------------------------------------------- dizzy
def star_grid(size, color="#FFC107", core="#FFF3A8"):
    g = Grid(); m = size // 2
    for i in range(size):
        g.S(i, m, color); g.S(m, i, color)
    if size >= 5:
        g.S(m, m, core)
    return g


def build_dizzy():
    FPS, N = 8, 32
    a = Anim(FPS, N)
    pc = lambda k: 100.0 * k / N
    rot = kf([(0, -6), (50, 6), (100, -6)])
    P = []
    for k in range(N):
        r = rot(pc(k))
        sa, sb, sc = lean_split(lean_of(r, 12))
        P.append(dict(top=12, bot=26, w=22, sa=sa, sb=sb, sc=sc, foot=29, ldx=0, sh=(24, .3, .15), es="eyes-x", edx=0, edy=0,
                      cl=((0, 0), (0, 0))))
    shadow, legs, tor, arms, eyes = std_scene(a, P)
    orb = kf([(0, (-10, 0, .85, 1)), (12.5, (-7, 2, .97, 1)), (25, (0, 3, 1.1, 1)), (37.5, (7, 2, .97, 1)), (50, (10, 0, .85, 1)),
              (62.5, (7, -2, .72, .8)), (75, (0, -3, .6, .4)), (87.5, (-7, -2, .72, .8)), (100, (-10, 0, .85, 1))], ease=LINEAR)
    sizes = (3, 5, 7)
    extra = "\n".join(prop(f"dstar{s}", star_grid(s)) for s in sizes)
    def sz(scl): return 7 if scl >= 1.0 else 5 if scl >= .8 else 3
    stars = []
    for i, off in enumerate((0, 8, 16)):
        def st(k, off=off):
            age = (k + off) % N
            tx, ty, scl, al = orb(100.0 * age / N)
            return (sz(scl), 15 + rhu(2 * tx), 4 + rhu(2 * ty))
        for s in sizes:
            vis = lambda k, s=s, st=st: st(k)[0] == s
            mv = lambda k, s=s, st=st: (st(k)[1] - s // 2, st(k)[2] - s // 2) if vis(k) else (0, 0)
            stars.append(a.vwrap(f"dv{i}_{s}", vis, a.wrap(f"dm{i}_{s}", mv, use(f"dstar{s}"))))
    scene = "\n".join([shadow, legs, tor, arms, eyes, "\n".join(stars)])
    c = "  <!-- Clawd v2 dizzy: 4 s loop at 8 fps (32 frames). Same beats as clawd-dizzy.svg: x eyes, the body sways from the feet (done as a stepped lean, no rotation), three stars orbit the head on a 3 s ellipse (three sizes fake the depth). -->"
    return assemble(c, "-15 -25 45 45", a.css(), scene, extra)


BUILDERS["clawd-working-confused-v2"] = build_confused
BUILDERS["clawd-dizzy-v2"] = build_dizzy


# ---------------------------------------------------------------- sweeping
def broom_grid(theta, tx, ty):
    g = Grid()
    g.R(27, 8, 1, 20, WOOD); g.R(28, 8, 1, 20, WOODD)
    head = rect_mask(24, 28, 8, 4)
    hg = Grid(); paint(hg, head, HAT, HATLINE)
    for (x, y), c in list(hg.p.items()):
        if c == HAT:
            hg.p[(x, y)] = HATL if y == 29 else HATD
    g.merge(hg)
    r = rotate_grid(g, theta, 27, 28)
    o = Grid(); o.merge(r, tx, ty)
    return o


def build_sweeping():
    FPS, N = 8, 12
    a = Anim(FPS, N)
    def e(k):
        t = k / N
        u = t * 2 if t < .5 else 2 - t * 2
        return EASE_IO(u)
    P, brooms = [], []
    for k in range(N):
        ek = e(k)
        rot = 5 + 10 * ek
        tx = rhu(2 + 4 * ek)
        L = lean_of(rot, 12)
        dyb = rhu(ek)
        P.append(dict(top=12 + dyb, bot=26 + dyb, w=22, sa=tx + rhu(L), sb=tx + rhu(.6 * L), sc=tx + rhu(.2 * L), dx=0,
                      foot=29, ldx=tx + rhu(.1 * L), sh=(26, .3, .15), shdx=4, es="eyes-focus", edx=0, edy=0,
                      cl=((12, 3), (rhu(ek), -rhu(3 * ek)))))
        brooms.append((rhu(10 + 20 * ek), rhu(4 * ek), -rhu(2 * ek)))
    shadow, legs, tor, arms, eyes = std_scene(a, P)
    broom = var_el(a, "bv", lambda k: brooms[k], lambda kk: reg(f"broom-{kk[0]}-{sg(kk[1])}-{sg(kk[2])}", broom_grid(*kk), "push broom"))
    # dust: two puffs fly off to the right along the ground
    def dust(delay, size, color, tag):
        def st(k):
            age = (k - delay) % N
            p = 100.0 * age / N
            if p < 40: return None
            if p < 50:
                f = (p - 40) / 10.0; x = 34 + 4 * f; sc = f
            else:
                f = (p - 50) / 50.0; x = 38 + 12 * f; sc = 1 - .5 * f
            n = max(0, rhu(size * sc))
            return (n, rhu(x)) if n >= 1 else None
        return st
    extra, ds = [], []
    for i, (delay, size, color) in enumerate(((1.6, 3, "#9E9E9E"), (3.2, 2, "#B0BEC5"))):
        st = dust(delay, size, color, i)
        sizes = sorted({st(k)[0] for k in range(N) if st(k)})
        for n in sizes:
            extra.append(prop(f"dust{i}-{n}", Grid().R(0, 0, n, n, color)))
            vis = lambda k, n=n, st=st: (st(k) or (0,))[0] == n
            mv = lambda k, n=n, st=st: (st(k)[1], 28) if vis(k) else (0, 0)
            ds.append(a.vwrap(f"dv{i}_{n}", vis, a.wrap(f"dm{i}_{n}", mv, use(f"dust{i}-{n}"))))
    scene = "\n".join([shadow, legs, tor, broom, arms, eyes, "\n".join(ds)])
    c = "  <!-- Clawd v2 sweeping: 1.5 s loop at 8 fps (12 frames). Same beats as clawd-working-sweeping.svg: the body leans into the stroke (stepped lean instead of rotation), the right pincer holds the broom, the broom swings out and back, dust puffs fly off to the right. -->"
    return assemble(c, "-15 -25 45 45", a.css(), scene, "\n".join(extra))


# ---------------------------------------------------------------- alert
def bang_grid(small=False):
    g = Grid()
    if small:
        m = rect_mask(0, 0, 3, 5) | rect_mask(0, 6, 3, 3)
    else:
        m = rect_mask(0, 0, 4, 8) | rect_mask(0, 10, 4, 4)
    paint(g, m, BANG, INK)
    return g


def build_alert():
    FPS, N = 10, 40
    a = Anim(FPS, N)
    pc = lambda k: 2.5 * k
    keys = [(0, (0, 0, 1, 1)), (12, (0, 0, 1, 1)), (14, (-1.5, 0, 1, 1)), (22, (-1.5, 0, 1, 1)), (26, (0, 2, 1.1, .9))]
    arms = [(0, (0, 0)), (12, (0, 0)), (14, (0, 1)), (22, (0, 1)), (26, (0, 3))]
    for i in range(6):
        p0 = 30 + 8 * i
        keys += [(p0, (0, -10, .95, 1.05)), (p0 + 4, (0, 2, 1.1, .9))]
        arms += [(p0, (-3, -8)), (p0 + 4, (-1, -4))]
    keys += [(80, (0, 0, 1, 1)), (100, (0, 0, 1, 1))]
    arms += [(80, (0, 0)), (100, (0, 0))]
    body = kf(keys); armk = kf(arms)
    P = []
    for k in range(N):
        p = pc(k)
        tx, ty, sx, sy = body(p)
        w = even(22 * sx, 18, 26); h = max(10, rhu(14 * sy))
        bot = min(30, rhu(2 * (15 + (13 - 15) * sy + ty)))
        foot = min(29, rhu(2 * (15 + ty)) - 1)
        if ty <= -8: sh = (14, .15, .08)
        elif ty < -3: sh = (18, .2, .1)
        elif ty > 1.5: sh = (28, .35, .18)
        else: sh = (24, .3, .15)
        ax, ay = armk(p)
        ax, ay = rhu(ax), rhu(ay)
        P.append(dict(top=bot - h, bot=bot, w=w, dx=rhu(2 * tx), foot=foot, sh=sh, es="eyes-open",
                      edx=2 if 13.9 <= p <= 25 else 0, edy=0, cl=((ax, ay), (-ax, ay))))
    shadow, legs, tor, arms_, eyes = std_scene(a, P)
    # exclamation mark popping up on the right
    bang_states = {5: ("s", -4), 6: ("n", -9), 7: ("n", -9), 8: ("n", -9), 9: ("n", -9), 10: ("s", -12)}
    extra = "\n".join([prop("bang-n", bang_grid()), prop("bang-s", bang_grid(True))])
    bs = []
    for kind in ("n", "s"):
        vis = lambda k, kind=kind: (bang_states.get(k) or (None,))[0] == kind
        mv = lambda k, kind=kind: (32, bang_states[k][1]) if vis(k) else (0, 0)
        bs.append(a.vwrap(f"bgv{kind}", vis, a.wrap(f"bgm{kind}", mv, use(f"bang-{kind}"))))
    scene = "\n".join([shadow, legs, "\n".join(bs), tor, arms_, eyes])
    c = "  <!-- Clawd v2 alert: 4 s loop at 10 fps (40 frames). Same beats as clawd-notification.svg: startled recoil and look right with a red ! popping up, squash, six stretch-and-land jumps with the pincers flapping up and out, recover. -->"
    return assemble(c, "-15 -25 45 45", a.css(), scene, extra)


BUILDERS["clawd-working-sweeping-v2"] = build_sweeping
BUILDERS["clawd-notification-v2"] = build_alert
