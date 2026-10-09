import sys
from hdr import *
for a in sys.argv[2:]:
    z=int(sys.argv[1]); _,fr=load_frames(PREV/"headers"/f"sprite_{a}.h"); print(a, sheet(fr, PREV/"sheets"/f"{a}.png", zoom=z, maxw=2400))
