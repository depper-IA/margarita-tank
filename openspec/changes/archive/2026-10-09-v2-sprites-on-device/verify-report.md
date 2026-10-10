# Verify Report: v2-sprites-on-device

- **Change**: v2-sprites-on-device
- **Spec**: openspec/changes/v2-sprites-on-device/specs/device-v2-sprites/spec.md
- **Phase**: sdd-verify (READ-ONLY — no code modified)
- **Branch**: personal @ e61dba2
- **Environment**: system Python 3.11, simulator/build/clawd-tank-sim.exe (freshly rebuilt — "ninja: no work to do", i.e. already in sync with current headers)
- **Verdict**: PASS WITH WARNINGS — ready to archive once the GRASS_HEIGHT scope note is reconciled and the two documented verification gaps (firmware idf.py build; 5 of 7 v1 anims not visually re-checked) are accepted.

---

## Test Evidence

| Suite | Result | Evidence |
|-------|--------|----------|
| `V2SpriteContractTest.test_header_contract` | PASS | 15 prefixes: fmt=rle, W/H/FRAME_COUNT>0, FRAME_COUNT==len(offsets)-1, every frame RLE run-sum == W*H, no overrun. `Ran 3 tests ... OK` (0.681s) |
| `V2SpriteContractTest.test_heap_ceiling` | PASS | peak = HAPPY 90x75 = 20,250 B << 74,752 B (73 KB) ceiling. All 15 well under |
| `V1NoRegressionTest.test_v1_headers_unchanged` | PASS | 7 v1 headers `git diff --quiet HEAD` exit 0 (disconnected, juggling, walking, going_away, wizard, beacon, mini_crab) |
| `FrameMsSimulatorTest.test_frame_ms_matches_fps` | PASS | 15 anims via `--capture-anim`, each ms == round(1000/fps). `Ran 1 test ... OK` (10.0s) |

Direct frame_ms proof (6fps 166->167 fix): `clawd-tank-sim.exe --capture-anim idle` ->
`[capture] Animation 'idle': 96 frames, 167ms/frame` and machine line `frame_ms=167`.
Confirms `IDLE_FRAME_MS ((1000+3)/6) == 167` (plain `1000/6` would truncate to 166).

Per-anim decode buffer (W*H*3 bytes), all < 73 KB:
wake 56x48=8064; idle 62x41=7626; alert 62x69=12834; happy 90x75=20250; sleeping 70x75=15750;
thinking 62x69=12834; typing 66x57=11286; building 108x50=16200; confused 70x57=11970;
dizzy 70x53=11130; sweeping 108x38=12312; debugger 66x35=6930; conducting 58x57=9918;
low_battery 52x46=7176; hat_mishap 68x51=10404. PEAK=20250 (happy).

---

## Spec Compliance Matrix

| # | Requirement | Verdict | Evidence |
|---|-------------|---------|----------|
| 1 | v2 Sprite Art Replacement | PASS | scene.c anim_defs for all 15 enums reference `<prefix>_rle_data`/`_frame_offsets`/`_WIDTH`/`_HEIGHT`/`_FRAME_COUNT` from regenerated headers; no new `clawd_anim_id_t`; waiting_reply has no slot. 14 regenerated in 7d80e27, WAKE in 5028c08 |
| 2 | Sprite Dimensions & Decode Contract | PASS | `test_header_contract` green: every frame RLE run-sum == exact W*H, no overrun, FRAME_COUNT consistent |
| 3 | Per-Anim Frame Timing | PASS | `test_frame_ms_matches_fps` green for all 15; 6fps macros yield 167 (`(1000+3)/6`), 8fps=125, 10fps=100; captured idle=167 directly |
| 4 | Looping & Oneshot | PASS | scene.c verified: ALERT/HAPPY/SWEEPING/WAKE `.looping=false`; the other 11 ported anims `.looping=true` (idle, sleeping, thinking, typing, building, confused, dizzy, debugger, conducting, low_battery, hat_mishap). Matches design table |
| 5 | Vertical Placement | PASS (by review) | All 15 ported anims `y_offset=-21` in scene.c; human-approved in simulator per apply-progress (commits 60f5efd, e61dba2). SHOULD-level visual acceptance; recorded as human-reviewed |
| 6 | No Regression for Non-v2 Anims | PARTIAL | 7 v1 headers byte-identical to HEAD (test green). BUT GRASS_HEIGHT 14->24 (scene.c:51) changes the shared scene for all 7 v1 anims; only wizard+beacon spot-checked. See WARNING-1 |
| 7 | Peak Per-Frame Heap Bound | PASS | peak ported = happy 20,250 B; stays below the unchanged v1 DISCONNECTED 182x137 (73 KB) worst case |
| 8 | Pipeline Reproducibility on Windows | PASS | svg2frames `.resolve()` fix committed (task 1.1 / commit noted ac0527f in brief; pipeline ran under py3.11 to produce all 15 headers). Not re-executed this phase — headers are the artifact of a successful run |
| 9 | Render Scale Validation | PASS | x3 frozen after WAKE simulator review (apply-progress + engram scale-decision 3503); applied uniformly to all 15 |

