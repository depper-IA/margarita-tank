"""Clawd v2 rig: reusable parts drawn on the 0.5-unit art grid (art px, crab body box 30x32)."""
from art import *

P = dict(
    body="#DE886D", light="#F3AC90", shine="#FFD3C2", shade="#B8644B", line="#6B3122",
    eye="#1B1311", white="#FFFFFF", blush="#EA7C7E",
    shadow="#000000@0.3", shadow2="#000000@0.15",
)
SH = P["shade"]; LN = P["line"]; BD = P["body"]; LT = P["light"]; SP = P["shine"]; EYE = P["eye"]; WH = P["white"]

# ---- geometry (art px) ----
TORSO = (4, 12, 22, 14)           # x, y, w, h  (outline included)
ARM_L = (-1, 15)                  # 6x8 C pincer, inner column sits on the body outline
ARM_R = (25, 15)
LEG_X = (6, 10, 18, 22)           # 2 px wide legs
LEG_TOP, FOOT_ROW = 18, 29        # legs are drawn tall and tucked behind the body


CLAW_ROWS = ["011111", "111111", "111111", "001111", "001111", "111111", "111111", "011111"]   # left claw, inner column on the right


def arm_mask(x, y, side):
    m = set()
    for j, row in enumerate(CLAW_ROWS):
        for i, ch in enumerate(row):
            if ch == "1":
                m.add((x + (i if side == "L" else 5 - i), y + j))
    return m


def shade_body(g, x, y, w, h):
    """Light top/left, shade bottom/right, specular dot, inside the 1 px outline."""
    x0, x1, y0, y1 = x + 1, x + w - 2, y + 1, y + h - 2
    g.R(x0 + 1, y0, x1 - x0 - 1, 1, LT)
    g.R(x0, y0, 1, y1 - y0 - 1, LT)
    g.R(x0 + 1, y1 - 1, x1 - x0, 2, SH)
    g.R(x1, y0 + 1, 1, y1 - y0, SH)
    g.R(x0 + 1, y0 + 1, 2, 1, SP)


def torso_grid(rect=TORSO):
    x, y, w, h = rect
    g = Grid()
    paint(g, rect_mask(x, y, w, h), BD, LN)
    shade_body(g, x, y, w, h)
    return g


def claw_grid(arm_xy, side):
    """Solid C pincer: body-colour fill, light on the top/left rim, shade on the bottom/right rim,
    1 px outline only on the outer silhouette (and around the notch)."""
    ax, ay = arm_xy
    am = arm_mask(ax, ay, side)
    g = Grid()
    paint(g, am, BD, LN)
    out = {}
    for (x, y) in am:
        if g.p[(x, y)] == LN:
            continue
        up = g.p.get((x, y - 1)) == LN or (x, y - 1) not in am
        dn = g.p.get((x, y + 1)) == LN or (x, y + 1) not in am
        if dn:
            out[(x, y)] = SH
        elif up:
            out[(x, y)] = LT
    g.p.update(out)
    return g


def free_arm(arm_xy, side):
    return claw_grid(arm_xy, side)


def fused_arm(torso_rect, arm_xy, side, shade_rect=None):
    """The claw as seen fused with the body: the inner column (rows 1..5) opens into the body."""
    g = claw_grid(arm_xy, side)
    ax, ay = arm_xy
    ix = ax + 5 if side == "L" else ax + 0
    for j in range(1, 7):
        g.p[(ix, ay + j)] = LT if j == 1 else (SH if j == 6 else BD)
    return g


def link_grid(side, x_from, x_to, y):
    """6-row forearm joining a raised pincer to the body (outline, light, 2 base, shade, outline)."""
    g = Grid()
    w = x_to - x_from + 1
    for j, c in enumerate((LN, LT, BD, BD, SH, LN)):
        g.R(x_from, y + j, w, 1, c)
    return g


def leg_grid(x, top=LEG_TOP, foot=FOOT_ROW):
    g = Grid()
    h = foot - top + 1
    g.R(x, top, 1, h, SH); g.R(x + 1, top, 1, h, LN); g.R(x, foot, 2, 1, LN)
    return g


