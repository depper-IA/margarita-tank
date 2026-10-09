"""Shared config for the sprite redesign work (lives outside the repo)."""
from pathlib import Path

ROOT = Path.home() / "Projects" / "margarita-tank-worktrees"
REPO = ROOT / "sprite-redesign"
PY = ROOT / "sprite-venv" / "bin" / "python"
SVG_DIR = REPO / "assets" / "svg-animations"
ASSETS = REPO / "firmware" / "main" / "assets"
PREV = ROOT / "previews"
WORK = ROOT / "sprite-work"

# anim -> (old svg stem, fps, duration arg, header prefix, v2 svg stem)
ANIMS = {
    "idle":       ("clawd-idle-living",        6,  "auto", "idle"),
    "thinking":   ("clawd-working-thinking",   8,  "auto", "thinking"),
    "typing":     ("clawd-working-typing",     8,  "auto", "typing"),
    "debugger":   ("clawd-working-debugger",   8,  "12",   "debugger"),
    "building":   ("clawd-working-building",   8,  "auto", "building"),
    "conducting": ("clawd-working-conducting", 8,  "auto", "conducting"),
    "happy":      ("clawd-happy",              10, "auto", "happy"),
    "sleeping":   ("clawd-sleeping",           6,  "auto", "sleeping"),
    "wake":       ("clawd-wake",               8,  "auto", "wake"),
    "low_battery":("clawd-idle-low-battery",   6,  "auto", "low_battery"),
    "hat_mishap": ("clawd-hat-mishap",         6,  "auto", "hat_mishap"),
    "confused":   ("clawd-working-confused",   8,  "auto", "confused"),
    "dizzy":      ("clawd-dizzy",              8,  "auto", "dizzy"),
    "sweeping":   ("clawd-working-sweeping",   8,  "auto", "sweeping"),
    "alert":      ("clawd-notification",       10, "auto", "alert"),
}
SCALE = 4
