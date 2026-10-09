"""SVG assembly: per-frame step tracks (CSS keyframes) + rig/prop defs + scene body."""
import math, re
from rig import rig_defs, PARTS


def rhu(x):
    """Round half up (not banker's)."""
    return int(math.floor(x + 0.5))


# ---- easing / sampling of old-style keyframes (percent -> value) ----
def _bezier(x1, y1, x2, y2):
    def f(t):
        if t <= 0: return 0.0
        if t >= 1: return 1.0
        lo, hi = 0.0, 1.0
        for _ in range(40):
            m = (lo + hi) / 2
            bx = 3 * (1 - m) ** 2 * m * x1 + 3 * (1 - m) * m ** 2 * x2 + m ** 3
            if bx < t: lo = m
            else: hi = m
        m = (lo + hi) / 2
        return 3 * (1 - m) ** 2 * m * y1 + 3 * (1 - m) * m ** 2 * y2 + m ** 3
    return f


EASE_IO = _bezier(.42, 0, .58, 1)
LINEAR = lambda t: t


def kf(points, ease=EASE_IO):
    """points: [(pct, value)], value float or tuple. Returns f(pct) with eased interpolation."""
    pts = sorted(points, key=lambda p: p[0])
    def f(p):
        if p <= pts[0][0]: return pts[0][1]
        if p >= pts[-1][0]: return pts[-1][1]
        for (p0, v0), (p1, v1) in zip(pts, pts[1:]):
            if p0 <= p <= p1:
                if p1 == p0: return v1
                t = ease((p - p0) / (p1 - p0))
                if isinstance(v0, tuple):
                    return tuple(a + (b - a) * t for a, b in zip(v0, v1))
                return v0 + (v1 - v0) * t
        return pts[-1][1]
    return f


def pct_fmt(x):
    s = f"{x:.4f}".rstrip("0").rstrip(".")
    return s + "%"


class Anim:
    def __init__(self, fps, n):
        self.fps, self.n = fps, n
        self.dur = n / fps
        self.tracks = []   # (cls, prop, [value strings per frame])

    @property
    def dur_s(self):
        d = self.dur
        return f"{d:g}s"

    def _add(self, cls, prop, vals):
        assert len(vals) == self.n, (cls, len(vals), self.n)
        self.tracks.append((cls, prop, vals))
        return cls

    def move(self, cls, f):
        """f(k) -> (dx, dy) in art px (ints)."""
        vals = []
        for k in range(self.n):
            dx, dy = f(k)
            vals.append(f"translate({int(dx)}px, {int(dy)}px)")
        return self._add(cls, "transform", vals)

    def show(self, cls, f):
        """f(k) -> bool or opacity float."""
        vals = []
        for k in range(self.n):
            v = f(k)
            v = 1 if v is True else 0 if v is False else v
            vals.append(f"{v:g}")
        return self._add(cls, "opacity", vals)

    def fill(self, cls, f):
        return self._add(cls, "fill", [f(k) for k in range(self.n)])

    def css(self, indent="      "):
        out = []
        for cls, prop, vals in self.tracks:
            out.append(f"{indent}.{cls} {{ animation: {cls} {self.dur_s} infinite step-end; }}")
        for cls, prop, vals in self.tracks:
            lines = [f"{indent}@keyframes {cls} {{"]
            prev = None
            for k, v in enumerate(vals):
                if v == prev:
                    continue
                pc = 0 if k == 0 else 100 * (k - 0.5) / self.n
                lines.append(f"{indent}  {pct_fmt(pc)} {{ {prop}: {v}; }}")
                prev = v
            lines.append(f"{indent}}}")
            out.append("\n".join(lines))
        text = "\n".join(out)
        # svg2frames auto-detects the duration with a regex: make sure no class name fools it
        found = [float(m.group(1)[:-1]) if m.group(1).endswith("s") and not m.group(1).endswith("ms") else float(m.group(1)[:-2]) / 1000
                 for m in re.finditer(r"animation\s*:\s*[^;{]+?(\d+(?:\.\d+)?(?:ms|s))", text)]
        assert found and abs(max(found) - self.dur) < 1e-9, (max(found), self.dur)
        return text


def use(pid, extra=""):
    return f'<use href="#{pid}"{(" " + extra) if extra else ""}/>'


def g(cls, *inner, attrs=""):
    body = "\n".join(inner)
    a = f' class="{cls}"' if cls else ""
    return f"<g{a}{(' ' + attrs) if attrs else ''}>\n{body}\n</g>"


def ind(text, n):
    pad = " " * n
    return "\n".join(pad + ln if ln.strip() else ln for ln in text.split("\n"))


def used_ids(*texts):
    ids = set()
    for t in texts:
        ids.update(re.findall(r'href="#([\w-]+)"', t))
    return ids


def assemble(comment, viewbox, css, body, extra_defs="", width=500, height=500):
    rig_ids = used_ids(body, extra_defs) & set(PARTS)
    defs = rig_defs(rig_ids)
    parts = ['<svg xmlns="http://www.w3.org/2000/svg" viewBox="%s" width="%d" height="%d">' % (viewbox, width, height)]
    if comment:
        parts.append(comment.rstrip())
    parts.append("  <defs>")
    if css:
        parts.append("    <style>")
        parts.append(css)
        parts.append("    </style>")
    parts.append("    <!-- ===== rig: shared Clawd v2 parts, identical in every clawd-*-v2.svg (see clawd-static-base-v2.svg) ===== -->")
    parts.append(defs)
    if extra_defs.strip():
        parts.append("    <!-- ===== props used by this animation ===== -->")
        parts.append(extra_defs.rstrip())
    parts.append("  </defs>")
    parts.append('  <g transform="scale(.5)">')
    parts.append(ind(body.strip("\n"), 4))
    parts.append("  </g>")
    parts.append("</svg>")
    return "\n".join(parts) + "\n"


