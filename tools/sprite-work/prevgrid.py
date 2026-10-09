import sys
sys.path.insert(0,'/Users/samwilkie/Projects/margarita-tank-worktrees/sprite-work/gen')
from rig import *
from PIL import Image
def png(g, box, out, z=16, bg=(36,52,92)):
    x0,y0,x1,y1=box
    im=Image.new("RGB",((x1-x0+1)*z,(y1-y0+1)*z),bg)
    for (x,y),c in g.p.items():
        if x0<=x<=x1 and y0<=y<=y1:
            h,a=split_color(c); rgb=tuple(int(h[i:i+2],16) for i in (1,3,5))
            rgb=tuple(int(bg[i]*(1-a)+rgb[i]*a) for i in range(3))
            for j in range(z):
                for i in range(z): im.putpixel(((x-x0)*z+i,(y-y0)*z+j),rgb)
    im.save(out)
g=Grid()
for k in ("leg1","leg2","leg3","leg4","torso","arm-l","arm-r","eyes-open","blush","smile"): g.merge(PARTS[k])
png(g,(-1,10,30,31),sys.argv[1])
g2=Grid(); g2.merge(PARTS["torso"]); g2.merge(PARTS["arm-l-free"],-3,-6); g2.merge(link_grid("L",1,5,13)); g2.merge(PARTS["arm-r-free"],3,-4)
png(g2,(-4,5,34,28),sys.argv[2])
