# Archive Report: v2-sprites-on-device

- **Change**: v2-sprites-on-device
- **Archived**: 2026-10-09
- **Archived to**: `openspec/changes/archive/2026-10-09-v2-sprites-on-device/`
- **Artifact store**: openspec (with Engram traceability mirror)
- **Verify verdict**: PASS WITH WARNINGS (no CRITICAL)
- **Archive type**: intentional-with-warnings — user explicitly accepted the documented warnings/gaps and chose to archive
- **Branch**: personal (local completion — not pushed, no PR opened)

## Executive Summary

Ported the redesigned v2 crab art onto the ESP32-C6 firmware and the shared SDL2 simulator for the 15 animations that have a v2 counterpart, at a frozen render scale of x3. All automatable verification is green (header contract, exact-pixel RLE decode, 73 KB per-frame heap ceiling, per-anim frame timing, and a byte-identical no-regression guard over the 7 untouched v1 headers). The 7 animations with no v2 art keep rendering v1 — a mixed v1/v2 device state is the accepted end state.

## What Shipped

- **15 anims regenerated from v2 SVGs** (idle, notification/alert, happy, sleeping, thinking, typing, building, confused, dizzy, sweeping, debugger, conducting, wake, low_battery, hat_mishap). Each `firmware/main/assets/sprite_*.h` regenerated in place at `--scale 3 --snap exact`.
- **Asset pipeline driver**: `tools/regen_v2_sprite.py` — thin per-anim driver running `svg2frames.py → png2rgb565.py → crop_sprites.py → analyze_sprite_bounds.py` under system Python 3.11; prints the `crop_sprites.py` `y_offset` delta as a human-review artifact and never edits `scene.c`.
- **Windows portability fix**: `tools/svg2frames.py` `.resolve()` before `.as_uri()`, prerequisite for running the pipeline on Windows.
- **Firmware wiring**: `firmware/main/scene.c` per-anim `y_offset`, `*_FRAME_MS` matched to v2 fps (6 fps → 167, 8 fps → 125, 10 fps → 100; 6 fps via `(1000+3)/6` to avoid 166 truncation), and `.looping` preserved (ALERT/HAPPY/SWEEPING/WAKE oneshot; the other 11 looping). No new enum; `waiting_reply` excluded (no device slot).
- **Scene/grass tuning**: uniform `y_offset=-21` with `GRASS_HEIGHT` raised 14→24 in `scene.c` so all 15 v2 crabs sit feet-on-line on the 320×172 panel (see WARNING-1 for the v1 scope impact).
- **Tests** (`tools/tests/test_v2_sprite_contract.py`, system Python 3.11):
  - `test_header_contract` — 15 prefixes: fmt=rle, W/H/FRAME_COUNT>0, FRAME_COUNT==len(offsets)-1, every frame RLE run-sum == W*H, no overrun. GREEN.
  - `test_heap_ceiling` — peak = happy 90×75 = 20,250 B << 74,752 B (73 KB) ceiling. GREEN.
  - `test_frame_ms_matches_fps` — 15 anims via simulator `--capture-anim`, each ms == round(1000/fps). GREEN (~9.8–10.0s).
  - `test_v1_headers_unchanged` — 7 v1 headers byte-identical to HEAD. GREEN.
- **Render scale frozen at x3** after the WAKE simulator review (x4 rejected for the 73 KB heap ceiling).

## Commit List (branch personal)

`501457b`, `5028c08`, `60f5efd`, `b4f4023`, `7d80e27`, `e61dba2`

## Accepted Warnings / Gaps (user accepted; not blockers)

### WARNING-1 — GRASS_HEIGHT scope expansion (scene, not just crab art)
`scene.c` raises `GRASS_HEIGHT` 14→24 and sets a uniform `y_offset=-21`. This expands scope from "crab art" to the shared scene and therefore affects the 7 v1 anims' on-screen vertical placement (their sprite bytes are byte-identical and unchanged; only placement under the taller grass band shifts). The spec/proposal had no requirement covering grass height or v1 placement under a taller band. Re-check status of the 7 v1 anims in the simulator:
- Confirmed well-aligned: disconnected, going_away, wizard, beacon.
- Grass-independent: mini_crab (a HUD icon).
- Not captured in isolation: walking + juggling (transient internal anims) — but they share the same BOTTOM+`y_offset` mechanism and their untouched v1 offsets, so low risk.

### WARNING-2 — Firmware target build NOT run
`idf.py build` was not run (idf.py not on PATH in this environment). The ESP32-C6 target compile of `scene.c` + the 15 regenerated headers is UNVERIFIED. Must be built in an ESP-IDF 5.3.2 environment before flashing. The SDL2 simulator builds clean.

### Not pushed / no PR opened
The user is working locally on branch `personal`. This archive reflects local completion, not a merged PR. Tasks 2.20 (idf.py build) and 2.21 (PR open/retarget) remain unchecked in `tasks.md` and are honestly recorded as intentionally incomplete.

## Recorded Follow-up (next change — not done here)

Design the 7 missing v2 SVGs (beacon, wizard, juggling, walking, going_away, disconnected, mini_crab) so all device anims can be v2. The existing 15 v2 SVGs were authored with Claude Opus 5.5 (not the Gemini pipeline). Once the 7 SVGs exist, porting them to the device is trivial via the proven `tools/regen_v2_sprite.py` + the parametrized contract test.

## Specs Synced

| Domain | Action | Details |
|--------|--------|---------|
| device-v2-sprites | Created | New capability; main spec did not exist (`openspec/specs/` held only `.gitkeep`). Delta copied directly to `openspec/specs/device-v2-sprites/spec.md`. 9 requirements. |

Source of truth now reflects device v2 sprites behavior at `openspec/specs/device-v2-sprites/spec.md`.

## Archive Contents

- `proposal.md`
- `specs/device-v2-sprites/spec.md`
- `design.md`
- `exploration.md`
- `tasks.md` (17/19 implementation items checked; 2.20 idf.py build + 2.21 PR open intentionally left unchecked and documented above)
- `verify-report.md`
- `archive-report.md` (this file)

## Engram Traceability (observation IDs)

| Artifact | Topic Key | Observation ID |
|----------|-----------|----------------|
| Exploration | `sdd/v2-sprites-on-device/explore` | 3496 |
| Proposal | `sdd/v2-sprites-on-device/proposal` | 3497 |
| Spec | `sdd/v2-sprites-on-device/spec` | 3498 |
| Design | `sdd/v2-sprites-on-device/design` | 3499 |
| Tasks | `sdd/v2-sprites-on-device/tasks` | 3500 |
| Apply progress | (PR2 v2 sprites: 14 anims ported + grass/offset tuning done) | 3501 |
| Scale decision | (v2 sprites device render scale frozen at x3) | 3503 |
| Verify report | `sdd/v2-sprites-on-device/verify-report` | 3505 |

## Other Updates

- `CHANGELOG.md` — added an `[Unreleased] > Changed` entry for the 15-anim v2 port (per `rules.archive`), honestly noting the firmware target build is still pending.
- `TODO.md` — added a "v2 crab art on the device (15 anims) — Implemented (firmware target build + full v1 re-check pending)" section plus the recorded follow-up, following the repo's existing per-feature status convention.

## DAG State

**archived** — the SDD cycle for `v2-sprites-on-device` is complete (planned → implemented → verified → archived).
