# Design: Port v2 crab animations onto ESP32-C6 firmware (render scale x3)

## Technical Approach

Direct compile-time sprite swap for the 15 v1 anims that have a v2 counterpart. Per anim:
regenerate `sprite_<prefix>.h` in place from the v2 SVG at `--scale 3 --snap exact`, crop, retune
`y_offset`, match `*_FRAME_MS` to v2 fps, preserve `.looping`. The `scene.h` enum and the vestigial
`clawd_sprites.h` are untouched. Dims flow from the header macros into `anim_defs[]`
(`scene.c:148`). Tests are written FIRST (strict_tdd): a Python header-contract test parses each
regenerated header and asserts dims + decode integrity + heap ceiling, and the simulator capture
asserts `frame_ms`. Delivery is two slices: PR1 proves the full path on one pilot anim; PR2 ports
the remaining 14 with the proven driver + parametrized test.

## Asset Pipeline (per anim, deterministic)

Prerequisite (PR1, first commit): commit the `svg2frames.py` `.resolve()` Windows fix (~line 290).
Pipeline runs on **system Python 3.11** (Pillow+numpy+playwright+chromium; host venv lacks numpy):

```
py -3.11 tools/svg2frames.py assets/svg-animations/<svg> <tmp>/ --fps <fps> --scale 3 --snap exact
py -3.11 tools/png2rgb565.py <tmp> firmware/main/assets/sprite_<prefix>.h --name <prefix>
py -3.11 tools/crop_sprites.py firmware/main/assets/sprite_<prefix>.h   # crops in place, PRINTS y_offset delta
py -3.11 tools/analyze_sprite_bounds.py firmware/main/assets/sprite_<prefix>.h  # verify bounds
```

### anim → SVG → prefix → fps (all 15, filenames verified against `assets/svg-animations/`)

| Enum | SVG file | prefix | fps | `*_FRAME_MS` macro | looping |
|------|----------|--------|-----|--------------------|---------|
| IDLE | clawd-idle-living-v2.svg | `idle` | 6 | `IDLE_FRAME_MS` | true |
| ALERT | **clawd-notification-v2.svg** | `alert` | 10 | `ALERT_FRAME_MS` | **false** |
| HAPPY | clawd-happy-v2.svg | `happy` | 10 | `HAPPY_FRAME_MS` | **false** |
| SLEEPING | clawd-sleeping-v2.svg | `sleeping` | 6 | `SLEEPING_FRAME_MS` | true |
| THINKING | clawd-working-thinking-v2.svg | `thinking` | 8 | `THINKING_FRAME_MS` | true |
| TYPING | clawd-working-typing-v2.svg | `typing` | 8 | `TYPING_FRAME_MS` | true |
| BUILDING | clawd-working-building-v2.svg | `building` | 8 | `BUILDING_FRAME_MS` | true |
| CONFUSED | clawd-working-confused-v2.svg | `confused` | 8 | `CONFUSED_FRAME_MS` | true |
| DIZZY | clawd-dizzy-v2.svg | `dizzy` | 8 | `DIZZY_FRAME_MS` | true |
| SWEEPING | clawd-working-sweeping-v2.svg | `sweeping` | 8 | `SWEEPING_FRAME_MS` | **false** |
| DEBUGGER | clawd-working-debugger-v2.svg | `debugger` | 8 | `DEBUGGER_FRAME_MS` | true |
| CONDUCTING | clawd-working-conducting-v2.svg | `conducting` | 8 | `CONDUCTING_FRAME_MS` | true |
| WAKE | clawd-wake-v2.svg | `wake` | 8 | `WAKE_FRAME_MS` | **false** |
| LOW_BATTERY | clawd-idle-low-battery-v2.svg | `low_battery` | 6 | `LOW_BATTERY_FRAME_MS` | true |
| HAT_MISHAP | clawd-hat-mishap-v2.svg | `hat_mishap` | 6 | `HAT_MISHAP_FRAME_MS` | true |