---

## Findings by Severity

### CRITICAL
None.

### WARNING
- **WARNING-1 — GRASS_HEIGHT scope expansion, not covered by spec.** scene.c:51 raises `GRASS_HEIGHT` 14->24 and sets a uniform `y_offset=-21`. The spec's "No Regression for Non-v2 Anims" requires the 7 v1 anims render "unchanged"; their sprite_*.h bytes are unchanged, but their on-screen vertical placement shifts because the grass band is taller and shared. The spec/proposal have NO requirement covering grass height or v1 placement under a taller grass band. Only wizard+beacon were visually spot-checked; disconnected, juggling, walking, going_away, mini_crab were NOT re-checked with the 24px grass. Recommend either (a) add a spec requirement acknowledging the scene/grass change and its v1 impact, or (b) justify it as cosmetic-but-intended and record the v1 re-check.
- **WARNING-2 — Firmware build not verified.** Task 2.20 `idf.py build` is BLOCKED (idf.py not on PATH in this env). Only the SDL2 simulator build is confirmed. The shared scene.c + 15 regenerated headers have NOT been compiled for the ESP32-C6 target. Must be built where ESP-IDF 5.3.2 is active before flashing.

### SUGGESTION
- **SUGGESTION-1 — tasks.md dimension annotations drift from reality.** tasks.md 2.x list dims like alert 64x69, building 110x50, idle starting-offset notes; actual cropped headers are alert 62x69, building 108x50, wake 56x48, etc. Immaterial (tests assert against the real macros, all green) but the task notes are stale.
- **SUGGESTION-2 — Open items honestly incomplete.** Tasks 2.20 (idf.py) and 2.21 (PR not opened) remain `[ ]` — correctly reflected. No push/PR yet (user working locally).
- **SUGGESTION-3 — Deferred follow-up noted in apply-progress:** v2 background/sky/sun/grass animation raised by user, deferred to a future SDD change. The GRASS_HEIGHT bump is arguably the first toe into that scope.

---

## Verification Gaps (could NOT be verified this phase)
1. **Firmware target build** — `idf.py build` cannot run (idf.py not on PATH). ESP32-C6 compile of scene.c + 15 headers unverified.
2. **5 of 7 v1 anims visual re-check under 24px grass** — only wizard+beacon spot-checked; disconnected, juggling, walking, going_away, mini_crab not visually confirmed with the taller grass.
3. **On-device render/flash** — not performed (hardware not in loop).

---

## Next Recommended
- `sdd-archive` IF the WARNINGs are accepted: WARNING-1 reconciled (spec note or explicit cosmetic acceptance + v1 re-check) and WARNING-2/gaps acknowledged as out-of-env (firmware build deferred to an ESP-IDF-activated environment before flashing).
- Otherwise `sdd-apply` to (a) add a spec requirement for the grass/scene change and v1 placement, and/or (b) re-check the remaining 5 v1 anims in the simulator.
