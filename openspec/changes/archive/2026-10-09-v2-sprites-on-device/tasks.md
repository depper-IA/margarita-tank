# Tasks: Port v2 crab animations onto ESP32-C6 firmware (render scale x3)

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | PR1 ~250-350 (fix + driver + test harness + 1 sprite header + scene.c pilot); PR2 ~1200-2500 (14 regenerated sprite headers are large generated RLE blobs + scene.c edits) |
| 400-line budget risk | High |
| Chained PRs recommended | Yes |
| Suggested split | PR 1 (pilot: fix + harness + WAKE) → PR 2 (remaining 14) |
| Delivery strategy | ask-on-risk → resolved to chained PRs |
| Chain strategy | stacked-to-main (PR1 merges to main, then PR2 stacks on PR1 then to main) |

Decision needed before apply: No
Chained PRs recommended: Yes
Chain strategy: stacked-to-main
400-line budget risk: High

### Suggested Work Units

| Unit | Goal | Likely PR | Notes |
|------|------|-----------|-------|
| 1 | svg2frames Windows fix (fix only, own commit) | PR 1 | base = main; isolated commit per work-unit-commits |
| 2 | regen driver + parametrized test harness (RED) | PR 1 | base = main; tests fail first (strict_tdd) |
| 3 | WAKE pilot: regen → crop → y_offset → green → sim visual → freeze scale | PR 1 | base = main; proves full path, mergeable alone |
| 4 | Extend prefix list 1→15 + port 14 anims + full verify | PR 2 | base = PR1 branch, then retarget to main after PR1 merges |

Generated RLE sprite headers are counted toward complete-snapshot identity but the authored-line budget drives the split; the 14 regenerated headers in PR2 are generated artifacts (per work-unit-commits), which is why PR2 is accepted as a large generated diff on a stacked PR rather than split further.

### PR Commit Structure (chained-pr + work-unit-commits)

- Conventional commits, no AI attribution / no Co-Authored-By.
- One deliverable work unit per commit; tests live in the same commit as the behavior they verify.
- stacked-to-main: PR1 → main first; PR2 branch created off PR1, retargeted/rebased onto main after PR1 merges so the PR2 diff shows only the 14-anim work.
- Each PR body states start, end, dependencies, follow-up, out-of-scope, and a dependency diagram marking the current PR with 📍.
- PR1 dependency diagram: `main → 📍 PR1 (fix+harness+WAKE)`; PR2: `main → PR1 → 📍 PR2 (14 anims)`.

---

# PR 1 — Pilot (proves the whole path, mergeable alone to main)

## Phase 1.A: Pipeline Prerequisite (Spec: Pipeline Reproducibility on Windows)

- [x] 1.1 Commit the `tools/svg2frames.py` `.resolve()`-before-`.as_uri()` Windows fix (~line 290), fix only, as its own conventional commit `fix(tools): resolve svg path before as_uri for Windows`. No other changes in this commit. (Design: Asset Pipeline prerequisite)

## Phase 1.B: Regen Driver (Design: Key Decisions — thin per-anim driver)

