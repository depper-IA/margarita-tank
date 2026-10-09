"""Header <-> image helpers (decode sprite headers into RGBA frames, contact sheets, comparisons)."""
import sys
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
from common import *
sys.path.insert(0, str(REPO / "tools"))
import crop_sprites as cs

KEY = 0x18C5

def px565(v):
    r = (v >> 11) & 31; g = (v >> 5) & 63; b = v & 31
    return ((r << 3) | (r >> 2), (g << 2) | (g >> 4), (b << 3) | (b >> 2), 255)

def load_frames(path):
    h = cs.parse_header(Path(path))
    frames = []
    for i in range(h["frame_count"]):
        px = cs.decode_frame(h["rle_data"], h["frame_offsets"], i, h["width"], h["height"])
        im = Image.new("RGBA", (h["width"], h["height"]), (0, 0, 0, 0))
        im.putdata([(0, 0, 0, 0) if v == KEY else px565(v) for v in px])
        frames.append(im)
    return h, frames

def rle_bytes(h):
    return len(h["rle_data"]) * 2

def font(size):
    for p in ("/System/Library/Fonts/Menlo.ttc", "/System/Library/Fonts/Supplemental/Courier New.ttf"):
        try: return ImageFont.truetype(p, size)
        except Exception: pass
    return ImageFont.load_default()

def sheet(frames, out, zoom=2, bg=(36, 52, 92), cols=None, label=True, maxw=2400):
    n = len(frames); w, h = frames[0].size
    cw, ch = w * zoom, h * zoom
    pad = 4; lab = 14 if label else 0
    if cols is None:
        cols = max(1, min(n, (maxw) // (cw + pad)))
    rows = (n + cols - 1) // cols
    W = cols * (cw + pad) + pad; H = rows * (ch + lab + pad) + pad
    img = Image.new("RGB", (W, H), bg)
    d = ImageDraw.Draw(img); f = font(11)
    for i, fr in enumerate(frames):
        x = pad + (i % cols) * (cw + pad); y = pad + (i // cols) * (ch + lab + pad)
        tile = Image.new("RGBA", (w, h), bg + (255,)); tile.alpha_composite(fr)
        img.paste(tile.resize((cw, ch), Image.NEAREST).convert("RGB"), (x, y + lab))
        d.rectangle([x - 1, y + lab - 1, x + cw, y + lab + ch], outline=(60, 78, 124))
        if label: d.text((x + 1, y), str(i), fill=(200, 200, 210), font=f)
    out = Path(out); out.parent.mkdir(parents=True, exist_ok=True)
    img.save(out)
    return img.size
