# device-v2-sprites Specification

## Purpose

The ESP32-C6 firmware (and the shared SDL2 simulator) render the redesigned v2 crab art for the 15 mapped animations at device render scale, with per-anim frame timing, looping behavior, and vertical placement preserved. The 7 animations with no v2 counterpart keep rendering v1 unchanged.

## Requirements

### Requirement: v2 Sprite Art Replacement

The firmware MUST render v2 art, generated from the corresponding v2 SVG, for each of the 15 mapped animations: IDLE←idle, ALERT←notification, HAPPY←happy, SLEEPING←sleeping, THINKING←thinking, TYPING←typing, BUILDING←building, CONFUSED←confused, DIZZY←dizzy, SWEEPING←sweeping, DEBUGGER←debugger, CONDUCTING←conducting, WAKE←wake, LOW_BATTERY←low_battery, HAT_MISHAP←hat_mishap. No new animation enum SHALL be added and `waiting_reply` SHALL remain excluded (no device slot).

#### Scenario: Mapped anim renders v2 art

- GIVEN a mapped animation X whose `sprite_X.h` was regenerated from `clawd-X-v2.svg`
- WHEN `scene.c` renders X via `anim_defs[X]`
- THEN the rendered frames come from the regenerated `X_rle_data`/`X_frame_offsets`
- AND no new `clawd_anim_id_t` enum value is introduced

### Requirement: Sprite Dimensions and Decode Contract

Every regenerated `sprite_*.h` MUST declare `*_WIDTH`, `*_HEIGHT`, and `*_FRAME_COUNT` macros consistent with the rendered PNGs. Every frame MUST RLE-decode to exactly `WIDTH*HEIGHT` pixels with no buffer overrun, and `ensure_frame_buf` MUST allocate `w*h*3` (device) for the declared dimensions.

#### Scenario: Header macros match rendered output

- GIVEN a regenerated `sprite_X.h`
- WHEN its macros are parsed (e.g. `analyze_sprite_bounds.parse_header`)
- THEN `X_WIDTH`, `X_HEIGHT`, `X_FRAME_COUNT` equal the rendered PNG dimensions and frame count

#### Scenario: Every frame decodes to exact pixel count

- GIVEN a regenerated `sprite_X.h` with `N = X_FRAME_COUNT` frames
- WHEN each frame is RLE-decoded
- THEN each frame yields exactly `X_WIDTH * X_HEIGHT` pixels
- AND no decode writes beyond the allocated buffer

### Requirement: Per-Anim Frame Timing

Each ported anim's `*_FRAME_MS` macro MUST equal `1000/fps` for its v2 fps: idle/sleeping/low_battery/hat_mishap = 6 fps; thinking/typing/debugger/building/conducting/wake/confused/dizzy/sweeping = 8 fps; happy/alert = 10 fps.

#### Scenario: frame_ms matches v2 fps

- GIVEN a ported anim X with v2 fps F
- WHEN `scene_get_anim_info(X, &frame_count, &frame_ms)` is read (simulator `--capture`)
- THEN `frame_ms == 1000/F` (167 for 6 fps, 125 for 8 fps, 100 for 10 fps)
- AND `anim_defs[X].frame_ms` equals the `X_FRAME_MS` macro

### Requirement: Looping and Oneshot Behavior

Oneshot anims (happy, wake, sweeping — `.looping=false`) MUST hold the last frame after playing once. Looping anims MUST keep looping. Each ported anim's looping flag MUST match the pre-change value for that anim.

#### Scenario: Oneshot holds last frame

- GIVEN happy, wake, or sweeping with `.looping=false`
- WHEN the animation plays past its final frame
- THEN the final frame is held and playback does not restart

#### Scenario: Looping anim repeats

- GIVEN a ported anim with `.looping=true` (e.g. idle, thinking)
- WHEN playback reaches the final frame
- THEN playback wraps to the first frame
- AND the `.looping` flag equals the pre-change value for that anim

### Requirement: Vertical Placement

Each ported anim's `y_offset` MUST be set so the crab sits ground-aligned on the 320x172 panel. Final placement SHOULD be visually confirmed in the simulator.

#### Scenario: y_offset recomputed per anim

- GIVEN a regenerated `sprite_X.h` with new dimensions
- WHEN `crop_sprites.py` reports the y_offset delta
- THEN `anim_defs[X].y_offset` is updated so the crab is ground-aligned on 320x172
- AND placement is visually confirmed in the simulator before freezing

### Requirement: No Regression for Non-v2 Anims

The 7 anims with no v2 counterpart (DISCONNECTED, JUGGLING, WALKING, GOING_AWAY, WIZARD, BEACON, MINI_CLAWD) MUST continue to render their v1 art unchanged.

#### Scenario: v1 anims unchanged

- GIVEN a non-v2 anim Y (e.g. DISCONNECTED)
- WHEN the change is applied and the firmware/simulator renders Y
- THEN Y's `sprite_Y.h`, dimensions, frame count, frame_ms, looping, and y_offset are unchanged from pre-change

### Requirement: Peak Per-Frame Heap Bound

No ported v2 frame at the chosen render scale MAY exceed the current device peak per-frame decode heap of 73 KB (v1 DISCONNECTED, 182×137). The change MUST NOT introduce a new worst-case decode buffer.

#### Scenario: v2 frame stays under existing peak

- GIVEN a ported anim X at the chosen scale
- WHEN its largest frame decode buffer is measured as `X_WIDTH * X_HEIGHT * 3` bytes (device)
- THEN the value does not exceed 73 KB
- AND the overall peak per-frame heap remains the unchanged v1 DISCONNECTED frame

### Requirement: Pipeline Reproducibility on Windows

The asset pipeline MUST run on Windows using system Python 3.11, which requires the committed `svg2frames.py` `.resolve()` fix.

#### Scenario: Pipeline runs on Windows

- GIVEN the `svg2frames.py` `.resolve()` fix is committed
- WHEN `svg2frames.py` runs under system Python 3.11 on Windows for a v2 SVG
- THEN frames are generated without the pre-fix URI/path failure

### Requirement: Render Scale Validation

The render scale (working default x3) MUST be validated in the simulator before it is frozen. Acceptance SHOULD be stated as "scale confirmed in simulator" rather than hardcoding x3 as immutable.

#### Scenario: Scale confirmed before freeze

- GIVEN sprites generated at the working default scale (x3)
- WHEN placement and size are reviewed in the SDL2 simulator
- THEN the scale is accepted as "confirmed in simulator" (or adjusted and re-confirmed)
- AND the accepted scale is applied uniformly to all 15 ported anims
