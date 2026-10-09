#!/usr/bin/env python3
"""
Thin per-anim driver that regenerates a single v2 sprite header end to end.

For a given prefix + v2 SVG + fps it runs the 4-stage asset pipeline, in order,
all under the SAME interpreter this script is launched with (intended to be
system Python 3.11, which carries Pillow + numpy + playwright + chromium):

  1. svg2frames.py <svg> <tmp>      --fps <fps> --scale <scale> --snap exact
  2. png2rgb565.py  <tmp> <header>  --name <prefix>
  3. crop_sprites.py                 (crops ALL sprite_*.h in place, prints deltas)
  4. analyze_sprite_bounds.py        (verifies bounds for ALL sprite_*.h)

The driver PRINTS the crop_sprites.py y_offset delta for THIS prefix to stdout
as a human-review artifact. It deliberately DOES NOT touch firmware/main/scene.c:
applying the y_offset delta is a manual, visually-confirmed step (see design.md,
"y_offset review decision"). The driver's only side effects on the tree are the
regenerated sprite_<prefix>.h (plus the in-place crop of the other headers, which
is crop_sprites.py's existing documented behaviour).

Note on CLIs: crop_sprites.py and analyze_sprite_bounds.py do not accept a path
argument -- they operate on every sprite_*.h under firmware/main/assets/. The
driver runs them unscoped and extracts the line for <prefix> from their output.

Usage:
    py -3.11 tools/regen_v2_sprite.py <prefix> <svg_filename> <fps> [--scale N]

Example:
    py -3.11 tools/regen_v2_sprite.py wake clawd-wake-v2.svg 8 --scale 3
"""

import argparse
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
TOOLS_DIR = REPO_ROOT / "tools"
SVG_DIR = REPO_ROOT / "assets" / "svg-animations"
ASSETS_DIR = REPO_ROOT / "firmware" / "main" / "assets"


def _run(cmd, label):
    """Run a pipeline stage with the current interpreter, UTF-8 forced.

    Returns captured stdout. Raises on non-zero exit so the driver fails loud.
    """
    env = dict(os.environ)
    # svg2frames prints a unicode arrow; force UTF-8 so Windows consoles don't choke.
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    print(f"\n==> [{label}] {' '.join(str(c) for c in cmd)}", flush=True)
    proc = subprocess.run(
        cmd,
        cwd=str(REPO_ROOT),
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    if proc.stdout:
        print(proc.stdout, end="", flush=True)
    if proc.returncode != 0:
        if proc.stderr:
            print(proc.stderr, end="", file=sys.stderr, flush=True)
        raise SystemExit(f"[{label}] failed with exit code {proc.returncode}")
    return proc.stdout or ""


def _extract_y_offset_delta(crop_stdout, prefix):
    """Pull the y_offset delta for <prefix> out of crop_sprites.py stdout.

    crop_sprites prints a per-file processing line such as:
        Processing sprite_wake.h... 182x120 -> 150x96 (28% buf savings, y_offset +=16)
    The delta is the integer after 'y_offset +='. Returns int or None if the
    sprite was skipped / not reported (e.g. no crop savings).
    """
    pat = re.compile(
        rf"Processing\s+sprite_{re.escape(prefix)}\.h\.\.\..*?y_offset\s*\+=\s*(-?\d+)"
    )
    m = pat.search(crop_stdout)
    if m:
        return int(m.group(1))
    return None


def main():
    parser = argparse.ArgumentParser(
        description="Regenerate one v2 sprite header end to end (prints y_offset delta)."
    )
    parser.add_argument("prefix", help="C-identifier array prefix, e.g. 'wake'")
    parser.add_argument("svg", help="v2 SVG filename under assets/svg-animations/")
    parser.add_argument("fps", type=float, help="frames per second, e.g. 8")
    parser.add_argument("--scale", type=float, default=3,
                        help="render scale (working default 3)")
    args = parser.parse_args()

    svg_path = SVG_DIR / args.svg
    if not svg_path.is_file():
        raise SystemExit(f"SVG not found: {svg_path}")

    header_path = ASSETS_DIR / f"sprite_{args.prefix}.h"
    svg2frames = TOOLS_DIR / "svg2frames.py"
    png2rgb565 = TOOLS_DIR / "png2rgb565.py"
    crop_sprites = TOOLS_DIR / "crop_sprites.py"
    analyze = TOOLS_DIR / "analyze_sprite_bounds.py"

    py = sys.executable  # same interpreter the driver runs under (system py3.11)

    with tempfile.TemporaryDirectory(prefix=f"regen_{args.prefix}_") as tmp:
        tmp_dir = Path(tmp)

        # 1. SVG -> PNG frames
        _run(
            [py, str(svg2frames), str(svg_path), str(tmp_dir),
             "--fps", str(args.fps), "--scale", str(args.scale), "--snap", "exact"],
            "svg2frames",
        )

        # 2. PNG frames -> RLE C header (in place)
        _run(
            [py, str(png2rgb565), str(tmp_dir), str(header_path), "--name", args.prefix],
            "png2rgb565",
        )

        # 3. Crop all headers in place; capture this prefix's y_offset delta
        crop_out = _run([py, str(crop_sprites)], "crop_sprites")

        # 4. Verify bounds (unscoped; informational)
        _run([py, str(analyze)], "analyze_sprite_bounds")

    y_delta = _extract_y_offset_delta(crop_out, args.prefix)

    print("\n" + "=" * 60)
    print(f"REGEN COMPLETE: {args.prefix}")
    print(f"  header: {header_path}")
    if y_delta is not None:
        print(f"  y_offset delta (crop_sprites): +{y_delta}")
        print(f"  --> HUMAN REVIEW: apply this delta to anim_defs[{args.prefix.upper()}].y_offset "
              f"in firmware/main/scene.c, then confirm visually in the simulator.")
    else:
        print("  y_offset delta: (not reported -- sprite skipped or no crop savings)")
    print(f"  NOTE: this driver did NOT edit scene.c.")
    print("=" * 60)

    # Machine-readable last line for test harnesses / human review scripts.
    print(f"y_offset_delta={y_delta if y_delta is not None else ''}")


if __name__ == "__main__":
    main()
