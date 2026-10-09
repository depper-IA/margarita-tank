import sys
from hdr import *
from PIL import Image, ImageDraw
BG=(36,52,92)
rows=[]
OLDBR={"idle":16,"thinking":16,"typing":16,"debugger":15,"building":12,"conducting":13,"happy":35,"sleeping":16}
NEWBR={"happy":36}
for a in ["idle","thinking","typing","debugger","building","conducting","happy","sleeping"]:
    ho,fo=load_frames(ASSETS/f"sprite_{a}.h"); hn,fn=load_frames(PREV/"headers"/f"sprite_{a}.h")
    n=min(len(fo),len(fn)); idxs=sorted({int(i*(n-1)/5) for i in range(6)})
    z=3 if max(ho["width"],hn["width"])<=100 else 2
    PADB=max(OLDBR[a],NEWBR.get(a,16))*z//4; H=max(ho["height"],hn["height"])*z+PADB; Wo=ho["width"]*z; Wn=hn["width"]*z
    cell_w=Wo+Wn+30; img=Image.new("RGB",(cell_w*len(idxs)+10, H+30),BG); d=ImageDraw.Draw(img); f=font(11)
    for c,i in enumerate(idxs):
        x=10+c*cell_w
        for im,w,off in ((fo[i],Wo,0),(fn[i],Wn,Wo+15)):
            t=im.resize((im.width*z,im.height*z),Image.NEAREST)
            # bottom-align on the shared ground line (feet/shadow rows are 16 px above canvas bottom in both)
            br=(OLDBR[a] if off==0 else NEWBR.get(a,16))*z//4
            img.paste(t,(x+off,20+H-t.height-(PADB-br)),t)
        d.text((x,3),f"frame {i}: old | new",fill=(220,220,230),font=f)
        d.line([(x+Wo+7,18),(x+Wo+7,H+25)],fill=(80,100,150))
    img.save(PREV/"sheets"/f"compare-{a}.png"); print(a,img.size)
