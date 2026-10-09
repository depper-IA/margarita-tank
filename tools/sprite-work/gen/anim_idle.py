from svgbuild import *

def build():
    FPS, N = 6, 96
    a = Anim(FPS, N)
    pc = lambda k: 100.0 * k / N
    u2a = lambda v: rhu(2 * v)           # units -> art px

    # --- old keyframes (units), sampled at each frame and snapped to the art grid ---
    body_x = kf([(0, 0), (8, 0), (12, 1), (22, 1), (26, 0), (30, .5), (36, .5), (38, 0), (42, -1), (50, -1), (55, 0), (100, 0)])
    body_y = kf([(0, 0), (55, 0), (60, -1), (65, -2), (72, 1), (76, 0), (100, 0)])
    def body(k):
        p = pc(k)
        return (u2a(body_x(p)), u2a(body_y(p)))
    breathe_k = kf([(0, 0), (50, .5), (100, 0)])
    def breathe(k):
        t = (k / FPS) % 3.2
        return (0, u2a(breathe_k(100 * t / 3.2)))
    look_x = kf([(0, 0), (10, 0), (12, 3), (22, 3), (25, 0), (38, 0), (42, -3), (50, -3), (52, 0), (100, 0)])
    def look(k):
        p = pc(k)
        dy = -1 if 60 <= p <= 75 else 0
        return (rhu(look_x(p) * 2 / 3), dy)

    blink_frames = {5, 19, 43, 82}
    yawn_shut = set(range(60, 72))
    def eye_state(k):
        return "shut" if (k in blink_frames or k in yawn_shut) else "open"

    # mouth levels during the yawn
    mouth_lv = {58: 1, 59: 1, 60: 2, 61: 2, 62: 3, 63: 3, 64: 3, 65: 3, 66: 3, 67: 2, 68: 2, 69: 2, 70: 1, 71: 1}
    def mouth_pick(k):
        lv = mouth_lv.get(k)
        return f"mouth-yawn-{lv}" if lv else None

    # tear
    def tear_pos(k):
        return (7, 20 + rhu((k - 63) * 4 / 8)) if 63 <= k <= 71 else None

    # arms
    scratch = {29: (2, -6), 30: (3, -8), 31: (1, -5), 32: (3, -8), 33: (1, -5), 34: (3, -8), 35: (1, -5), 36: (1, -2)}
    yl = kf([(58, (0, 0)), (62, (-2, -4)), (65, (-4, -6)), (72, (0, 2)), (76, (0, 0))])
    def arm_l(k):
        if k in scratch: return scratch[k]
        if 58 <= k <= 76:
            v = yl(pc(k)); return (rhu(v[0]), rhu(v[1]))
        return (0, 0)
    def arm_r(k):
        if 58 <= k <= 76:
            v = yl(pc(k)); return (-rhu(v[0]), rhu(v[1]))
        return (0, 0)
    # scratching leans the body half a unit; fold into body already (0.5u) -> ok

    # shadow follows the body, shrinks while stretched
    def sh_dx(k): return (body(k)[0], 0)
    def sh_small(k): return body(k)[1] <= -3

    shadow = a.wrap("idle-shadow", sh_dx,
                    "\n".join([a.vwrap("sh-n", lambda k: not sh_small(k), use("shadow")),
                               a.vwrap("sh-s", sh_small, use("shadow-sm"))]))
    legs = legs_el(a)
    mouth = variant_el(a, "mo", ["mouth-yawn-1", "mouth-yawn-2", "mouth-yawn-3"], mouth_pick)
    tear_el = a.vwrap("tear-v", lambda k: tear_pos(k) is not None,
                      a.wrap("tear-m", lambda k: ((tear_pos(k) or (7, 20))[0] - 7, (tear_pos(k) or (7, 20))[1] - 20),
                             '<path fill="#40C4FF" d="M7 20h1v2h-1z"/>\n<path fill="#BDEBFF" d="M7 20h1v1h-1z"/>'))
    inner = "\n".join([
        use("torso"),
        arm_el(a, "L", arm_l, "ar-l"),
        arm_el(a, "R", arm_r, "ar-r"),
        eyes_el(a, eye_state, look, "ey"),
        mouth,
        tear_el,
    ])
    body_el = a.wrap("idle-body", body, a.wrap("idle-breathe", breathe, inner))
    scene = "\n".join([shadow, legs, body_el])
    comment = "  <!-- Clawd v2 idle: 16 s loop at 6 fps (96 frames). Same beats as clawd-idle-living.svg: look right, scratch, look left, big yawn with a tear. -->"
    return assemble(comment, "-15 -25 45 45", a.css(), scene)

if __name__ == "__main__":
    import sys
    open(sys.argv[1], "w").write(build())
