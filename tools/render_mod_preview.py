#!/usr/bin/env python3
"""Check the mod's half-block output against the source PNG frames and write contact sheets.

    deno run --allow-read --unstable-sloppy-imports tools/mod_preview_dump.ts > /tmp/mod.json
    render_mod_preview.py /tmp/mod.json PREVIEWS_DIR OUT_DIR [--scale 6]

For every source frame of every animation it rebuilds the pixel grid from the text cells
(' ' empty, full block fg, upper half fg over bg, lower half fg) and compares it with the
cropped, matte-composited PNG; any difference is an error (exit 1). OUT_DIR gets one sheet per
animation: top row the source frames, bottom row the mod output, 5 evenly spaced frames.
"""

import argparse
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
import svg2mod_frames as g

BG = (0x16, 0x16, 0x16)


def hexrgb(h):
    return tuple(int(h[i:i + 2], 16) for i in (1, 3, 5))


def grid_from_runs(rows):
    """Half-block text rows -> 2D list (2*rows x width) of '#RRGGBB' | None."""
    out = []
    for runs in rows:
        top, bottom = [], []
        for r in runs:
            ch, fg, bgc, n = r["ch"], r.get("fg"), r.get("bg"), r["n"]
            if ch == " ":
                t = b = None
            elif ch == "█":
                t = b = fg
            elif ch == "▀":
                t, b = fg, bgc
            elif ch == "▄":
                t, b = bgc, fg
            else:
                raise ValueError(f"unexpected glyph {ch!r}")
            top += [t] * n
            bottom += [b] * n
        out += [top, bottom]
    return out


def to_image(grid, scale):
    h, w = len(grid), len(grid[0])
    arr = np.zeros((h, w, 3), dtype=np.uint8)
    for y in range(h):
        for x in range(w):
            arr[y, x] = hexrgb(grid[y][x]) if grid[y][x] else BG
    return Image.fromarray(arr).resize((w * scale, h * scale), Image.NEAREST)


def expected_grid(frame):
    return [[None if v == g.TRANSPARENT else f"#{v:06X}" for v in row] for row in frame.tolist()]


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("dump")
    ap.add_argument("previews")
    ap.add_argument("out")
    ap.add_argument("--scale", type=int, default=6)
    a = ap.parse_args(argv)
    data = json.loads(Path(a.dump).read_text())
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    bad = 0
    for name, d in data.items():
        src = g.common_crop(g.load_frames(Path(a.previews) / name))
        assert len(src) == len(d["frames"]), name
        mine_imgs, src_imgs = [], []
        for k, rows in enumerate(d["frames"]):
            got, want = grid_from_runs(rows), expected_grid(src[k])
            if got != want:
                bad += 1
                diff = sum(1 for y in range(len(want)) for x in range(len(want[0])) if got[y][x] != want[y][x])
                print(f"MISMATCH {name} frame {k}: {diff} pixels differ")
            if k in {int(i) for i in np.linspace(0, len(src) - 1, 5)}:
                mine_imgs.append(to_image(got, a.scale))
                src_imgs.append(to_image(want, a.scale))
        w, h = mine_imgs[0].size
        sheet = Image.new("RGB", (len(mine_imgs) * (w + 8), 2 * (h + 8)), BG)
        for i, (s, m) in enumerate(zip(src_imgs, mine_imgs)):
            sheet.paste(s, (i * (w + 8), 0))
            sheet.paste(m, (i * (w + 8), h + 8))
        sheet.save(out / f"{name}.png")
        print(f"{name}: {len(src)} frames checked")
    print("OK" if not bad else f"{bad} frames differ")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
