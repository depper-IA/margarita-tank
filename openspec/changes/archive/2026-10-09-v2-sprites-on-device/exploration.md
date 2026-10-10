# Exploration: Port v2 crab animations onto ESP32-C6 firmware (device render scale x3)

Status: complete · Artifact store: openspec · Engram: `sdd/v2-sprites-on-device/explore` (id 3496)

## Goal

Port the v2 crab animations (currently host/terminal-only) onto the ESP32-C6 firmware so the
physical device plays the redesigned v2 art, at device render scale x3.

## Current State

Device sprites come from RLE RGB565 C headers (`firmware/main/assets/sprite_*.h`). Each anim is
wired through a compile-time table `anim_defs[]` at `firmware/main/scene.c:259`, indexed by
`clawd_anim_id_t` (`firmware/main/scene.h:6-28`, 22 values). Each entry points at `*_rle_data`,
`*_frame_offsets`, `*_FRAME_COUNT`, a per-anim `*_FRAME_MS` macro (`scene.c:106-131`), plus
`looping`, `width`, `height`, `y_offset`. Decode is per-frame: `decode_and_apply_frame`
(`scene.c:497`) + `ensure_frame_buf` (`scene.c:479`) which does `malloc(w*h*3)` from internal heap
(RGB565A8; simulator uses `w*h*4` ARGB8888). No PSRAM.

`clawd_sprites.h` is VESTIGIAL — declares `CLAWD_ANIM_COUNT 5` with 5-entry tables that `scene.c`
does NOT use. scene.c includes each `sprite_*.h` directly and builds its own `anim_defs[]`.
Swapping art does not require touching `clawd_sprites.h`.

Device art is FIXED AT COMPILE TIME. No runtime style toggle, no BLE path, no config path selects
art style. The `/margarita style v1|v2` toggle is terminal-only. BLE "v2/v3" at
`ble_service.c:295` is PROTOCOL version, not art style.

## v2 → firmware enum mapping

ANIMS_V2 (`anims-v2/index.ts:22`) = 16 anims + `idle_living` alias.

- 15 device enums HAVE a v2 counterpart (swap targets): IDLE←idle, ALERT←notification, HAPPY←happy,
  SLEEPING←sleeping, THINKING←thinking, TYPING←typing, BUILDING←building, CONFUSED←confused,
  DIZZY←dizzy, SWEEPING←sweeping, DEBUGGER←debugger, CONDUCTING←conducting, WAKE←wake,
  LOW_BATTERY←low_battery, HAT_MISHAP←hat_mishap.
- 7 device enums have NO v2 — must keep v1 working: DISCONNECTED, JUGGLING, WALKING, GOING_AWAY,
  WIZARD, BEACON, MINI_CLAWD.
- 1 v2 anim has NO device slot: `waiting_reply`. Excluded unless a new enum + protocol path is added.

## Asset pipeline (one anim, end to end)

1. `python tools/svg2frames.py assets/svg-animations/clawd-<name>-v2.svg <out>/ --fps <fps> --scale 3 --snap exact`
   — system Python 3.11 (Pillow+numpy+playwright+chromium; host venv lacks numpy). The uncommitted
   `.resolve()` fix (~svg2frames.py:290) is required on Windows and is still uncommitted — commit first.
2. `python tools/png2rgb565.py <out> firmware/main/assets/sprite_<name>.h --name <name>` — emits
   `#define <NAME>_WIDTH/_HEIGHT/_FRAME_COUNT`, `static const uint32_t <name>_frame_offsets[N+1]`,
   `static const uint16_t <name>_rle_data[]`. png2rgb565 does NOT crop.
3. `tools/crop_sprites.py` crops in place and prints the y_offset deltas for scene.c.
   `tools/analyze_sprite_bounds.py` reports bounds.

Naming: enum `CLAWD_ANIM_X` → prefix `x` → `sprite_x.h`. Watch mismatches: ALERT↔svg
`clawd-notification`, WALKING↔svg `crab-walking`. `--name` must be a valid C identifier.

