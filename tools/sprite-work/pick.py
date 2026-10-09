import sys
from hdr import *
# usage: pick.py anim out.png idx,idx,... [zoom]
a=sys.argv[1]; idx=[int(i) for i in sys.argv[2].split(",")]; out=sys.argv[3]; z=int(sys.argv[4]) if len(sys.argv)>4 else 4
h,fr=load_frames(PREV/"headers"/f"sprite_{a}.h")
sheet([fr[i] for i in idx], out, zoom=z, cols=min(len(idx),5), maxw=2400)
