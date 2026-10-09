import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from svgbuild import *
from rig import P

BIBLE = """  <!--
    CLAWD v2 ART BIBLE
    Grid     : 1 art pixel = 0.5 SVG unit. The body box is 30 x 32 art px (= the old 15 x 16 units), so a
               viewBox kept from the v1 files renders at the same size: at --scale 4 one art pixel is 2 device
               pixels and every edge lands on a whole pixel. Art lives in a <g transform="scale(.5)"> and is
               written in art-pixel integers; props and motion use whole art pixels only (no rotation, no
               scaling, no fractional moves, so nothing is ever anti-aliased).
    Palette  : outline #6B3122 | base #DE886D | light #F3AC90 | specular #FFD3C2 | shade #B8644B
               eyes #1B1311 + white highlight #FFFFFF | blush #EA7C7E | ground shadow black at 30% and 15%.
               Props: hat #F2B630 #FFDB6E #C98918 on #6E4A0C | wood #93603E #5C3922 | steel #A9B2BC #DCE2E8 #6B737D
               on #2F353C | spark #FFD84D | speech bubble paper #FFFFFF on ink #2A1E1A, bang #E25A35.
    Rules    : 1 px outline around every shape (computed as the inner outline of the silhouette). Light comes
               from the top left: light band on the top and left, shade on the bottom and right, one 2x1
               specular. Eyes are 2x4 with a white top-left highlight (wide 2x5, shut 2x1, happy arc, squint 2x2).
               Pincers are solid 6x8 C shapes (body colour, light/shade rim, outline only on the outer silhouette); legs are 2 px wide (shade column + outline
               column, outline foot). Blush and a small smile mark friendly states.
    Rig      : <defs> ids below are the reusable parts; animation files copy the ones they use. Animate them
               by wrapping <use> in a <g class="..."> whose CSS translates whole art pixels (step-end keyframes,
               one key per rendered frame); swap variants (eyes, pincers, shadow) with opacity keyframes.
               Pincer rule: use arm-l / arm-r (open into the body) only at the rest spot or sliding along
               the body side (dy -3..3); use arm-l-free / arm-r-free anywhere else, and add a 4-row forearm
               (light/shade band, see svgbuild.link_spec) whenever a raised pincer is not touching the body.
               Blush is two 4x3 patches #EA7C7E with a lighter #F7A3A1 centre.
  -->"""

body = "\n".join([
    use("shadow"),
    use("leg1"), use("leg2"), use("leg3"), use("leg4"),
    use("torso"), use("arm-l"), use("arm-r"), use("eyes-open"),
])

svg = assemble(BIBLE, "0 0 15 16", "", body, width=300, height=320)
out = Path(sys.argv[1] if len(sys.argv) > 1 else "/tmp/clawd-static-base-v2.svg")
out.write_text(svg)
print("wrote", out, len(svg), "bytes")
