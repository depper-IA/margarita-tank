from svgbuild import *
from props import *
from anims_a import u2a
from rig import EYE


def build_happy():
    FPS, N = 10, 20
    a = Anim(FPS, N)
    lift = [0, 0, 0, -10, -20, -24, -20, -10, 0, 0]
    squash = [0, 0, 3, 0, 0, 0, 0, 0, 3, 0]
    L = lambda k: lift[k % 10]
    def crab(k): return (0, L(k))
    def body(k): return (0, squash[k % 10])
    def shadow_pick(k):
        h = -L(k)
        return "shadow" if h < 6 else "shadow-sm" if h < 16 else "shadow-xs"
    sh = variant_el(a, "sh", ["shadow", "shadow-sm", "shadow-xs"], shadow_pick)
    def arm_l(k): return (-2, -4) if k % 2 == 0 else (-3, -9)
    def arm_r(k): return (2, -4) if k % 2 == 0 else (3, -9)
    inner = "\n".join([
        use("torso"), arm_el(a, "L", arm_l, "ar-l"), arm_el(a, "R", arm_r, "ar-r"),
        use("eyes-happy"), use("blush"), use("smile-open"),
    ])
    crab_el = a.wrap("hop", crab, "\n".join([legs_el(a), a.wrap("sq", body, inner)]))
    cols = ["#FFD700", "#FFA000", "#FFF59D", "#FFC107", "#FFF59D", "#FFD700"]
    pos = [(-8, -4), (36, -8), (40, 20), (-12, 24), (14, -16), (-4, 12)]
    starts = [0, 3, 6, 9, 12, 7]
    extra, sp = [], []
    for i, (c, (x, y), s) in enumerate(zip(cols, pos, starts)):
        full = star(c)
        dot = Grid().S(2, 2, "#FFF8D6")
        ring = Grid()
        for pt, cc in full.p.items():
            if cc != "#FFF8D6": ring.p[pt] = cc
        extra += [prop(f"sp{i}-dot", dot), prop(f"sp{i}-star", full), prop(f"sp{i}-ring", ring)]
        def ph(k, s=s):
            age = (k - s) % N
            return "dot" if age == 2 else "star" if age in (3, 4) else "ring" if age == 5 else None
        els = "\n".join(a.vwrap(f"spv{i}-{t}", lambda k, t=t, ph=ph: ph(k) == t, use(f"sp{i}-{t}")) for t in ("dot", "star", "ring"))
        sp.append(f'<g transform="translate({x - 2} {y - 2})">\n{els}\n</g>')
    scene = "\n".join(["\n".join(sp), sh, crab_el])
    c = "  <!-- Clawd v2 happy: 2 s loop at 10 fps (20 frames): two hops with squash, flapping pincers, happy eyes, twinkling sparkles. Sparkle timing is explicit per frame (no <use> + CSS variable delays). -->"
    return assemble(c, "-12 -15 40 40", a.css(), scene, "\n".join(extra))


def zglyph(n, color, bold=False):
    g = Grid()
    g.R(0, 0, n, 1, color); g.R(0, n - 1, n, 1, color)
    if bold and n >= 7:
        g.R(0, 1, n, 1, color); g.R(0, n - 2, n, 1, color)
    for r in range(1, n - 1):
        g.S(n - 1 - r, r, color)
        if n >= 7: g.S(n - 2 - r + (1 if r == n - 2 else 0), r, color)
    return g


