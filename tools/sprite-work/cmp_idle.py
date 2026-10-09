import sys
from collections import Counter
from common import *
sys.path.insert(0, str(REPO / "tools"))
import crop_sprites as cs
def load(p):
    h = cs.parse_header(p)
    return h, [cs.decode_frame(h["rle_data"], h["frame_offsets"], i, h["width"], h["height"]) for i in range(h["frame_count"])]
a = sys.argv[1]
oh, of = load(ASSETS/f"sprite_{a}.h")
nh, nf = load(PREV/"_repro_old"/f"sprite_{a}.h")
def pal(fr): return Counter(v for f in fr for v in f)
print("old colors", [(hex(k),v) for k,v in pal(of).most_common(12)])
print("new colors", [(hex(k),v) for k,v in pal(nf).most_common(12)])
# per-frame diffs
if (oh["width"],oh["height"])==(nh["width"],nh["height"]):
    print([sum(1 for x,y in zip(p,q) if x!=y) for p,q in zip(nf,of)][:30])
