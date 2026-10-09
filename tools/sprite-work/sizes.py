import sys
from hdr import *
for f in sorted(Path(sys.argv[1]).glob("sprite_*.h")):
    h=cs.parse_header(f); print(f.stem, h["frame_count"], h["width"], h["height"], rle_bytes(h))