# ---- composition helpers bound to an Anim ----
def _wrap(self, cls, f, inner):
    vals = [tuple(f(k)) for k in range(self.n)]
    if all(v == (0, 0) for v in vals):
        return inner
    self.move(cls, lambda k: vals[k])
    return g(cls, inner)


def _vwrap(self, cls, f, inner):
    vals = [f(k) for k in range(self.n)]
    if all(v is True or v == 1 for v in vals):
        return inner
    if all(v is False or v == 0 for v in vals):
        return ""
    self.show(cls, lambda k: vals[k])
    return g(cls, inner)


Anim.wrap = _wrap
Anim.vwrap = _vwrap


DEFAULT_BODY = (4, 25, 12, 14)   # left outline col, right outline col, top row, height


def link_grid_for(side, pos, body):
    """Forearm (6-row horizontal band and/or 4-col vertical band, drawn in front of the torso edge) that
    joins a pincer to the body whenever the pincer is raised or pushed away from it. None when it touches."""
    from rig import LN, LT, SH, BD
    from art import Grid
    eL, eR, top, h = body
    dx, dy = pos
    ct = 15 + dy                       # claw top row
    ix = (4 + dx) if side == "L" else (25 + dx)
    gap = (eL - ix) if side == "L" else (ix - eR)
    g = Grid()
    t = max(top + 1, min(ct + 1, top + h - 7))
    need_h = gap > 0
    target = (t + 1) if need_h else (top + 3)
    need_v = (ct + 7) < (t if need_h else top + 1)
    if not need_h and not need_v:
        return None
    if need_h:
        x0, x1 = (ix, eL + 1) if side == "L" else (eR - 1, ix)
        w = x1 - x0 + 1
        for j, c in enumerate((LN, LT, BD, BD, SH, LN)):
            g.R(x0, t + j, w, 1, c)
    if need_v:
        vx = ix - 3 if side == "L" else ix
        for i, c in enumerate((LN, LT, SH, LN)):
            g.R(vx + i, ct + 7, 1, target - (ct + 7) + 1, c)
    return g


def arm_el(a, side, pos_fn, name, body_fn=None):
    """Pincer with automatic variant: fused (arm-x) when it sits on the body side outline, free elsewhere.
    A free pincer that is not touching the body gets a forearm (link) so it never looks detached.
    pos_fn(k) is the offset from the default rest spot; body_fn(k) = (left outline col, right outline col, top row, height)."""
    from rig import to_paths
    s = side.lower()
    bodies = [tuple(body_fn(k)) if body_fn else DEFAULT_BODY for k in range(a.n)]
    pos = []
    att = []
    for k in range(a.n):
        dx, dy = tuple(pos_fn(k))
        eL, eR, top, h = bodies[k]
        d = ((4 + dx) - eL) if side == "L" else (eR - (25 + dx))     # > 0: the pincer overlaps the body
        rows_ok = (16 + dy >= top + 1) and (21 + dy <= top + h - 2)
        if 0 < d <= 2 and rows_ok:                                   # barely overlapping: snap to the edge
            dx = dx - d if side == "L" else dx + d
            d = 0
        pos.append((dx, dy))
        att.append(d == 0 and rows_ok)
    inner = []
    if any(att):
        inner.append(a.vwrap(f"{name}-a", lambda k: att[k], use(f"arm-{s}")))
    if not all(att):
        inner.append(a.vwrap(f"{name}-f", lambda k: not att[k], use(f"arm-{s}-free")))
    claw = a.wrap(name, lambda k: pos[k], "\n".join(i for i in inner if i))
    links = []
    for k in range(a.n):
        g = None if att[k] else link_grid_for(side, pos[k], bodies[k])
        links.append(None if g is None else to_paths(g, indent="  "))
    out = [claw]
    for i, spec in enumerate(sorted({l for l in links if l})):
        out.append(a.vwrap(f"{name}-k{i}", lambda k, spec=spec: links[k] == spec, f"<g>\n{spec}\n</g>"))
    return "\n".join(o for o in out if o)


def eyes_el(a, state_fn, look_fn=None, tag="eyes", pairs=True):
    states = []
    for k in range(a.n):
        s = state_fn(k)
        if s not in states:
            states.append(s)
    parts = []
    for s in states:
        el = use(f"eyes-{s}" if isinstance(s, str) and not s.startswith("eye-") else s)
        parts.append(a.vwrap(f"{tag}-{s}", lambda k, s=s: state_fn(k) == s, el))
    inner = "\n".join(p for p in parts if p)
    if look_fn:
        inner = a.wrap(f"{tag}-look", look_fn, inner)
    return inner


def legs_el(a, f=None, prefix="leg"):
    """f(k) -> [(dx, dy)] * 4; None keeps the legs planted."""
    out = []
    for i in range(1, 5):
        el = use(f"leg{i}")
        if f:
            el = a.wrap(f"{prefix}{i}", lambda k, i=i: f(k)[i - 1], el)
        out.append(el)
    return "\n".join(out)


def variant_el(a, tag, names, pick, wrap_fn=None):
    """Show exactly one of `names` per frame (pick(k) -> name or None)."""
    parts = []
    for nme in names:
        el = use(nme)
        parts.append(a.vwrap(f"{tag}-{nme}", lambda k, nme=nme: pick(k) == nme, el))
    return "\n".join(p for p in parts if p)
