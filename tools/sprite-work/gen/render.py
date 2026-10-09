"""Build one v2 animation, render it with the repo pipeline into previews, and report numbers."""
import subprocess, shutil, sys, json
from pathlib import Path
HERE = Path(__file__).parent
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE.parent))
from common import *
from hdr import *

# anim -> v2 svg stem, old anim key (for params), fps, duration, header prefix
V2 = {
    "idle":         ("clawd-idle-living-v2",        6,  "auto", "idle"),
    "thinking":     ("clawd-working-thinking-v2",   8,  "auto", "thinking"),
    "typing":       ("clawd-working-typing-v2",     8,  "auto", "typing"),
    "debugger":     ("clawd-working-debugger-v2",   8,  "12",   "debugger"),
    "building":     ("clawd-working-building-v2",   8,  "auto", "building"),
    "conducting":   ("clawd-working-conducting-v2", 8,  "auto", "conducting"),
    "happy":        ("clawd-happy-v2",              10, "auto", "happy"),
    "sleeping":     ("clawd-sleeping-v2",           6,  "auto", "sleeping"),
    "waiting_reply":("clawd-waiting-reply-v2",      8,  "auto", "waiting_reply"),
    "wake":         ("clawd-wake-v2",               8,  "auto", "wake"),
    "low_battery":  ("clawd-idle-low-battery-v2",   6,  "auto", "low_battery"),
    "hat_mishap":   ("clawd-hat-mishap-v2",         6,  "auto", "hat_mishap"),
    "confused":     ("clawd-working-confused-v2",   8,  "auto", "confused"),
    "dizzy":        ("clawd-dizzy-v2",              8,  "auto", "dizzy"),
    "sweeping":     ("clawd-working-sweeping-v2",   8,  "auto", "sweeping"),
    "alert":        ("clawd-notification-v2",       10, "auto", "alert"),
}


def run(cmd):
    r = subprocess.run([str(c) for c in cmd], capture_output=True, text=True)
    if r.returncode:
        print(r.stdout[-2000:], r.stderr[-3000:]); raise SystemExit(f"failed: {cmd[:3]}")
    return r.stdout


def render(anim, quiet=False):
    stem, fps, dur, prefix = V2[anim]
    svg = SVG_DIR / f"{stem}.svg"
    fdir = PREV / anim
    if fdir.exists(): shutil.rmtree(fdir)
    run([PY, REPO / "tools" / "svg2frames.py", svg, fdir, "--fps", fps, "--duration", dur, "--scale", SCALE, "--snap", "exact"])
    hdir = PREV / "headers"; hdir.mkdir(parents=True, exist_ok=True)
    hdr = hdir / f"sprite_{anim}.h"
    run([PY, REPO / "tools" / "png2rgb565.py", fdir, hdr, "--name", prefix])
    res = cs.process_sprite(hdr)   # crops the candidate header in place (previews/headers only)
    h = cs.parse_header(hdr)
    _, frames = load_frames(hdr)
    sheet(frames, PREV / "sheets" / f"{anim}.png", zoom=2 if h["width"] <= 100 else 1)
    info = dict(anim=anim, frames=h["frame_count"], w=h["width"], h=h["height"], rle=rle_bytes(h),
                bottom_removed=res.get("bottom_removed"), y_off=res.get("y_offset_delta"))
    if not quiet: print(json.dumps(info))
    return info


if __name__ == "__main__":
    for a in sys.argv[1:] or V2:
        render(a)
