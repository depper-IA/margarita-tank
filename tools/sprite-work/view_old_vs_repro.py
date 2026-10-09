import sys
from hdr import *
a = sys.argv[1]
ho, fo = load_frames(ASSETS/f"sprite_{a}.h")
hn, fn = load_frames(PREV/"_repro_old"/f"sprite_{a}.h")
sheet(fo, PREV/"_repro_old"/f"{a}_OLD.png", zoom=1, cols=10)
sheet(fn, PREV/"_repro_old"/f"{a}_REPRO.png", zoom=1, cols=10)
