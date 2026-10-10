#!/usr/bin/env python3
"""Turn rendered v2 PNG frame sequences into compact TypeScript data for the Claude Code mod.

Input: one directory of ``frame_*.png`` per animation, as written by
``svg2frames.py --scale 4 --snap exact`` (art pixels are PX x PX device pixels, PX = 2).

For each animation this tool:
  1. verifies every PX x PX block is uniform and downscales to art pixels (no resampling);
  2. composites semi-transparent pixels (shadow, glow) over a matte colour, because a terminal
     cannot blend; fully transparent pixels (alpha <= ALPHA_FLOOR) stay transparent;
  3. crops all frames to ONE bounding box (union over the animation; the ground never jumps)
     and pads the top so the height is even (half blocks draw two pixel rows per text row);
  4. builds a palette (exact colours) and run-length encodes rows;
  5. merges consecutive identical frames into one with a hold count (timing stays exact).

Row syntax: runs ``<c><n>`` joined without separators, ``c`` a palette letter (a-z, A-Z) or
``.`` for transparent, ``n`` omitted when 1. A trailing transparent run is dropped and an empty
row is all transparent. Rows are joined with ``/``.

Usage:
    svg2mod_frames.py --all PREVIEWS_DIR --out claude-mod/margarita-band/hooks/anims-v2
    svg2mod_frames.py FRAMES_DIR --anim idle --fps 6 --out DIR
"""

import argparse
import sys
from collections import Counter
from pathlib import Path

import numpy as np
from PIL import Image

PX = 2
ALPHA_FLOOR = 16
MATTE = (0x26, 0x26, 0x26)
ALPHABET = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"
TRANSPARENT = -1

# anim -> fps of the firmware sprite (see the sprite redesign handoff).
FPS = {
    "idle": 6, "sleeping": 6, "low_battery": 6, "hat_mishap": 6,
    "thinking": 8, "typing": 8, "debugger": 8, "building": 8, "conducting": 8,
    "waiting_reply": 8, "wake": 8, "confused": 8, "dizzy": 8, "sweeping": 8,
    "beacon": 8,
    "happy": 10, "alert": 10,
}
# mod AnimName -> v2 animation that plays it (the v2 idle art is the "living" idle).
ALIASES = {"idle_living": "idle"}


def downscale(arr: np.ndarray, px: int = PX) -> np.ndarray:
    """RGBA device pixels -> RGBA art pixels, exactly; refuses a frame that is not px-aligned."""
    h, w = arr.shape[:2]
    if h % px or w % px:
        raise ValueError(f"frame {w}x{h} is not a multiple of {px}")
    blocks = arr.reshape(h // px, px, w // px, px, 4)
    if not (blocks == blocks[:, :1, :, :1, :]).all():
        raise ValueError(f"frame has pixels that are not {px}x{px} aligned blocks")
    return blocks[:, 0, :, 0, :]


def flatten(art: np.ndarray, matte=MATTE, alpha_floor: int = ALPHA_FLOOR) -> np.ndarray:
    """RGBA art -> int grid of 0xRRGGBB, TRANSPARENT where alpha <= alpha_floor."""
    rgb = art[..., :3].astype(np.float64)
    a = art[..., 3:4].astype(np.float64) / 255.0
    mixed = np.rint(rgb * a + np.array(matte, dtype=np.float64) * (1 - a)).astype(np.int64)
    out = (mixed[..., 0] << 16) | (mixed[..., 1] << 8) | mixed[..., 2]
    out[art[..., 3] <= alpha_floor] = TRANSPARENT
    return out


def load_frames(directory: Path, px: int = PX, matte=MATTE) -> list[np.ndarray]:
    files = sorted(Path(directory).glob("frame_*.png"))
    if not files:
        raise FileNotFoundError(f"no frame_*.png in {directory}")
    return [flatten(downscale(np.array(Image.open(f).convert("RGBA")), px), matte) for f in files]


def common_crop(frames: list[np.ndarray]) -> list[np.ndarray]:
    """Crop every frame to the union bounding box; pad the top row so the height is even."""
    stack = np.stack(frames)
    ys, xs = np.nonzero((stack != TRANSPARENT).any(axis=0))
    if len(ys) == 0:
        raise ValueError("animation is fully transparent")
    y0, y1, x0, x1 = ys.min(), ys.max() + 1, xs.min(), xs.max() + 1
    cropped = [f[y0:y1, x0:x1] for f in frames]
    if (y1 - y0) % 2:  # bottom aligned: the extra row goes on top
        cropped = [np.vstack([np.full((1, x1 - x0), TRANSPARENT, dtype=f.dtype), f]) for f in cropped]
    return cropped


def build_palette(frames: list[np.ndarray]) -> list[int]:
    counts = Counter()
    for f in frames:
        vals, n = np.unique(f[f != TRANSPARENT], return_counts=True)
        counts.update(dict(zip(vals.tolist(), n.tolist())))
    palette = [c for c, _ in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))]
    if len(palette) > len(ALPHABET):
        raise ValueError(f"{len(palette)} colours do not fit the {len(ALPHABET)}-letter alphabet")
    return palette


def encode_row(row: list[int], letters: dict[int, str]) -> str:
    end = len(row)
    while end and row[end - 1] == TRANSPARENT:
        end -= 1
    out, i = [], 0
    while i < end:
        j = i
        while j < end and row[j] == row[i]:
            j += 1
        out.append((letters[row[i]] if row[i] != TRANSPARENT else ".") + (str(j - i) if j - i > 1 else ""))
        i = j
    return "".join(out)