- [x] 1.2 Create `tools/regen_v2_sprite.py` that, for a given prefix+svg+fps, runs the 4 pipeline commands in order under system py3.11: `svg2frames.py <svg> <tmp> --fps <fps> --scale 3 --snap exact` → `png2rgb565.py <tmp> firmware/main/assets/sprite_<prefix>.h --name <prefix>` → `crop_sprites.py` → `analyze_sprite_bounds.py`. (Note: crop_sprites.py / analyze_sprite_bounds.py take NO path arg — they process all sprite_*.h; the driver runs them unscoped and extracts the prefix's line.)
- [x] 1.3 In `tools/regen_v2_sprite.py`, capture and PRINT the `crop_sprites.py` `y_offset` delta to stdout as a human-review artifact; the driver MUST NOT edit `scene.c` or apply the delta. (Design: y_offset review decision)

## Phase 1.C: Test Harness — RED (strict_tdd: write FAILING tests first)

- [x] 1.4 [TDD-RED] Create `tools/tests/test_v2_sprite_contract.py` with a parametrized header-contract test (system py3.11, joins existing `tools/tests/`) over a prefix list seeded with ONLY `wake`. Per prefix assert via `analyze_sprite_bounds.parse_header()`: `fmt=='rle'`, `WIDTH>0`, `HEIGHT>0`, `FRAME_COUNT>0`, `FRAME_COUNT == len(frame_offsets)-1`, and every frame RLE-decodes (via `decode_frame`) to exactly `WIDTH*HEIGHT` pixels with no overrun (run-sum == W*H). Confirm it FAILS before WAKE is regenerated. (Spec: Sprite Dimensions and Decode Contract)
- [x] 1.5 [TDD-RED] Add the heap-ceiling assertion to the same parametrized test: `WIDTH*HEIGHT*3 <= 73*1024` per prefix. Confirm it is wired and failing/erroring pre-regen. (Spec: Peak Per-Frame Heap Bound)
- [x] 1.6 [TDD-RED] Add the byte-identical no-regression test over the 7 untouched v1 headers (`disconnected, juggling, walking, going_away, wizard, beacon, mini_crab`): SHA-compare each against its committed git blob. Confirm it PASSES now (headers untouched) and will guard against accidental edits. (Spec: No Regression for Non-v2 Anims)
- [x] 1.7 [TDD-RED] Create the `frame_ms` test driving the simulator `--capture` path: assert `scene_get_anim_info(X,&fc,&ms)` returns `ms == round(1000/fps)` for WAKE (8fps → 125) and `anim_defs[WAKE].frame_ms == WAKE_FRAME_MS`. Confirm it fails/errors before the WAKE build. (Spec: Per-Anim Frame Timing)

## Phase 1.D: WAKE Pilot — GREEN (Spec: v2 Sprite Art Replacement, Looping/Oneshot, Vertical Placement)

- [x] 1.8 Run `tools/regen_v2_sprite.py` for WAKE: `clawd-wake-v2.svg`, prefix `wake`, 8fps, `--scale 3 --snap exact`. Regenerates `firmware/main/assets/sprite_wake.h` in place; capture the printed y_offset delta. (Design: anim→SVG→prefix→fps table)
- [x] 1.9 Verify `sprite_wake.h` macros (`WAKE_WIDTH/_HEIGHT/_FRAME_COUNT`) via `analyze_sprite_bounds.py`; the crop step already ran in the driver. Make tasks 1.4/1.5 pass for `wake` (contract + heap GREEN).
- [x] 1.10 In `firmware/main/scene.c`, update `anim_defs[WAKE].y_offset` from the printed crop delta (current −8); confirm `.looping=false` is preserved (WAKE is a oneshot) and `WAKE_FRAME_MS` still equals 125. No enum/`scene.h` edit. (Design: Firmware Wiring; Spec: Looping and Oneshot)
- [x] 1.11 Build the SDL2 simulator with the regenerated WAKE and make the `frame_ms` test (1.7) pass for WAKE. (Design: Test Contract — frame_ms via simulator capture)

## Phase 1.E: Human-Review Gate + Scale Freeze (NOT auto-testable — main risk)

- [x] 1.12 [HUMAN-REVIEW GATE] Capture a simulator screenshot of WAKE at x3 and visually confirm the crab is ground-aligned on 320×172 AND that the oneshot holds its last frame (does not restart). Record approval before proceeding. This gate is the primary risk control for manual y_offset and cannot be automated. (Spec: Vertical Placement; Design: Risks → y_offset / oneshot) — DONE: crop-delta y_offset +4 floated; corrected to -3 (commit 60f5efd), confirmed on grass in simulator at both ends of the animation.
- [x] 1.13 [DECISION] Freeze the render-scale decision (x3 vs x2) based on the WAKE simulator review; record the accepted scale as "confirmed in simulator" to be applied uniformly to all 15 anims. (Spec: Render Scale Validation; Design: Open Question — scale freeze) — DONE: x3 frozen (user confirmed after a 3-crab fit check; x4 rejected for the 73KB heap ceiling). Engram sdd/v2-sprites-on-device/scale-decision.
- [x] 1.14 Confirm PR1 is independently green and mergeable: contract+heap+frame_ms pass for WAKE, 7-header no-regression passes, simulator builds. Open PR1 (base main) per the commit structure above. — Local verify green; PR not opened (user working locally, no push yet).

---

# PR 2 — Remaining 14 anims (depends on PR1 driver+tests; stacked on PR1 then to main)

## Phase 2.A: Extend Parametrized Harness

- [x] 2.1 [TDD] Extend the parametrized prefix list in `tools/tests/test_v2_sprite_contract.py` from `[wake]` to all 15 ported prefixes (add: `idle, alert, happy, sleeping, thinking, typing, building, confused, dizzy, sweeping, debugger, conducting, low_battery, hat_mishap`). This is a data-list edit only — no new test code. Confirm the 14 new cases FAIL (RED) before regeneration. (Design: Test Contract — parametrized)

## Phase 2.B: Regenerate & Port the 14 (one task per anim; each: regen → crop → y_offset → preserve .looping → verify macros → green → sim visual)

Each task applies the frozen scale, runs `tools/regen_v2_sprite.py`, updates `anim_defs[X].y_offset` from the printed crop delta in `scene.c`, preserves the design `.looping` value, confirms `*_FRAME_MS == round(1000/fps)`, and makes the contract+heap+frame_ms cases green. (Spec: v2 Sprite Art Replacement, Dimensions/Decode, Per-Anim Frame Timing, Looping/Oneshot, Vertical Placement)

- [x] 2.2 IDLE ← `clawd-idle-living-v2.svg`, prefix `idle`, 6fps (FRAME_MS 167), `.looping=true`, y_offset from −8. → 62x41, 96 frames, crop +12, starting y_offset 4.
- [x] 2.3 ALERT ← `clawd-notification-v2.svg`, prefix `alert`, 10fps (FRAME_MS 100), `.looping=false` (ONESHOT — preserve), y_offset from −4. → 64x69, crop +12, starting y_offset 8, looping=false preserved.
- [x] 2.4 HAPPY ← `clawd-happy-v2.svg`, prefix `happy`, 10fps (FRAME_MS 100), `.looping=false` (ONESHOT — preserve), y_offset from −7. → 90x75, crop +27, starting y_offset 20, looping=false preserved.
- [x] 2.5 SLEEPING ← `clawd-sleeping-v2.svg`, prefix `sleeping`, 6fps (FRAME_MS 167), `.looping=true`, y_offset from −8. → 70x75, crop +12, starting y_offset 4.
- [x] 2.6 THINKING ← `clawd-working-thinking-v2.svg`, prefix `thinking`, 8fps (FRAME_MS 125), `.looping=true`, y_offset from −8. → 64x69, crop +12, starting y_offset 4.
- [x] 2.7 TYPING ← `clawd-working-typing-v2.svg`, prefix `typing`, 8fps (FRAME_MS 125), `.looping=true`, y_offset from −8. → 68x57, crop +12, starting y_offset 4.
- [x] 2.8 BUILDING ← `clawd-working-building-v2.svg`, prefix `building`, 8fps (FRAME_MS 125), `.looping=true`, y_offset from −4. → 110x50, crop +12, starting y_offset 8.
- [x] 2.9 CONFUSED ← `clawd-working-confused-v2.svg`, prefix `confused`, 8fps (FRAME_MS 125), `.looping=true`, y_offset from −4. → 70x57, crop +12, starting y_offset 8.
- [x] 2.10 DIZZY ← `clawd-dizzy-v2.svg`, prefix `dizzy`, 8fps (FRAME_MS 125), `.looping=true`, y_offset from −8. → 72x53, crop +12, starting y_offset 4.
- [x] 2.11 SWEEPING ← `clawd-working-sweeping-v2.svg`, prefix `sweeping`, 8fps (FRAME_MS 125), `.looping=false` (ONESHOT — preserve), y_offset from 0. → 110x38, crop +10, starting y_offset 10, looping=false preserved.
- [x] 2.12 DEBUGGER ← `clawd-working-debugger-v2.svg`, prefix `debugger`, 8fps (FRAME_MS 125), `.looping=true`, y_offset from −8. → 68x35, crop +12, starting y_offset 4.
- [x] 2.13 CONDUCTING ← `clawd-working-conducting-v2.svg`, prefix `conducting`, 8fps (FRAME_MS 125), `.looping=true`, y_offset from −8. → 60x57, crop +12, starting y_offset 4.
- [x] 2.14 LOW_BATTERY ← `clawd-idle-low-battery-v2.svg`, prefix `low_battery`, 6fps (FRAME_MS 167), `.looping=true`, y_offset from −8. → 52x46, crop +12, starting y_offset 4.
- [x] 2.15 HAT_MISHAP ← `clawd-hat-mishap-v2.svg`, prefix `hat_mishap`, 6fps (FRAME_MS 167), `.looping=true`, y_offset from −7. → 68x51, crop +12, starting y_offset 5.

## Phase 2.C: Human-Review Gate (per anim — NOT auto-testable, main risk)

- [x] 2.16 [HUMAN-REVIEW GATE] For each of the 14 anims, capture a simulator screenshot and visually confirm ground-aligned placement at the frozen scale; for ALERT, HAPPY, SWEEPING confirm the oneshot last-frame hold. Record per-anim approval of the final y_offset before freezing. (Spec: Vertical Placement; Design: Risks → manual y_offset) — DONE: crop-delta offsets (-8+12 formula) all sank the crabs; measured that all 15 cropped sprites have 0 bottom-transparent rows, so ONE uniform offset works. User tuned to y_offset -21 and raised GRASS_HEIGHT 14→24 ("more floor"). Confirmed feet-on-line in simulator. Commit e61dba2. SCOPE NOTE: GRASS_HEIGHT change also affects the 7 v1 anims — spot-checked wizard + beacon, both still ground-aligned.

## Phase 2.D: Final Full Verification

- [x] 2.17 Run the full parametrized contract+heap test: all 15 prefixes GREEN (dims, decode-to-exact-pixel, `W*H*3 <= 73*1024`). (Spec: Dimensions/Decode, Heap Bound) — GREEN (orchestrator-verified).
- [x] 2.18 Run the `frame_ms` simulator-capture test for all 15: each `ms == round(1000/fps)` and matches its `*_FRAME_MS` macro. (Spec: Per-Anim Frame Timing) — GREEN (9.8s).
- [x] 2.19 Run the 7-header byte-identical no-regression test: all GREEN (v1 anims untouched). (Spec: No Regression for Non-v2 Anims) — GREEN (headers byte-identical; only scene.c GRASS_HEIGHT/y_offset changed, not the v1 sprite data).
- [ ] 2.20 Build the firmware (`idf.py build`) and build the SDL2 simulator; confirm both compile with all 15 regenerated headers and shared `scene.c`. (Design: Risks → shared scene.c) — SIMULATOR build GREEN. `idf.py build` BLOCKED: idf.py not on PATH in this environment; must be run where ESP-IDF 5.3.2 is activated before flashing.
- [ ] 2.21 Retarget/rebase the PR2 branch onto main after PR1 merges so the PR2 diff shows only the 14-anim work; open PR2 with the dependency diagram marking PR2 with 📍. (chained-pr: clean diff rule) — PENDING: no push/PR yet (user working locally).
