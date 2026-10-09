from art import *
INK="#2A1E1A"; PAPER="#FFFFFF"; PAPER_S="#E6DDD8"; BANG="#E25A35"; BLUE="#2F7DE1"
HAT="#F2B630"; HATL="#FFDB6E"; HATD="#C98918"; HATLINE="#6E4A0C"
WOOD="#93603E"; WOODD="#5C3922"
STEEL="#A9B2BC"; STEELL="#DCE2E8"; STEELD="#6B737D"; STEELLINE="#2F353C"
SPARK="#FFD84D"; SPARK2="#FFF59D"

def prop(pid, g, indent="    "):
    return f'{indent}<g id="{pid}">\n{to_paths(g, indent=indent+"  ")}\n{indent}</g>'

def bubble_grid(x, y, w, h, tail=None, fill=PAPER, shade=PAPER_S):
    """Rounded speech bubble (chamfered corners) with ink outline; tail = list of (dx,dy) ink/paper pixels."""
    g = Grid()
    m = rect_mask(x, y, w, h)
    for c in ((x, y), (x + w - 1, y), (x, y + h - 1), (x + w - 1, y + h - 1)):
        m.discard(c)
    paint(g, m, fill, INK)
    g.R(x + 1, y + h - 3, w - 2, 1, shade) if h > 5 else None
    return g

def hat_grid():
    T = 12
    m = Grid(); mk = set()
    mk |= rect_mask(11, T-7, 8, 1) | rect_mask(10, T-6, 10, 1) | rect_mask(9, T-5, 12, 3) | rect_mask(6, T-2, 18, 2)
    paint(m, mk, HAT, HATLINE, solid=rect_mask(4, 12, 22, 14))
    m.R(11, T-6, 3, 1, HATL); m.R(10, T-5, 1, 2, HATL)
    m.R(14, T-6, 2, 4, HATD); m.R(19, T-5, 1, 3, HATD)
    m.R(7, T-1, 16, 1, HATD)
    return m

def anvil_grid(ox=0, oy=0):
    m = Grid(); mk = rect_mask(0, 0, 9, 2) | rect_mask(2, 2, 5, 1) | rect_mask(1, 3, 7, 2)
    paint(m, mk, STEEL, STEELLINE)
    m.R(2, 1, 5, 1, STEELL); m.R(2, 3, 5, 1, STEELD)
    out = Grid(); out.merge(m, ox, oy); return out

def hammer_up():
    """Hammer held upright: head 8x5 on top of a 2 px handle (handle bottom near y=15)."""
    g = Grid()
    g.R(3, 5, 1, 11, WOOD); g.R(4, 5, 1, 11, WOODD)
    mk = rect_mask(0, 0, 8, 5)
    paint(g, mk, STEEL, STEELLINE)
    g.R(1, 1, 6, 1, STEELL); g.R(1, 3, 6, 1, STEELD)
    return g

def hammer_down():
    g = Grid()
    g.R(1, 0, 1, 4, WOOD); g.R(2, 0, 1, 4, WOODD)
    mk = rect_mask(0, 4, 8, 5)
    paint(g, mk, STEEL, STEELLINE)
    g.R(1, 5, 6, 1, STEELL); g.R(1, 7, 6, 1, STEELD)
    return g

def spark_grid(big=True):
    g = Grid()
    if big:
        g.R(0, 0, 2, 2, SPARK); g.S(0, 0, "#FFFFFF")
    else:
        g.R(0, 0, 1, 1, SPARK)
    return g

def star(color, core="#FFF8D6"):
    g = Grid()
    g.S(2, 2, core)
    for dx, dy in ((0, 2), (1, 2), (3, 2), (4, 2), (2, 0), (2, 1), (2, 3), (2, 4)):
        g.S(dx, dy, color)
    return g
