# sprite-work

Local sprite-sheet generation and comparison helpers for the Clawd v2 rig.

These scripts are developer tooling, not part of the game build. They are used
to generate sprite sheets, render animation frames, and compare the reproduced
output against the original art while iterating on the v2 rig.

## Layout

- Top-level scripts: comparison and preview helpers
  (`compare.py`, `compare_a.py`, `cmp_happy.py`, `cmp_idle.py`, `hdr.py`,
  `pick.py`, `prevgrid.py`, `repro_old.py`, `resheet.py`, `shot_mock.py`,
  `sizes.py`, `view_old_vs_repro.py`, `common.py`).
- `gen/`: the rig and animation generation pipeline
  (`build_all.py`, `build_base.py`, `render.py`, `rig.py`, `pose.py`,
  `props.py`, `art.py`, `svgbuild.py`, `anim_idle.py`, `anims_a.py`,
  `anims_b.py`, `anims_c.py`).

## Setup

```sh
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium
```

## Known issues

Three scripts contain absolute or temporary paths that must be fixed before
running on another machine:

- `prevgrid.py` has a hardcoded
  `sys.path.insert(0, '/Users/samwilkie/.../sprite-work/gen')`.
- `shot_mock.py` points at a `/private/tmp/claude-501/...` scratch path that no
  longer exists.
- `gen/build_base.py` defaults its output to `/tmp/clawd-static-base-v2.svg`.

These paths are environment-specific and will not resolve on a fresh checkout.
Update them to paths valid on your machine before running the affected scripts.
