"""Re-render the OLD svgs with the candidate params and diff against the committed headers."""
import subprocess, sys, shutil
sys.path.insert(0, str(Path := __import__("pathlib").Path(__file__).parent))
from common import *
sys.path.insert(0, str(REPO / "tools"))
import crop_sprites as cs

only = sys.argv[1:] or list(ANIMS)
out = PREV / "_repro_old"
out.mkdir(parents=True, exist_ok=True)
for a in only:
    stem, fps, dur, prefix = ANIMS[a]
    fdir = out / a
    if fdir.exists(): shutil.rmtree(fdir)
    subprocess.run([str(PY), str(REPO/"tools"/"svg2frames.py"), str(SVG_DIR/f"{stem}.svg"), str(fdir),
                    "--fps", str(fps), "--duration", dur, "--scale", str(SCALE)], check=True, capture_output=True)
    hdr = out / f"sprite_{a}.h"
    subprocess.run([str(PY), str(REPO/"tools"/"png2rgb565.py"), str(fdir), str(hdr), "--name", prefix], check=True, capture_output=True)
    res = cs.process_sprite(hdr)
    new = cs.parse_header(hdr); old = cs.parse_header(ASSETS/f"sprite_{a}.h")
    same_dims = (new["width"], new["height"], new["frame_count"]) == (old["width"], old["height"], old["frame_count"])
    nf = [cs.decode_frame(new["rle_data"], new["frame_offsets"], i, new["width"], new["height"]) for i in range(new["frame_count"])]
    of = [cs.decode_frame(old["rle_data"], old["frame_offsets"], i, old["width"], old["height"]) for i in range(old["frame_count"])]
    diff = None
    if same_dims:
        diff = sum(1 for p, q in zip(nf, of) for x, y in zip(p, q) if x != y)
    print(f"{a:11s} new {new['width']}x{new['height']}x{new['frame_count']}  old {old['width']}x{old['height']}x{old['frame_count']}  "
          f"crop_y={res.get('crop_y')} bottom_removed={res.get('bottom_removed')} diff_px={diff}")