Name-mismatch note: ALERT's SVG is `clawd-notification-v2`, not `clawd-alert-*`. All other prefixes
match their SVG stem. `--name <prefix>` must be a valid C identifier (`low_battery`, `hat_mishap`
use underscores, matching existing macros). fps values confirmed in exploration (svg2mod_frames.py:42).

Driver decision below (Key Decisions): a thin `tools/regen_v2_sprite.py` driver runs the 4 commands
for one prefix and **echoes crop_sprites' y_offset delta without applying it** — the delta is a human
review artifact, never auto-written into scene.c.

## Firmware Wiring (`firmware/main/scene.c` only)

- **`anim_defs[]` (`scene.c:148`)**: for each of the 15 enums, `width`/`height`/`frame_count` already
  read from the header macros (`<PREFIX>_WIDTH/_HEIGHT/_FRAME_COUNT`) — regenerating the header
  updates them automatically, no edit. The ONLY hand-edits per entry are `y_offset` (recomputed from
  crop delta) and, if v2 fps differs from the current macro, the `*_FRAME_MS` macro.
- **`*_FRAME_MS` macros (`scene.c:106-131`)**: current values already match the v2 fps table above
  (IDLE/SLEEPING/LOW_BATTERY/HAT_MISHAP=6→167, ALERT/HAPPY=10→100, the 8fps group=125). Expected
  edits here are **zero unless a regenerated frame count implies a different intended fps**; the
  frame_ms test (below) is the guard.
- **`y_offset`**: current values are IDLE −8, ALERT −4, HAPPY −7, SLEEPING −8, THINKING −8, TYPING
  −8, BUILDING −4, CONFUSED −4, DIZZY −8, SWEEPING 0, DEBUGGER −8, CONDUCTING −8, WAKE −8,
  LOW_BATTERY −8, HAT_MISHAP −7. Each is recomputed from the crop delta and confirmed visually.
- **`.looping`**: preserved exactly. Oneshots that hold last frame = **ALERT, HAPPY, SWEEPING, WAKE**
  (`.looping = false`). All other 11 mapped anims loop. (Correction to the brief: ALERT is also a
  oneshot in the current code, not only happy/wake/sweeping.)
- **`scene.h`**: UNCHANGED (no new slots). **`clawd_sprites.h`**: vestigial, NOT touched.
- No other reference to old sprite dims exists: `anim_defs` consumes only the macros; `decode_and_apply_frame`
  / `ensure_frame_buf` read `def->width/height` at runtime. Confirmed no hardcoded dimension literals
  for the mapped prefixes outside each `sprite_*.h`.

## Test Contract (strict_tdd — tests written FIRST)

New dir `tools/tests/` (joins existing `test_svg2frames_snap.py`), run with system py3.11.

| Test | Shape | Assertion |
|------|-------|-----------|
| Header contract | **ONE parametrized test** over the 15 ported prefixes | For each: `analyze_sprite_bounds.parse_header()` returns `fmt=='rle'`; `WIDTH>0`, `HEIGHT>0`, `FRAME_COUNT==len(frame_offsets)-1`; every frame RLE-decodes (via `decode_frame`) to **exactly WIDTH*HEIGHT pixels with no overrun** (RLE run-sum == W*H, not padded/truncated) |
| Heap ceiling | parametrized over 15 | `WIDTH*HEIGHT*3 <= 73*1024` (current device peak = DISCONNECTED v1, which stays v1) |
| frame_ms | simulator `--capture` | `scene_get_anim_info(&fc,&ms)` → assert `ms == round(1000/fps)` per anim via `sim_main.c --capture` driving `scene_get_anim_info`. **Chosen over firmware/test C** because the mapping lives in `anim_defs[]` compiled into `scene.c` and the simulator already exposes it machine-readably |
| v1 no-regression | ONE test | The 7 non-v2 headers (`disconnected, juggling, walking, going_away, wizard, beacon, mini_crab`) are **byte-identical** to their committed git blob (SHA compare), proving they were untouched |