def encode_frame(frame: np.ndarray, letters: dict[int, str]) -> str:
    return "/".join(encode_row(r, letters) for r in frame.tolist())


def build_animation(frames: list[np.ndarray], fps: int) -> dict:
    """-> {fps, width, height, palette: ['#rrggbb'], frames: [[rle, hold], ...]}"""
    cropped = common_crop(frames)
    palette = build_palette(cropped)
    letters = {c: ALPHABET[i] for i, c in enumerate(palette)}
    merged: list[list] = []
    prev = None
    for f in cropped:
        if prev is not None and np.array_equal(f, prev):
            merged[-1][1] += 1
        else:
            merged.append([encode_frame(f, letters), 1])
        prev = f
    h, w = cropped[0].shape
    return {
        "fps": fps, "width": int(w), "height": int(h),
        "palette": [f"#{c:06X}" for c in palette], "frames": merged,
        "source_frames": len(frames),
    }


def decode_frame(rle: str, width: int, height: int, palette: list[str]) -> list[list]:
    """Reference decoder (mirrors hooks/anims-v2/decode.ts): rows of '#RRGGBB' | None."""
    rows = rle.split("/")
    if len(rows) != height:
        raise ValueError(f"{len(rows)} rows, expected {height}")
    out = []
    for r in rows:
        cells, i = [], 0
        while i < len(r):
            c = r[i]
            i += 1
            j = i
            while j < len(r) and r[j].isdigit():
                j += 1
            n = int(r[i:j]) if j > i else 1
            i = j
            cells.extend([None if c == "." else palette[ALPHABET.index(c)]] * n)
        out.append(cells + [None] * (width - len(cells)))
    return out


def anim_ts(name: str, anim: dict) -> str:
    frames = ",\n".join(f"    [{_q(rle)}, {hold}]" for rle, hold in anim["frames"])
    pal = ", ".join(_q(c) for c in anim["palette"])
    return (
        "// Generated by tools/svg2mod_frames.py from the v2 SVG frames. Do not edit.\n"
        "import type { V2Anim } from './types'\n\n"
        f"// {name}: {anim['source_frames']} source frames -> {len(anim['frames'])} stored, "
        f"{anim['width']}x{anim['height']} art px\n"
        "export const anim: V2Anim = {\n"
        f"  fps: {anim['fps']},\n  width: {anim['width']},\n  height: {anim['height']},\n"
        f"  palette: [{pal}],\n"
        f"  frames: [\n{frames},\n  ],\n}}\n"
    )


def _q(s: str) -> str:
    return "'" + s.replace("\\", "\\\\").replace("'", "\\'") + "'"


def index_ts(names: list[str], aliases: dict[str, str], max_width: int, max_height: int) -> str:
    imports = "\n".join(f"import {{ anim as v2_{n} }} from './{n}'" for n in names)
    entries = [f"  {n}: v2_{n}," for n in names] + [f"  {a}: v2_{t}," for a, t in aliases.items() if t in names]
    return (
        "// Generated by tools/svg2mod_frames.py. Do not edit.\n"
        "import type { AnimName } from '../../types'\n"
        f"{imports}\nimport type {{ V2Anim }} from './types'\n\n"
        "// AnimName -> v2 art; names missing here fall back to the v1 pose functions.\n"
        "export const ANIMS_V2: Partial<Record<AnimName, V2Anim>> = {\n" + "\n".join(entries) + "\n}\n\n"
        f"// Widest and tallest v2 animation, in art pixels (columns / pixel rows).\n"
        f"export const V2_MAX_WIDTH = {max_width}\nexport const V2_MAX_HEIGHT = {max_height}\n"
    )


def generate_all(previews: Path, out: Path, matte=MATTE) -> dict[str, int]:
    out.mkdir(parents=True, exist_ok=True)
    names, sizes, mw, mh = [], {}, 0, 0
    for name in FPS:
        anim = build_animation(load_frames(previews / name, matte=matte), FPS[name])
        text = anim_ts(name, anim)
        (out / f"{name}.ts").write_text(text, encoding="utf-8")
        sizes[name] = len(text.encode())
        names.append(name)
        mw, mh = max(mw, anim["width"]), max(mh, anim["height"])
    idx = index_ts(names, ALIASES, mw, mh)
    (out / "index.ts").write_text(idx, encoding="utf-8")
    sizes["index"] = len(idx.encode())
    return sizes


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("frames", nargs="?", help="directory of frame_*.png (single animation)")
    ap.add_argument("--all", metavar="PREVIEWS", help="directory holding one frame dir per animation")
    ap.add_argument("--anim", help="animation name (single mode)")
    ap.add_argument("--fps", type=int, help="frames per second (single mode)")
    ap.add_argument("--out", required=True, help="output directory for the .ts files")
    ap.add_argument("--matte", default="#262626", help="colour semi-transparent pixels blend over")
    a = ap.parse_args(argv)
    matte = tuple(int(a.matte.lstrip("#")[i:i + 2], 16) for i in (0, 2, 4))
    out = Path(a.out)
    if a.all:
        sizes = generate_all(Path(a.all), out, matte)
        for k, v in sizes.items():
            print(f"{k:14s}{v:8d} B")
        print(f"{'total':14s}{sum(sizes.values()):8d} B")
        return 0
    if not (a.frames and a.anim and a.fps):
        ap.error("single mode needs FRAMES, --anim and --fps (or use --all)")
    anim = build_animation(load_frames(Path(a.frames), matte=matte), a.fps)
    out.mkdir(parents=True, exist_ok=True)
    (out / f"{a.anim}.ts").write_text(anim_ts(a.anim, anim), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