## Wiring a new/replaced sprite

Pure swap (e.g. HAPPY): regenerate `sprite_happy.h` (same prefix). width/height/frame_count flow
from the macros automatically; but `y_offset` is hand-tuned per anim and MUST be recomputed
(crop_sprites.py prints the delta), the `*_FRAME_MS` macro must match v2 fps, and `.looping` must be
preserved. No enum / clawd_sprites.h edit needed. Adding a slot (e.g. WAITING_REPLY) needs: new enum
in scene.h, new `#include` in scene.c, new `anim_defs[]` entry, new `*_FRAME_MS`, plus daemon/host
mapping to trigger it.

v2 fps (svg2mod_frames.py:42, confirmed by playback.test): idle/sleeping/low_battery/hat_mishap=6;
thinking/typing/debugger/building/conducting/waiting_reply/wake/confused/dizzy/sweeping=8; happy/alert=10.

## Replace vs Add

Flash: ~5.7 MB free of 7.94 MB; v1 ~1.25 MB — either fits. RECOMMEND REPLACE the 15 mapped v1
sprites with v2; keep v1 for the 7 non-v2 anims. Device art is compile-time with no selector, so
keeping both only bloats flash with no way to choose.

## Dimensions / heap at x3

Measured: happy-v2 x3 = 120×120, 42.2 KB/frame heap, 25.9 KB RLE. Current device peak heap =
73 KB (disconnected v1 182×137). Most v2 SVGs share viewBox `-15 -25 45 45` → ~135×135 pre-crop at
x3, cropping into the ~120×120 / ~45 KB class. confused-v2 is SMALLER than v1 confused. disconnected
has NO v2, so the 73 KB peak is UNCHANGED. Net: x3 per-v2-frame heap ≈ up to ~45 KB, below the
existing 73 KB peak — no new worst case introduced.

## Test setup & testable contract (strict_tdd=true)

- `firmware/test` (`make test`, gcc + ASan/UBSan): `test_rle_decode.c` covers the DECODER, not
  specific sprites.
- `simulator` (`cmake -B build && cmake --build build`): compiles the same `scene.c` via shims;
  `sim_main.c --capture` reads `scene_get_anim_info(&frame_count,&frame_ms)` → machine-readable contract.
- Testable contract for a re-rendered v2 sprite: assert header macros `<NAME>_WIDTH/_HEIGHT/_FRAME_COUNT`
  equal expected rendered dims + frame count; assert `anim_defs[X].frame_ms == 1000/fps`. A Python test
  (tools/tests, system py3.11) can parse via `analyze_sprite_bounds.parse_header` and assert every frame
  RLE-decodes to exactly width*height pixels without overrun.

## Risks

- `y_offset` retuning is manual/visual — crop_sprites.py prints deltas but final placement needs
  simulator screenshot review.
- frame-count/timing drift v1→v2; oneshots (happy/wake/sweeping, `.looping=false`) must keep correct
  last-frame hold.
- firmware + simulator SHARE scene.c (sim ARGB8888 4B vs device RGB565A8 3B; sim MAX_SLOTS=8 vs
  device 6) — a dims change affects both.
- svg2frames `.resolve()` fix uncommitted → not reproducible on Windows until committed.
- Forgetting crop_sprites.py → oversized buffers (heap regression) + wrong y_offset.
- `waiting_reply` v2 has no device slot/trigger — excluded unless enum+protocol added.

## Recommendation

Replace the 15 mapped v1 sprites with v2 at `--scale 3 --snap exact`, run crop_sprites.py, retune
y_offset per anim, keep the 7 non-v2 anims on v1, no runtime toggle. Commit the svg2frames
`.resolve()` fix first. Add a header-contract test (dims + frame count + frame_ms) per regenerated
sprite.

Ready for Proposal: Yes.
