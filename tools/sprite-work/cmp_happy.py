import sys
from collections import Counter
from common import *
sys.path.insert(0, str(REPO / "tools"))
import crop_sprites as cs
h = cs.parse_header(PREV/"_repro_old"/"sprite_happy.h")
fr = [cs.decode_frame(h["rle_data"], h["frame_offsets"], i, h["width"], h["height"]) for i in range(h["frame_count"])]
W=h["width"]
for i,f in enumerate(fr):
    rows=[y for y in range(14) if any(f[y*W+x]!=0x18c5 for x in range(W))]
    cols=Counter(f[y*W+x] for y in range(14) for x in range(W) if f[y*W+x]!=0x18c5)
    print(i, rows[:3], dict((hex(k),v) for k,v in cols.most_common(4)))