Parametrized over per-prefix tests: **parametrized** — one driver, 15 cases, fails loudly naming the
offending prefix; adding PR2's 14 is a data-list edit, not new test code. The `frame_ms` check is the
one path that must go through the simulator capture because it exercises the compiled `anim_defs[]`.

## Delivery / PR Split

**PR1 — pilot (proves the whole path):**
1. Commit the `svg2frames.py` `.resolve()` fix (fix only).
2. Add `tools/tests/` header-contract + heap + frame_ms + no-regression scaffolding.
3. Drive ONE pilot anim end to end: **WAKE** (`clawd-wake-v2.svg`, 8fps, `.looping=false`). Chosen
   because it is a **oneshot** (exercises the last-frame-hold path, the riskier branch) AND currently
   carries a **non-trivial y_offset (−8)** that must be recomputed — so the pilot proves crop/offset
   retuning, oneshot hold, timing, header-contract test, and simulator visual review in one slice.
4. Simulator visual check of WAKE at x3; freeze scale decision here.

**PR2 — remaining 14:** reuse the proven `tools/regen_v2_sprite.py` driver and extend the
parametrized prefix list from 1 → 15. Per-anim: regenerate, crop, retune `y_offset`, verify macros,
visual check. No new test code — only the prefix data list and 14 `y_offset` values change.

Chain strategy (stacked-to-main vs feature-branch-chain) is **deferred to sdd-tasks**. Boundaries:
PR1 = fix + harness + pilot (fully green, mergeable alone); PR2 = the 14, depends on PR1's driver+tests.

## Key Decisions

| Decision | Choice | Alternatives | Rationale |
|----------|--------|--------------|-----------|
| Batch vs manual | Thin per-anim driver `tools/regen_v2_sprite.py` that runs the 4 commands and **prints** the y_offset delta | Full batch over 15; fully manual | Repeatable + deterministic, but keeps the human y_offset review explicit — driver never writes scene.c |
| Test home | Python (`tools/tests`) for contract/heap/no-regression; simulator capture for frame_ms | C `firmware/test` | parse_header + decode_frame already exist in Python; frame_ms lives in compiled `anim_defs[]`, only the sim exposes it machine-readably |
| Replace vs new files | Replace `sprite_<prefix>.h` in place (same prefix) | New `sprite_<prefix>_v2.h` | No selector exists; same prefix means dims auto-flow and no `#include`/enum edits; clean git revert |
| y_offset review | crop_sprites prints delta → human applies to scene.c → simulator screenshot confirms | Auto-apply delta | Final placement is visual; auto-apply hides regressions |
| Scale x3 freeze | Validate WAKE in simulator in PR1, then freeze x3 | Freeze upfront | x3 is working default, not proven; pilot locks it before the 14 |

## Risks → Mechanism

| Risk | Catch |
|------|-------|
| Manual y_offset wrong (main risk) | crop delta printed by driver + mandatory simulator screenshot review per anim; not test-automatable, so gated by explicit human-review task |
| Oneshot loses last-frame hold (ALERT/HAPPY/SWEEPING/WAKE) | `.looping=false` preserved; pilot = WAKE exercises the hold path; simulator visual confirms |
| Timing drift v1→v2 | frame_ms simulator-capture test asserts `ms==round(1000/fps)` per anim |
| Shared `scene.c` breaks simulator (ARGB8888/RGB565A8, slot counts) | simulator build + visual check is a required step both PRs; `make test` decoder coverage |
| Forgetting crop step | header-contract heap test fails loudly if uncropped dims push `W*H*3` over ceiling; bounds verified by analyze_sprite_bounds |
| v1 regression | byte-identical SHA no-regression test over the 7 untouched headers |

## Open Questions
- [ ] Scale x3 vs x2 — resolve via WAKE simulator review in PR1 (design assumes x3).
- [ ] Chain strategy (stacked vs feature-branch) — deferred to sdd-tasks.
