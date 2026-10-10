# Proposal: Port v2 crab animations onto ESP32-C6 firmware (device render scale x3)

## Intent

The redesigned v2 crab art currently plays only on the host/terminal; the physical device still
renders the older v1 sprites. This change ports the v2 animations onto the ESP32-C6 firmware so the
device displays the redesigned art, replacing the 15 v1 sprites that have a v2 counterpart. Device
art is compile-time with no runtime style selector, so this is a direct sprite swap, not a toggle.

## Scope

### In Scope
- Commit the uncommitted `tools/svg2frames.py` Windows portability fix (`.resolve()` before
  `.as_uri()`), prerequisite for running the pipeline on Windows.
- Regenerate the 15 mapped sprites from v2 SVGs at `--scale 3 --snap exact`, run `crop_sprites.py`,
  retune `y_offset` per anim, match `*_FRAME_MS` to v2 fps, preserve `.looping`.
- Wire regenerated `sprite_*.h` into `scene.c` (same prefixes; dims flow from the macros).
- A header-contract test per regenerated sprite (`WIDTH`/`HEIGHT`/`FRAME_COUNT` + `frame_ms`).
- Visual validation of final placement/scale in the SDL2 simulator.

### Out of Scope
- The 7 anims with no v2 (DISCONNECTED, JUGGLING, WALKING, GOING_AWAY, WIZARD, BEACON, MINI_CLAWD)
  stay on v1. A mixed v1/v2 device state is the accepted intermediate end state.
- No device-side v1/v2 toggle (would need new enum + BLE/config + daemon plumbing).
- `waiting_reply` v2 (no device slot/trigger).
- No changes to host, claude-mod, or any BLE/protocol/installer surface.

## Capabilities

### New Capabilities
- `device-v2-sprites`: the firmware/simulator renders the v2 crab art for the 15 mapped anims at
  device scale, with per-anim frame timing, looping, and vertical placement preserved.

### Modified Capabilities
- None (no existing spec files; `openspec/specs/` holds only `.gitkeep`).

## Approach

Per-anim pipeline: `svg2frames.py` (system Python 3.11, `--scale 3 --snap exact`) ->
`png2rgb565.py` -> `crop_sprites.py` (prints `y_offset` deltas) -> wire into `scene.c` -> header
contract test -> simulator visual check. Delivery is split into chained PRs: PR1 commits the
svg2frames fix and drives ONE pilot animation end to end to prove the full path; PR2 ports the
remaining 14. Scale x3 is the working default but is treated as a decision to validate in the
simulator before freezing.

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `tools/svg2frames.py` | Modified | Commit `.resolve()` Windows fix (fix only). |
| `firmware/main/assets/sprite_*.h` | Modified | Regenerate 15 mapped sprites from v2. |
| `firmware/main/scene.c` | Modified | Per-anim `y_offset`, `*_FRAME_MS`, `.looping`. |
| `firmware/main/scene.h` | Reviewed | Enum unchanged (no new slots). |
| `simulator/` | Reviewed | Shares `scene.c`; used for visual validation. |
| `tools/tests` (+ `firmware/test`) | New | Header-contract tests per sprite. |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| `y_offset` retune is manual/visual (main execution risk) | High | `crop_sprites.py` deltas + simulator screenshot review per anim. |
| Oneshots lose last-frame hold | Med | Preserve `.looping=false` (happy/wake/sweeping). |
| Frame-count/timing drift v1->v2 | Med | Match `*_FRAME_MS` to v2 fps; header-contract test asserts `frame_ms`. |
| Shared `scene.c` dims change affects simulator (ARGB8888/RGB565A8, slot counts) | Med | Validate in simulator; `make test` decoder coverage. |
| Forgetting `crop_sprites.py` -> oversized buffers / wrong offset | Med | Required pipeline step; bounds asserted by test. |
| Heap regression at x3 | Low | Measured ~42-45 KB/frame, under existing 73 KB peak (unchanged, from v1 DISCONNECTED). |

## Rollback Plan

v1 `sprite_*.h` and `scene.c` are in git. Revert is `git checkout` of the affected headers +
`scene.c`. No BLE/protocol/installer surface is touched, so rollback is a clean revert with no
device re-provisioning or migration.

## Dependencies

- System Python 3.11 (Pillow + numpy + playwright + chromium) for the asset pipeline.
- Committed `svg2frames.py` `.resolve()` fix (first step of this change).
- SDL2 simulator build for visual validation.

## Open Questions / Assumptions

These were approved for proceeding but are recorded explicitly so they can be corrected:
1. **Scale x3 is the working default, NOT frozen.** Final scale must be validated in the simulator
   before locking (x3 gives ~120x120 crab on a 320x172 panel; measured 42 KB/frame vs 73 KB peak).
2. **Mixed v1/v2 is the accepted end state.** The 7 non-v2 anims stay v1; no toggle is added.
3. **The svg2frames `.resolve()` fix is the first step** (pipeline does not run on Windows without it).
4. **Delivery is split into chained PRs** (estimated >400 changed lines): PR1 = fix + one pilot anim
   end to end; PR2 = remaining 14. `waiting_reply` excluded (no device slot).

## Success Criteria

- [ ] `svg2frames.py` Windows fix committed; pipeline runs on Windows.
- [ ] 15 mapped sprites regenerated from v2, cropped, with retuned `y_offset`.
- [ ] `*_FRAME_MS` matches v2 fps and `.looping` preserved for every ported anim.
- [ ] Header-contract test passes per regenerated sprite.
- [ ] Final scale/placement visually confirmed in the simulator.
- [ ] The 7 non-v2 anims still render correctly on v1 (no regression).