def eye_open(x, top=16, h=4):
    g = Grid(); g.R(x, top, 2, h, EYE); g.S(x, top, WH); return g


def eye_shut(x, row=19):
    return Grid().R(x, row, 2, 1, EYE)


def eye_squint(x, top=17):
    return Grid().R(x, top, 2, 2, EYE)


def eye_happy(x, row=18):
    """Upturned arc (^): 4 wide, 2 tall, centred on the 2 px eye."""
    g = Grid()
    g.R(x, row, 2, 1, EYE); g.S(x - 1, row + 1, EYE); g.S(x + 2, row + 1, EYE)
    return g


EYE_XL, EYE_XR = 8, 20


def pair(fn, **kw):
    g = Grid(); g.merge(fn(EYE_XL, **kw)); g.merge(fn(EYE_XR, **kw)); return g


BLUSH_HI = "#F7A3A1"


def blush_grid(row=20):
    """Two 4x3 rounded patches with a lighter 2x1 centre: readable at 2 device px per art px."""
    g = Grid()
    for x0 in (6, 20):
        g.R(x0 + 1, row, 2, 1, P["blush"]); g.R(x0, row + 1, 4, 1, P["blush"]); g.R(x0 + 1, row + 2, 2, 1, P["blush"])
        g.R(x0 + 1, row + 1, 2, 1, BLUSH_HI)
    return g


def smile_grid(row=21):
    g = Grid(); g.S(13, row, LN); g.R(14, row + 1, 2, 1, LN); g.S(16, row, LN); return g


def smile_open_grid(row=21):
    """Open happy mouth (D shape): dark with a tongue."""
    g = Grid()
    g.R(12, row, 6, 1, EYE); g.R(13, row + 1, 4, 1, EYE)
    g.R(14, row + 1, 2, 1, P["blush"])
    return g


def mouth_yawn(level):
    g = Grid()
    if level == 1:
        g.R(14, 21, 2, 1, EYE)
    elif level == 2:
        g.R(14, 20, 2, 3, EYE); g.R(13, 21, 4, 1, EYE)
    else:
        g.R(13, 19, 4, 1, EYE); g.R(12, 20, 6, 3, EYE); g.R(13, 23, 4, 1, EYE)
        g.R(14, 22, 2, 2, P["blush"])
    return g


def shadow_grid(kind="normal"):
    g = Grid()
    if kind == "normal":
        g.R(3, 30, 24, 1, P["shadow"]); g.R(6, 31, 18, 1, P["shadow2"])
    elif kind == "small":
        g.R(6, 30, 18, 1, P["shadow"]); g.R(9, 31, 12, 1, P["shadow2"])
    elif kind == "tiny":
        g.R(9, 30, 12, 1, P["shadow"]); g.R(12, 31, 6, 1, P["shadow2"])
    elif kind == "wide":
        g.R(-2, 30, 34, 1, P["shadow"]); g.R(1, 31, 28, 1, P["shadow2"])
    return g


# ---- sleeping sploot pose ----
SPLOOT_Y1 = 30   # bottom edge (exclusive) of the sploot torso


def sploot_rect(h):
    return (2, SPLOOT_Y1 - h, 26, h)


def sploot_torso(h):
    return torso_grid(sploot_rect(h))


def sploot_arm(side, h=10):
    rect = sploot_rect(h)
    xy = (-3, 22) if side == "L" else (27, 22)
    return fused_arm(rect, xy, side)


def leg_up(x, top):
    """A leg sticking up behind the flattened body (tip at the top, tucked behind the torso)."""
    g = Grid()
    g.R(x, top + 1, 1, 3, SH); g.R(x + 1, top + 1, 1, 3, LN); g.R(x, top, 2, 1, LN)
    return g


