from svgbuild import *
from props import *
import props

def u2a(v): return rhu(2 * v)


def build_thinking():
    FPS, N = 8, 32
    a = Anim(FPS, N)
    pc = lambda k: 100.0 * k / N
    sway = kf([(0, 0), (25, -1), (75, 1), (100, 0)])
    def body(k): return (u2a(sway(pc(k))), 0)
    def legs_f(k):
        d = int(body(k)[0] / 2)
        return [(d, 0)] * 4
    blink = {15, 16}
    def eye_state(k): return "shut" if k in blink else "open"
    def arm_r(k): return (-5, 4 if (k // 4) % 2 == 0 else 3)   # taps the "chin" every half second
    dots = lambda k: (0 if (k % 16) < 4 else 1 if (k % 16) < 7 else 2 if (k % 16) < 10 else 3)
    # bubble
    bg = Grid()
    m = rect_mask(14, -14, 22, 15)
    for c in ((14, -14), (15, -14), (14, -13), (35, -14), (34, -14), (35, -13), (14, 0), (15, 0), (14, -1), (35, 0), (34, 0), (35, -1)): m.discard(c)
    paint(bg, m, PAPER, INK)
    bg.R(15, -2, 20, 1, PAPER_S)
    t1 = rect_mask(17, 3, 4, 4)
    for c in ((17, 3), (20, 3), (17, 6), (20, 6)): t1.discard(c)
    paint(bg, t1, PAPER, INK)
    bg.R(14, 9, 2, 2, INK)
    d = lambda x: Grid().R(x, -9, 2, 2, BLUE)
    extra = "\n".join([prop("think-bubble", bg)] + [prop(f"think-dot{i}", d(19 + 5 * i)) for i in range(3)])
    dots_el = "\n".join(a.vwrap(f"dot{i}", lambda k, i=i: dots(k) > i, use(f"think-dot{i}")) for i in range(3))
    inner = "\n".join([
        use("torso"), arm_el(a, "L", lambda k: (0, 0), "ar-l"), arm_el(a, "R", arm_r, "ar-r"),
        eyes_el(a, eye_state, lambda k: (2, -1), "ey"),
    ])
    scene = "\n".join([
        use("shadow"), use("think-bubble"), dots_el,
        legs_el(a, legs_f), a.wrap("sway", body, inner),
    ])
    c = "  <!-- Clawd v2 thinking: 4 s loop at 8 fps (32 frames). Slow sway, right pincer taps the chin, eyes look up at the bubble, dots load. -->"
    return assemble(c, "-15 -25 45 45", a.css(), scene, extra)


def build_typing():
    FPS, N = 8, 12
    a = Anim(FPS, N)
    def body(k): return (0, k % 2)
    sweep = [-2, -2, -1, -1, 0, 0, 1, 1, 2, 2, 2, -2]
    def arm_l(k): return (0, 0 if k % 2 == 0 else 3)
    def arm_r(k): return (0, 3 if k % 2 == 0 else 0)
    LAP, LAPL, LAPD, LAPLINE = "#8696A3", "#A9B8C4", "#5F6F7B", "#2B343B"
    lap = Grid()
    paint(lap, rect_mask(6, 19, 18, 10), LAP, LAPLINE)
    lap.R(7, 20, 16, 1, LAPL); lap.R(7, 27, 16, 1, LAPD); lap.R(7, 20, 1, 7, LAPL)
    paint(lap, rect_mask(4, 29, 22, 2), LAPD, LAPLINE)
    lap.R(5, 29, 20, 1, LAP)
    glow = [0, 0, 1, 1, 2, 2, 2, 2, 1, 1, 0, 0]
    gcol = ["#3A6A80", "#4FA9CF", "#40C4FF"]
    ring = Grid()
    for (x, y) in rect_mask(13, 22, 4, 4):
        if not (14 <= x <= 15 and 23 <= y <= 24): ring.S(x, y, "#40C4FF")
    center = Grid().R(14, 23, 2, 2, WH())
    extra = "\n".join([prop("laptop", lap), prop("logo-ring", ring), prop("logo-core", center)])
    ring_el = g("glow", use("logo-ring"))
    a.fill("glow", lambda k: gcol[glow[k]])
    # packets
    PK = Grid().R(0, 0, 3, 3, "#40C4FF").S(0, 0, "#BDEFFF")
    extra += "\n" + prop("packet", PK)
    starts = [0, 2, 5, 6, 1, 3, 6]
    origins = [(-4, 24), (10, 22), (24, 26), (34, 22), (16, 20), (2, 22), (30, 24)]
    alpha = [0.4, 0.8, 1, 1, 1, 0.8, 0.6, 0.4]
    pk = []
    for i, (s, (ox, oy)) in enumerate(zip(starts, origins)):
        def pos(k, s=s, ox=ox, oy=oy):
            age = (k - s) % N
            return (ox, oy - rhu(30 * age / 8)) if age < 8 else (ox, oy)
        def op(k, s=s):
            age = (k - s) % N
            return alpha[age] if age < 8 else 0
        a.move(f"pm{i}", lambda k, pos=pos, ox=ox, oy=oy: (pos(k)[0] - ox, pos(k)[1] - oy))
        a.show(f"po{i}", op)
        pk.append(f'<g class="pm{i}"><g class="po{i}"><use href="#packet" x="{ox}" y="{oy}"/></g></g>')
    inner = "\n".join([
        use("torso"), arm_el(a, "L", arm_l, "ar-l"), arm_el(a, "R", arm_r, "ar-r"),
        eyes_el(a, lambda k: "squint", lambda k: (sweep[k], 0), "ey"),
    ])
    scene = "\n".join([use("shadow"), "\n".join(pk), legs_el(a), a.wrap("jit", body, inner),
                       use("laptop"), ring_el, use("logo-core")])
    c = "  <!-- Clawd v2 typing: 1.5 s loop at 8 fps (12 frames). Body shakes, pincers hammer the keys behind the laptop, eyes read left to right, data bits float up. -->"
    return assemble(c, "-15 -25 45 45", a.css(), scene, extra)


def WH(): return "#FFFFFF"


def build_conducting():
    FPS, N = 8, 16
    a = Anim(FPS, N)
    pc = lambda k: 100.0 * k / N
    bob = kf([(0, 0), (50, 1), (100, 0)])
    def body(k): return (0, u2a(bob(pc(k))))
    lk = kf([(0, (0, 2)), (50, (-3, -8)), (100, (0, 2))])
    rk = kf([(0, (3, -8)), (50, (0, 2)), (100, (3, -8))])
    def arm_l(k): v = lk(pc(k)); return (rhu(v[0]), rhu(v[1]))
    def arm_r(k): v = rk(pc(k)); return (rhu(v[0]), rhu(v[1]))
    cols = [("#3D8BFD", "#9CC4FF"), ("#FFC93C", "#FFE9A3"), ("#FF5A5F", "#FFA3A6"), ("#4CC27A", "#9BE3B7"), ("#A45CE6", "#D3A9F5")]
    extra_l = []
    pkts = []
    path = kf([(0, (-2, 6)), (15, (0, 1)), (50, (7.5, -3)), (85, (15, 1)), (100, (17, 6))], ease=LINEAR)
    sc = kf([(0, 0), (15, 1), (50, 1.5), (85, 1), (100, 0)], ease=LINEAR)
    starts = [0, 3, 6, 10, 13]
    for i, ((c1, c2), s) in enumerate(zip(cols, starts)):
        for sz in (2, 3, 4):
            gg = Grid().R(0, 0, sz, sz, c1)
            if sz >= 3: gg.S(0, 0, c2)
            extra_l.append(prop(f"dp{i}-{sz}", gg))
        def size_at(k, s=s):
            age = (k - s) % N
            v = sc(100.0 * age / N)
            return 4 if v >= 1.25 else 3 if v >= 0.75 else 2 if v >= 0.3 else 0
        def pos_at(k, s=s):
            age = (k - s) % N
            p = path(100.0 * age / N)
            return (u2a(p[0]), u2a(p[1]))
        a.move(f"dm{i}", pos_at)
        vs = "\n".join(a.vwrap(f"dv{i}-{sz}", lambda k, sz=sz, size_at=size_at: size_at(k) == sz, use(f"dp{i}-{sz}")) for sz in (2, 3, 4))
        pkts.append(f'<g class="dm{i}">\n{vs}\n</g>')
    inner = "\n".join([
        use("torso"), arm_el(a, "L", arm_l, "ar-l"), arm_el(a, "R", arm_r, "ar-r"),
        use("eyes-happy"), use("smile"),
    ])
    scene = "\n".join([use("shadow"), "\n".join(pkts), legs_el(a), a.wrap("bob", body, inner)])
    c = "  <!-- Clawd v2 conducting: 2 s loop at 8 fps (16 frames). Calm bob, pincers swoop in opposite phase, five data bits arc over the head. -->"
    return assemble(c, "-15 -25 45 45", a.css(), scene, "\n".join(extra_l))


def build_building():
    FPS, N = 8, 8
    a = Anim(FPS, N)
    dy = [0, -1, -4, -2, 4, 2, 0, 0]
    armdy = [0, -2, -3, 0, -4, -1, 0, 0]
    def body(k): return (0, dy[k])
    eyes = ["open", "open", "wide", "open", "shut", "open", "open", "open"]
    # hammer world poses: (variant, x, y)
    ham = [("up", 27, 6), ("up", 27, 3), ("up", 27, -1), ("down", 29, 11), ("down", 29, 15), ("down", 29, 12), ("up", 27, 8), ("up", 27, 6)]
    hot = ["#FF5252"] * 8
    hot[4] = "#FFF59D"; hot[5] = "#FFC107"
    extra = "\n".join([
        prop("hardhat", hat_grid()), prop("anvil", anvil_grid(29, 26)),
        prop("hammer-up", hammer_up()), prop("hammer-down", hammer_down()),
        prop("spark-b", spark_grid(True)), prop("spark-s", spark_grid(False)),
        prop("sweat", Grid().R(0, 1, 2, 2, "#40C4FF").S(0, 0, "#BDEFFF") if False else Grid().R(0, 1, 2, 2, "#40C4FF").S(0, 1, "#BDEFFF").S(1, 0, "#40C4FF")),
        prop("wshadow", Grid().R(28, 31, 11, 1, "#000000@0.3")),
    ])
    hup = a.vwrap("h-up", lambda k: ham[k][0] == "up", "")  # placeholder (not used)
    a.tracks.pop()  if hup == "" and False else None
    hams = []
    for var in ("up", "down"):
        def pos(k, var=var):
            v, x, y = ham[k]
            return (x, y) if v == var else (0, 0)
        # place with x/y via move track; element at origin
        a.move(f"hm-{var}", lambda k, pos=pos: pos(k))
        a.show(f"hv-{var}", lambda k, var=var: ham[k][0] == var)
        hams.append(f'<g class="hv-{var}"><g class="hm-{var}"><use href="#hammer-{var}"/></g></g>')
    hotel = '<path class="hot" d="M31 24h4v2h-4z"/>'
    a.fill("hot", lambda k: hot[k])
    # sparks
    dirs = [(8, -12), (14, -2), (6, 6)]
    spk = []
    for i, (dx, dyy) in enumerate(dirs):
        def sp(k, dx=dx, dyy=dyy):
            if k == 4: return (35, 22, "b")
            if k == 5: return (35 + dx // 2, 22 + dyy // 2, "b")
            if k == 6: return (35 + dx, 22 + dyy, "s")
            return None
        a.move(f"sm{i}", lambda k, sp=sp: ((sp(k) or (0, 0, 0))[0], (sp(k) or (0, 0, 0))[1]))
        a.show(f"sv{i}", lambda k, sp=sp: sp(k) is not None)
        spk.append(f'<g class="sv{i}"><g class="sm{i}"><use href="#spark-b"/></g></g>')
    # sweat drop flies back
    sw = {1: (2, 16), 2: (1, 13), 3: (0, 10), 4: (-2, 7), 5: (-3, 4)}
    a.move("swm", lambda k: sw.get(k, (0, 0)))
    a.show("swv", lambda k: k in sw)
    sweat = '<g class="swv"><g class="swm"><use href="#sweat"/></g></g>'
    inner = "\n".join([
        use("torso"), arm_el(a, "L", lambda k: (0, 0), "ar-l"), arm_el(a, "R", lambda k: (0, armdy[k]), "ar-r"),
        eyes_el(a, lambda k: eyes[k], None, "ey"), use("hardhat"),
    ])
    scene = "\n".join([use("shadow"), use("wshadow"), use("anvil"), hotel, legs_el(a), a.wrap("bounce", body, inner),
                       "\n".join(hams), "\n".join(spk), sweat])
    c = "  <!-- Clawd v2 building: 1 s loop at 8 fps (8 frames). Hard hat, hammer wind-up, strike on the anvil with sparks and a squash. -->"
    return assemble(c, "-15 -25 45 45", a.css(), scene, extra)
