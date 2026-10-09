"""Tests for tools/svg2mod_frames.py.

Run from the repo root with the sprite pipeline venv (needs Pillow and numpy):
    python -m unittest discover -s tools/tests -v
"""

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np
from PIL import Image

import svg2mod_frames as g

T = g.TRANSPARENT
RED, GREEN = (255, 0, 0, 255), (0, 255, 0, 255)
CLEAR = (0, 0, 0, 0)


def art_png(path, rows, px=2):
    """rows of RGBA art pixels -> PNG upscaled by px."""
    arr = np.array(rows, dtype=np.uint8).repeat(px, axis=0).repeat(px, axis=1)
    Image.fromarray(arr, "RGBA").save(path)


class DownscaleTest(unittest.TestCase):
    def test_exact_blocks(self):
        art = np.array([[RED, CLEAR], [CLEAR, GREEN]], dtype=np.uint8)
        big = art.repeat(2, axis=0).repeat(2, axis=1)
        np.testing.assert_array_equal(g.downscale(big), art)

    def test_rejects_misaligned_art(self):
        big = np.zeros((4, 4, 4), dtype=np.uint8)
        big[1, 1] = RED  # one device pixel of a 2x2 block
        with self.assertRaises(ValueError):
            g.downscale(big)

    def test_rejects_size_not_multiple(self):
        with self.assertRaises(ValueError):
            g.downscale(np.zeros((5, 4, 4), dtype=np.uint8))


class FlattenTest(unittest.TestCase):
    def test_opaque_kept_clear_transparent_partial_over_matte(self):
        art = np.array([[RED, CLEAR, (0, 0, 0, 77), (0, 0, 0, 10)]], dtype=np.uint8)
        out = g.flatten(art, matte=(0x80, 0x80, 0x80))
        self.assertEqual(out[0, 0], 0xFF0000)
        self.assertEqual(out[0, 1], T)
        # black at alpha 77/255 over grey 128 -> round(128 * (1 - 77/255)) = 89
        self.assertEqual(out[0, 2], (89 << 16) | (89 << 8) | 89)
        self.assertEqual(out[0, 3], T)  # below the alpha floor: noise


class CropTest(unittest.TestCase):
    def _f(self, cells, h=6, w=6):
        f = np.full((h, w), T, dtype=np.int64)
        for (y, x), c in cells.items():
            f[y, x] = c
        return f

    def test_union_bbox_and_even_height_pads_top(self):
        a = self._f({(2, 1): 1, (4, 2): 1})
        b = self._f({(3, 4): 2, (4, 4): 2})
        ca, cb = g.common_crop([a, b])
        # union: rows 2..4 (3 rows -> padded to 4 on top), cols 1..4 (4 cols)
        self.assertEqual(ca.shape, (4, 4))
        self.assertEqual(cb.shape, (4, 4))
        self.assertTrue((ca[0] == T).all())  # the pad row is on top
        self.assertEqual(ca[1, 0], 1)  # (2,1) -> pad + row 0, col 0
        self.assertEqual(cb[3, 3], 2)  # bottom row stays the bottom row

    def test_empty_animation_is_an_error(self):
        with self.assertRaises(ValueError):
            g.common_crop([self._f({})])


class EncodeTest(unittest.TestCase):
    def test_row_runs_and_trailing_transparent_dropped(self):
        letters = {10: "a", 20: "b"}
        self.assertEqual(g.encode_row([10, 10, 10, T, T, 20, T, T], letters), "a3.2b")
        self.assertEqual(g.encode_row([T, T, T], letters), "")
        self.assertEqual(g.encode_row([20], letters), "b")

    def test_round_trip(self):
        rng = np.random.default_rng(1)
        frame = rng.choice([T, 0x112233, 0x445566, 0x778899], size=(8, 13)).astype(np.int64)
        anim = g.build_animation([frame], 8)
        got = g.decode_frame(anim["frames"][0][0], anim["width"], anim["height"], anim["palette"])
        want = [[None if v == T else f"#{v:06X}" for v in row] for row in frame.tolist()]
        # the crop trims empty borders: compare inside the bbox
        ys, xs = np.nonzero(frame != T)
        self.assertEqual(anim["width"], xs.max() - xs.min() + 1)
        pad = anim["height"] - (ys.max() - ys.min() + 1)
        for y in range(anim["height"]):
            for x in range(anim["width"]):
                src_y = ys.min() + y - pad
                expected = want[src_y][xs.min() + x] if src_y >= ys.min() else None
                self.assertEqual(got[y][x], expected)


class AnimationTest(unittest.TestCase):
    def test_identical_consecutive_frames_merge_with_hold(self):
        a = np.array([[1, T], [T, T]], dtype=np.int64)
        b = np.array([[1, 2], [T, T]], dtype=np.int64)
        anim = g.build_animation([a, a, a, b, a], 10)
        self.assertEqual([hold for _, hold in anim["frames"]], [3, 1, 1])  # a is not merged across b
        self.assertEqual(sum(h for _, h in anim["frames"]), 5)
        self.assertEqual(anim["fps"], 10)
        self.assertEqual(anim["source_frames"], 5)

    def test_palette_is_exact_and_ordered_by_use(self):
        f = np.array([[0x00FF00, 0xFF0000, 0xFF0000, T]], dtype=np.int64)
        anim = g.build_animation([f, f], 6)
        self.assertEqual(anim["palette"], ["#FF0000", "#00FF00"])

    def test_too_many_colours_is_an_error(self):
        f = np.arange(53, dtype=np.int64).reshape(1, 53)
        with self.assertRaises(ValueError):
            g.build_animation([f], 6)


class EndToEndTest(unittest.TestCase):
    def test_png_dir_to_ts(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            (d / "idle").mkdir()
            art_png(d / "idle" / "frame_00.png", [[CLEAR, RED, CLEAR], [CLEAR, GREEN, (0, 0, 0, 77)]])
            art_png(d / "idle" / "frame_01.png", [[CLEAR, RED, CLEAR], [CLEAR, GREEN, (0, 0, 0, 77)]])
            frames = g.load_frames(d / "idle")
            self.assertEqual(len(frames), 2)
            anim = g.build_animation(frames, 6)
            self.assertEqual((anim["width"], anim["height"]), (2, 2))
            self.assertEqual(anim["frames"][0][1], 2)
            self.assertEqual(set(anim["palette"]), {"#FF0000", "#00FF00", "#1B1B1B"})  # shadow blended over the matte
            ts = g.anim_ts("idle", anim)
            self.assertIn("export const anim: V2Anim", ts)
            self.assertIn("fps: 6", ts)

    def test_index_maps_aliases(self):
        ts = g.index_ts(["idle", "happy"], {"idle_living": "idle"}, 57, 50)
        self.assertIn("idle_living: v2_idle,", ts)
        self.assertIn("V2_MAX_WIDTH = 57", ts)
        self.assertIn("import { anim as v2_happy } from './happy'", ts)


if __name__ == "__main__":
    unittest.main()
