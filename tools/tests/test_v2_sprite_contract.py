"""Header-contract, heap-ceiling, frame_ms, and no-regression tests for the
v2 sprite port (change: v2-sprites-on-device).

Run under SYSTEM Python 3.11 (same interpreter used for the asset pipeline):
    py -3.11 -m unittest discover -s tools/tests -v
or just this module:
    py -3.11 -m unittest tools.tests.test_v2_sprite_contract -v

Strict TDD: the contract / heap / frame_ms cases are RED until each ported
sprite header is regenerated and the simulator is rebuilt. The 7-header
no-regression test is GREEN now and guards the untouched v1 anims.
"""

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import analyze_sprite_bounds as asb

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
ASSETS_DIR = REPO_ROOT / "firmware" / "main" / "assets"

TRANSPARENT_KEY = asb.TRANSPARENT_KEY

# Heap ceiling: current device peak per-frame decode buffer = v1 DISCONNECTED
# (182x137 @ 3 B/px). No ported v2 frame may exceed it.
HEAP_CEILING_BYTES = 73 * 1024

# Ported prefixes, seeded with ONLY the WAKE pilot (PR1). PR2 extends this list.
PORTED_PREFIXES = ["wake"]

# fps per ported prefix -> expected frame_ms == round(1000/fps).
PORTED_FPS = {
    "wake": 8,
}

# The 7 anims with NO v2 counterpart. These headers must stay byte-identical to
# their committed git blob (proving the port never touched them).
V1_UNTOUCHED_PREFIXES = [
    "disconnected", "juggling", "walking", "going_away",
    "wizard", "beacon", "mini_crab",
]


def _rle_run_sum(rle_data, frame_offsets, frame_idx):
    """Sum of RLE run counts for one frame (the TRUE decoded pixel count,
    before any padding/truncation). Also returns whether any run index
    overran the frame's [start, end) window."""
    start = frame_offsets[frame_idx]
    end = frame_offsets[frame_idx + 1]
    total = 0
    i = start
    overrun = False
    while i < end:
        if i + 1 >= len(rle_data):
            overrun = True
            break
        count = rle_data[i + 1]
        total += count
        i += 2
    # A well-formed frame consumes exactly [start, end) in (value,count) pairs.
    if i != end:
        overrun = True
    return total, overrun


class V2SpriteContractTest(unittest.TestCase):
    """Header contract + heap ceiling, parametrized over ported prefixes."""

    def _parse(self, prefix):
        path = ASSETS_DIR / f"sprite_{prefix}.h"
        self.assertTrue(path.is_file(), f"missing header: {path}")
        # parse_header returns: prefix, width, height, frame_count, data_a, data_b, fmt
        return path, asb.parse_header(path)

    def test_header_contract(self):
        for prefix in PORTED_PREFIXES:
            with self.subTest(prefix=prefix):
                _, parsed = self._parse(prefix)
                p, width, height, frame_count, data_a, data_b, fmt = parsed

                self.assertEqual(fmt, "rle", f"{prefix}: expected RLE format")
                self.assertGreater(width, 0, f"{prefix}: WIDTH must be > 0")
                self.assertGreater(height, 0, f"{prefix}: HEIGHT must be > 0")
                self.assertGreater(frame_count, 0, f"{prefix}: FRAME_COUNT must be > 0")

                frame_offsets, rle_data = data_a, data_b
                self.assertEqual(
                    frame_count, len(frame_offsets) - 1,
                    f"{prefix}: FRAME_COUNT must equal len(frame_offsets)-1",
                )

                # Every frame must RLE-decode to EXACTLY width*height pixels,
                # with no overrun (run-sum == W*H, not padded/truncated).
                expected = width * height
                for f in range(frame_count):
                    run_sum, overrun = _rle_run_sum(rle_data, frame_offsets, f)
                    self.assertFalse(
                        overrun, f"{prefix} frame {f}: RLE overran its offset window")
                    self.assertEqual(
                        run_sum, expected,
                        f"{prefix} frame {f}: RLE run-sum {run_sum} != W*H {expected}")

    def test_heap_ceiling(self):
        for prefix in PORTED_PREFIXES:
            with self.subTest(prefix=prefix):
                _, parsed = self._parse(prefix)
                _, width, height, _, _, _, _ = parsed
                buf = width * height * 3  # RGB565A8 device decode buffer
                self.assertLessEqual(
                    buf, HEAP_CEILING_BYTES,
                    f"{prefix}: W*H*3 = {buf} B exceeds {HEAP_CEILING_BYTES} B ceiling")