def build_sleeping():
    FPS, N = 6, 36
    a = Anim(FPS, N)
    seq = [10, 10, 10, 11, 11, 12, 12, 12, 11, 11, 10, 10, 10, 10, 10, 10, 10, 10]
    H = lambda k: seq[k % 18]
    legs = []
    for i in range(1, 5):
        legs.append(a.wrap(f"lu{i}", lambda k: (0, -(H(k) - 10)), use(f"leg-up{i}")))
    bodies = []
    for h in (10, 11, 12):
        bodies.append(a.vwrap(f"bh{h}", lambda k, h=h: H(k) == h,
                              "\n".join([use(f"torso-sploot-{h}"), use(f"arm-sploot-l-{h}"), use(f"arm-sploot-r-{h}")])))
    face = "\n".join([
        a.wrap("sl-eyes", lambda k: (0, 6 - (H(k) - 10)), use("eyes-shut")),
        a.wrap("sl-blush", lambda k: (0, 6 - (H(k) - 10)), use("blush")),
    ])
    # zzz
    zcols = ["#90A4AE", "#B0BEC5", "#CFD8DC"]
    specs = [  # pos (units), scale, base size (art px), delay frames
        ([(0, (5, 8)), (30, (9, 4)), (50, (4, 0)), (70, (8, -4)), (100, (6, -8))], [(0, .4), (30, .6), (50, .8), (70, 1), (100, 1.1)], 8, 0),
        ([(0, (8, 9)), (30, (5, 5)), (50, (9, 1)), (70, (6, -3)), (100, (8, -7))], [(0, .3), (30, .5), (50, .7), (70, .9), (100, 1.0)], 6, 12),
        ([(0, (6, 7)), (30, (9, 3)), (50, (4, -1)), (70, (8, -5)), (100, (5, -9))], [(0, .5), (30, .7), (50, .9), (70, 1.1), (100, 1.2)], 8, 24),
    ]
    op = kf([(0, 0), (10, 1), (90, .8), (100, 0)], ease=LINEAR)
    extra, zs = [], []
    for i, ((pp, ss, base, dl), col) in enumerate(zip(specs, zcols)):
        pk, sk = kf(pp), kf(ss)
        sizes = sorted({max(5, min(9, rhu(base * sk(p)))) | 1 for p in range(0, 101)})
        for n in sizes:
            extra.append(prop(f"z{i}-{n}", zglyph(n, col, bold=True)))
        def state(k, pk=pk, sk=sk, base=base, dl=dl):
            age = (k - dl) % N
            p = 100.0 * age / N
            o = op(p)
            if o < 0.2: return None
            n = max(5, min(9, rhu(base * sk(p)))) | 1
            v = pk(p)
            return (n, rhu(v[0] * 2), rhu(v[1] * 2), 1 if o > .85 else .7 if o > .5 else .4)
        def zpos(k, state=state):
            s = state(k)
            return (s[1], s[2]) if s else (0, 0)
        a.move(f"zm{i}", zpos)
        a.show(f"zo{i}", lambda k, state=state: (state(k)[3] if state(k) else 0))
        vs = "\n".join(a.vwrap(f"zv{i}-{n}", lambda k, n=n, state=state: (state(k) or (0,))[0] == n, use(f"z{i}-{n}")) for n in sizes)
        zs.append(f'<g class="zo{i}"><g class="zm{i}">\n{vs}\n</g></g>')
    scene = "\n".join([use("shadow-wide"), "\n".join(legs), "\n".join(bodies), face, "\n".join(zs)])
    c = "  <!-- Clawd v2 sleeping: 6 s loop at 6 fps (36 frames). Sploot pose, two slow breaths per loop (the v1 4.5 s breath did not loop), three Zs floating up on the original 6 s cycle. -->"
    return assemble(c, "-10 -20 40 40", a.css(), scene, "\n".join(extra))