def build_parts():
    parts = {}
    parts["shadow"] = shadow_grid("normal")
    parts["shadow-sm"] = shadow_grid("small")
    parts["shadow-xs"] = shadow_grid("tiny")
    parts["shadow-wide"] = shadow_grid("wide")
    for i, x in enumerate(LEG_X, 1):
        parts[f"leg{i}"] = leg_grid(x)
    parts["torso"] = torso_grid()
    parts["arm-l"] = fused_arm(TORSO, ARM_L, "L")
    parts["arm-r"] = fused_arm(TORSO, ARM_R, "R")
    parts["arm-l-free"] = free_arm(ARM_L, "L")
    parts["arm-r-free"] = free_arm(ARM_R, "R")
    parts["eyes-open"] = pair(eye_open)
    parts["eyes-wide"] = pair(eye_open, top=15, h=5)
    parts["eyes-shut"] = pair(eye_shut)
    parts["eyes-squint"] = pair(eye_squint)
    parts["eyes-happy"] = pair(eye_happy)
    parts["eye-l-open"] = eye_open(EYE_XL)
    parts["eye-r-open"] = eye_open(EYE_XR)
    parts["eye-l-squint"] = eye_squint(EYE_XL)
    parts["blush"] = blush_grid()
    parts["smile"] = smile_grid()
    parts["smile-open"] = smile_open_grid()
    for lv in (1, 2, 3):
        parts[f"mouth-yawn-{lv}"] = mouth_yawn(lv)
    for h in (10, 11, 12):
        parts[f"torso-sploot-{h}"] = sploot_torso(h)
        parts[f"arm-sploot-l-{h}"] = sploot_arm("L", h)
        parts[f"arm-sploot-r-{h}"] = sploot_arm("R", h)
    for i, x in enumerate(LEG_X, 1):
        parts[f"leg-up{i}"] = leg_up(x, 17)
    return parts


PARTS = build_parts()

DESCR = {
    "shadow": "ground shadow, two translucent rows",
    "shadow-sm": "ground shadow, small (body in the air)",
    "shadow-xs": "ground shadow, tiny (body high in the air)",
    "shadow-wide": "ground shadow for the sploot pose",
    "torso": "body: 1 px outline, light top/left, shade bottom/right, specular dot",
    "arm-l": "left pincer fused with the body (rest spot and sliding along the body side)",
    "arm-r": "right pincer fused with the body (rest spot and sliding along the body side)",
    "arm-l-free": "left pincer, closed outline (any position)",
    "arm-r-free": "right pincer, closed outline (any position)",
    "eyes-open": "eyes 2x4 with a white highlight",
    "eyes-wide": "eyes 2x5, wide open",
    "eyes-shut": "eyes shut, 2x1 line",
    "eyes-squint": "eyes squinted, 2x2",
    "eyes-happy": "eyes happy, upturned arcs",
    "eye-l-open": "left eye alone", "eye-r-open": "right eye alone", "eye-l-squint": "left squinted eye alone",
    "blush": "blush patches", "smile": "small smile", "smile-open": "open smile with tongue",
}
for i in range(1, 5):
    DESCR[f"leg{i}"] = f"leg {i} of 4 (drawn tall; the top is hidden behind the body)"
for lv in (1, 2, 3):
    DESCR[f"mouth-yawn-{lv}"] = f"yawn mouth, size {lv}"
for h in (10, 11, 12):
    DESCR[f"torso-sploot-{h}"] = f"flattened sleeping body, {h} px tall"
    DESCR[f"arm-sploot-l-{h}"] = f"left pincer flat on the ground ({h} px body)"
    DESCR[f"arm-sploot-r-{h}"] = f"right pincer flat on the ground ({h} px body)"
for i in range(1, 5):
    DESCR[f"leg-up{i}"] = f"leg {i} sticking up behind the sleeping body"


def part_svg(pid, indent="    "):
    g = PARTS[pid]
    return f'{indent}<!-- {DESCR.get(pid, pid)} -->\n{indent}<g id="{pid}">\n{to_paths(g, indent=indent + "  ")}\n{indent}</g>'


def rig_defs(used, indent="    "):
    """Rig definitions for the part ids in `used`, in a stable order."""
    order = list(PARTS)
    return "\n".join(part_svg(pid, indent) for pid in order if pid in used)


if __name__ == "__main__":
    # ASCII preview of the standing crab for review
    g = Grid()
    for k in ("leg1", "leg2", "leg3", "leg4"):
        g.merge(PARTS[k])
    for k in ("torso", "arm-l", "arm-r", "eyes-open"):
        g.merge(PARTS[k])
    print(ascii_dump(g, box=(0, 10, 29, 31)))