class V1NoRegressionTest(unittest.TestCase):
    """The 7 non-v2 headers must be identical to their committed git blob.

    We ask git itself (`git diff --quiet HEAD -- <path>`) whether the working
    tree differs from HEAD rather than SHA-comparing raw `git show` bytes. On
    this repo `core.autocrlf=true`, so the checked-out files carry CRLF while
    the stored blob is LF -- a raw byte SHA would spuriously differ on Windows.
    `git diff` applies the same checkout normalization git uses to decide if a
    file is "unchanged", which is the real no-regression contract: the port
    must not change these headers as git sees them.
    """

    def test_v1_headers_unchanged(self):
        for prefix in V1_UNTOUCHED_PREFIXES:
            with self.subTest(prefix=prefix):
                path = ASSETS_DIR / f"sprite_{prefix}.h"
                self.assertTrue(path.is_file(), f"missing header: {path}")
                rel = path.relative_to(REPO_ROOT).as_posix()
                proc = subprocess.run(
                    ["git", "diff", "--quiet", "HEAD", "--", rel],
                    cwd=str(REPO_ROOT),
                    capture_output=True,
                )
                # exit 0 = no diff (unchanged), 1 = differs, other = git error.
                self.assertNotEqual(
                    proc.returncode, 2,
                    f"git diff errored for {rel}: {proc.stderr.decode(errors='replace')}")
                self.assertEqual(
                    proc.returncode, 0,
                    f"{prefix}: working header differs from committed git blob (HEAD)")


class FrameMsSimulatorTest(unittest.TestCase):
    """frame_ms via the simulator --capture-anim path.

    Builds nothing itself; expects simulator/build/clawd-tank-sim(.exe) to exist.
    Runs `--capture-anim <prefix> <tmpdir>` and parses the machine-readable
    `frame_ms=<N>` line, asserting ms == round(1000/fps) per ported prefix.
    """

    @classmethod
    def _sim_binary(cls):
        build = REPO_ROOT / "simulator" / "build"
        for name in ("clawd-tank-sim.exe", "clawd-tank-sim"):
            cand = build / name
            if cand.is_file():
                return cand
            cand = build / "Debug" / name
            if cand.is_file():
                return cand
            cand = build / "Release" / name
            if cand.is_file():
                return cand
        return None

    def test_frame_ms_matches_fps(self):
        sim = self._sim_binary()
        if sim is None:
            self.fail(
                "simulator binary not found under simulator/build/ -- "
                "build it with: cmake -B simulator/build -S simulator ; "
                "cmake --build simulator/build"
            )
        for prefix in PORTED_PREFIXES:
            with self.subTest(prefix=prefix):
                fps = PORTED_FPS[prefix]
                expected_ms = round(1000 / fps)
                with tempfile.TemporaryDirectory(prefix=f"capture_{prefix}_") as tmp:
                    proc = subprocess.run(
                        [str(sim), "--capture-anim", prefix, tmp],
                        cwd=str(REPO_ROOT / "simulator"),
                        capture_output=True,
                        text=True,
                        timeout=120,
                    )
                stdout = proc.stdout or ""
                # Machine-readable line: "frame_ms=<N>"
                ms = None
                for line in stdout.splitlines():
                    line = line.strip()
                    if line.startswith("frame_ms="):
                        ms = int(line.split("=", 1)[1])
                        break
                self.assertIsNotNone(
                    ms, f"{prefix}: no 'frame_ms=' line in sim output:\n{stdout}\n{proc.stderr}")
                self.assertEqual(
                    ms, expected_ms,
                    f"{prefix}: sim frame_ms {ms} != round(1000/{fps}) {expected_ms}")


if __name__ == "__main__":
    unittest.main()
