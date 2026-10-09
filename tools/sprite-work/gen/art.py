"""Tiny pixel-art toolkit: grids, masks, outlines and SVG path emission (art-pixel coordinates)."""
from collections import defaultdict

N4 = ((1, 0), (-1, 0), (0, 1), (0, -1))


class Grid:
    """Sparse pixel grid. Colours are strings: '#RRGGBB' or '#RRGGBB@alpha'."""

    def __init__(self):
        self.p = {}

    def R(self, x, y, w, h, c):
        for j in range(y, y + h):
            for i in range(x, x + w):
                self.p[(i, j)] = c
        return self

    def S(self, x, y, c):
        self.p[(x, y)] = c
        return self

    def pix(self, pts, c):
        for (x, y) in pts:
            self.p[(x, y)] = c
        return self

    def merge(self, other, dx=0, dy=0):
        for (x, y), c in other.p.items():
            self.p[(x + dx, y + dy)] = c
        return self

    def bbox(self):
        xs = [k[0] for k in self.p]; ys = [k[1] for k in self.p]
        return min(xs), min(ys), max(xs), max(ys)


def rect_mask(x, y, w, h):
    return {(i, j) for j in range(y, y + h) for i in range(x, x + w)}


def disc_mask(cx, cy, r):
    """Pixel disc: pixel (x, y) is in when its centre is within r of (cx, cy) (cx, cy may be .5)."""
    out = set()
    for j in range(int(cy - r) - 1, int(cy + r) + 2):
        for i in range(int(cx - r) - 1, int(cx + r) + 2):
            if (i + 0.5 - cx) ** 2 + (j + 0.5 - cy) ** 2 <= r * r:
                out.add((i, j))
    return out


def paint(g, mask, fill, line, solid=None):
    """Fill a mask; pixels touching empty space become the outline (4-neighbourhood).
    `solid` counts as filled for that test (so a prop can sit against the body without a seam)."""
    for (x, y) in mask:
        edge = False
        for dx, dy in N4:
            q = (x + dx, y + dy)
            if q not in mask and not (solid and q in solid):
                edge = True
                break
        g.p[(x, y)] = line if edge else fill
    return g


def runs_to_rects(pixels):
    """Greedy rectangle cover of a pixel set: merge horizontal runs, then identical runs in
    consecutive rows. Returns [(x, y, w, h)]."""
    rows = defaultdict(list)
    for (x, y) in pixels:
        rows[y].append(x)
    rects = []
    open_runs = {}  # (x0, x1) -> y_start
    prev_y = None
    for y in sorted(rows):
        xs = sorted(rows[y])
        runs = []
        s = p = xs[0]
        for x in xs[1:]:
            if x == p + 1:
                p = x
            else:
                runs.append((s, p)); s = p = x
        runs.append((s, p))
        if prev_y is not None and y != prev_y + 1:
            for (x0, x1), ys in open_runs.items():
                rects.append((x0, ys, x1 - x0 + 1, prev_y - ys + 1))
            open_runs = {}
        cur = {}
        for r in runs:
            cur[r] = open_runs.pop(r) if r in open_runs else y
        for (x0, x1), ys in open_runs.items():
            rects.append((x0, ys, x1 - x0 + 1, y - ys))
        open_runs = cur
        prev_y = y
    for (x0, x1), ys in open_runs.items():
        rects.append((x0, ys, x1 - x0 + 1, prev_y - ys + 1))
    return rects


def split_color(c):
    if "@" in c:
        h, a = c.split("@")
        return h, float(a)
    return c, 1.0


def to_paths(g, order=None, indent="    "):
    """SVG <path> elements, one per colour, in first-use order (or `order`)."""
    by = defaultdict(set)
    seq = []
    for pt, c in g.p.items():
        if c not in by:
            seq.append(c)
        by[c].add(pt)
    if order:
        seq = [c for c in order if c in by] + [c for c in seq if c not in order]
    out = []
    for c in seq:
        rects = runs_to_rects(by[c])
        rects.sort(key=lambda r: (r[1], r[0]))
        d = "".join(f"M{x} {y}h{w}v{h}h-{w}z" for x, y, w, h in rects)
        hexc, a = split_color(c)
        op = f' fill-opacity="{a:g}"' if a < 1 else ""
        out.append(f'{indent}<path fill="{hexc}"{op} d="{d}"/>')
    return "\n".join(out)


def ascii_dump(g, palette_chars=None, box=None):
    x0, y0, x1, y1 = box or g.bbox()
    chars = {}
    sym = "ox#%&*+=@$ABCDEFGHJKLMNPQRSTUVWXYZ"
    lines = []
    for y in range(y0, y1 + 1):
        row = ""
        for x in range(x0, x1 + 1):
            c = g.p.get((x, y))
            if c is None:
                row += "."
            else:
                if c not in chars:
                    chars[c] = (palette_chars or {}).get(c) or sym[len(chars) % len(sym)]
                row += chars[c]
        lines.append(f"{y:3d} {row}")
    return "\n".join(lines) + "\n   " + "  ".join(f"{v}={k}" for k, v in chars.items())