def build_debugger():
    FPS, N = 8, 96
    a = Anim(FPS, N)
    def phase(k):
        t = (k / FPS) % 4.0 / 4.0
        u = t * 2 if t < .5 else 2 - t * 2
        return EASE_IO(u)
    def body(k): return (u2a(-2 + 5 * phase(k)), 2)
    def legs_f(k):
        A = (k % 4) < 2
        bx = body(k)[0]
        return [(bx, -2 if A else 0), (bx, 0 if A else -2), (bx, -2 if A else 0), (bx, 0 if A else -2)]
    def sh(k): return (body(k)[0], 0)
    # magnifying glass
    GL = Grid()
    cx, cy, r = 21, 15, 7
    outer = disc_mask(cx, cy, r)
    inner = disc_mask(cx, cy, 5)
    paint(GL, outer, STEEL, STEELLINE)
    for (x, y) in outer:
        if (x, y) in inner:
            GL.p[(x, y)] = "#CFE9EE"
        elif GL.p[(x, y)] == STEEL:
            if (x + y) < (cx + cy - 2): GL.p[(x, y)] = STEELL
            elif (x + y) > (cx + cy + 2): GL.p[(x, y)] = STEELD
    GL.R(19, 12, 4, 6, EYE)
    GL.S(19, 12, WH_)
    GL.R(16, 10, 3, 1, WH_); GL.S(16, 11, WH_)
    HD = Grid()
    for i in range(5):
        HD.R(24 + i, 19 + i, 2, 1, WOOD); HD.S(26 + i, 19 + i, WOODD)
    dyg = lambda k: (0, -1 if 6 <= (k % 24) < 18 else 0)
    extra = "\n".join([prop("lens", GL), prop("handle", HD)])
    glass = a.wrap("glass", dyg, "\n".join([use("handle"), use("lens")]))
    inner_b = "\n".join([
        use("torso"),
        arm_el(a, "L", lambda k: (2, -2), "ar-l"),
        use("eye-l-squint"),
        arm_el(a, "R", lambda k: (0, 0), "ar-r"),
        glass,
    ])
    scene = "\n".join([a.wrap("dsh", sh, use("shadow")), legs_el(a, legs_f), a.wrap("hunch", body, inner_b)])
    c = "  <!-- Clawd v2 debugger: 12 s loop at 8 fps (96 frames). Hunched crab sneaks left and right (3 round trips), legs tiptoe in pairs, magnifier over the right eye. -->"
    return assemble(c, "-15 -25 45 45", a.css(), scene, extra)

WH_ = "#FFFFFF"


def build_waiting():
    FPS, N = 8, 16
    a = Anim(FPS, N)
    eye = lambda k: "shut" if k in (12, 13) else "wide"
    WAVE = [(-5, -6), (-3, -7), (-1, -6), (-3, -7)]   # a real wave: the pincer swings out and back
    def arm_l(k): return WAVE[(k // 2) % 4]
    def leg4(k): return [(0, 0)] * 3 + [(0, -2 if (k % 4) < 2 else 0)]
    def b(k): return (0, (k // 4) % 2)
    m = rect_mask(17, 0, 12, 10)
    for c in ((17, 0), (28, 0), (17, 9), (28, 9)): m.discard(c)
    m |= {(21, 10), (20, 11)}
    bg = Grid(); paint(bg, m, PAPER, INK)
    bang = Grid().R(22, 2, 2, 4, BANG).R(22, 7, 2, 1, BANG)
    extra = "\n".join([prop("wbubble", bg), prop("wbang", bang)])
    inner = "\n".join([
        use("torso"), arm_el(a, "L", arm_l, "ar-l"), use("arm-r"),
        eyes_el(a, eye, None, "ey"), use("blush"), use("smile"),
    ])
    bub = a.wrap("bub", b, "\n".join([use("wbubble"), a.vwrap("bang", lambda k: (k % 8) < 6, use("wbang"))]))
    scene = "\n".join([use("shadow"), legs_el(a, leg4), inner, bub])
    c = "  <!-- Clawd v2 waiting_reply (new): 2 s loop at 8 fps (16 frames). Turn finished, waiting for the next prompt: wide eyes toward the viewer, blush and smile, left pincer waves, right back foot taps, bubble hops with a blinking bang. -->"
    return assemble(c, "-15 -25 45 45", a.css(), scene, extra)


BUILDERS = {
    "clawd-happy-v2": build_happy,
    "clawd-sleeping-v2": build_sleeping,
    "clawd-working-debugger-v2": build_debugger,
    "clawd-waiting-reply-v2": build_waiting,
}
