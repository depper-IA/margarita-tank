import sys
from pathlib import Path
HERE = Path(__file__).parent
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE.parent))
from common import SVG_DIR
import anims_a, anim_idle
import anims_b, anims_c

BUILDERS = {
    "clawd-idle-living-v2": anim_idle.build,
    "clawd-working-thinking-v2": anims_a.build_thinking,
    "clawd-working-typing-v2": anims_a.build_typing,
    "clawd-working-conducting-v2": anims_a.build_conducting,
    "clawd-working-building-v2": anims_a.build_building,
}
BUILDERS.update(anims_b.BUILDERS)
BUILDERS.update(anims_c.BUILDERS)

if __name__ == "__main__":
    only = sys.argv[1:]
    for name, fn in BUILDERS.items():
        if only and not any(o in name for o in only): continue
        (SVG_DIR / f"{name}.svg").write_text(fn())
        print("wrote", name)
