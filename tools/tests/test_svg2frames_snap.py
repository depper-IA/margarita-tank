"""Tests for the colour snapping in tools/svg2frames.py.

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

import svg2frames


def _save(pixels, path):
    """pixels: list of rows, each a list of (r, g, b, a)."""
    arr = np.array(pixels, dtype=np.uint8)
    Image.fromarray(arr, "RGBA").save(path)


def _load(path):
    return np.array(Image.open(path).convert("RGBA"))


class ExtractSvgPaletteTest(unittest.TestCase):
    def test_reads_attributes_and_css_declarations(self):
        svg = (
            '<svg><style>.a { fill: #DE886D; color:#abc; }</style>'
            '<rect fill="#6b3122"/><path stroke=\'#FFFFFF\'/>'
            '<g stop-color="#000"/></svg>'
        )
        self.assertEqual(
            svg2frames.extract_svg_palette(svg),
            [(0, 0, 0), (0x6B, 0x31, 0x22), (0xAA, 0xBB, 0xCC), (0xDE, 0x88, 0x6D), (255, 255, 255)],
        )

    def test_ignores_element_ids_that_look_like_hex(self):
        svg = '<use href="#add"/><use href="#face00"/><rect id="x" fill="#112233"/>'
        self.assertEqual(svg2frames.extract_svg_palette(svg), [(0x11, 0x22, 0x33)])

    def test_ignores_non_color_properties(self):
        svg = '<rect background="#123456" data-color="#654321"/>'
        self.assertEqual(svg2frames.extract_svg_palette(svg), [])


class SnapPixelArtTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "frame.png"

    def test_exact_palette_keeps_more_than_twelve_colours(self):
        palette = [(i * 12 + 3, 255 - i * 11, (i * 29) % 256) for i in range(20)]
        _save([[c + (255,) for c in palette]], self.path)
        svg2frames.snap_pixel_art(self.path, palette=palette)
        out = _load(self.path)
        self.assertEqual([tuple(px[:3]) for px in out[0]], palette)
        self.assertTrue((out[:, :, 3] == 255).all())

    def test_exact_palette_snaps_antialiased_leftovers_to_nearest_declared_colour(self):
        palette = [(0xDE, 0x88, 0x6D), (0x6B, 0x31, 0x22)]
        _save([[(0xDC, 0x86, 0x6B, 255), (0x70, 0x33, 0x24, 255)]], self.path)
        svg2frames.snap_pixel_art(self.path, palette=palette)
        out = _load(self.path)
        self.assertEqual(tuple(out[0, 0][:3]), palette[0])
        self.assertEqual(tuple(out[0, 1][:3]), palette[1])

    def test_exact_palette_keeps_alpha_tiers(self):
        palette = [(10, 20, 30)]
        _save([[(10, 20, 30, 255), (0, 0, 0, 77), (10, 20, 30, 10), (10, 20, 30, 230)]], self.path)
        svg2frames.snap_pixel_art(self.path, palette=palette)
        out = _load(self.path)
        self.assertEqual(out[0, 0, 3], 255)  # solid stays solid
        self.assertEqual(tuple(out[0, 1]), (0, 0, 0, 77))  # intentional shadow untouched
        self.assertEqual(out[0, 2, 3], 0)  # noise removed
        self.assertEqual(out[0, 3, 3], 255)  # near-opaque becomes opaque

    def test_legacy_snap_still_clusters_to_the_twelve_most_common_rounded_colours(self):
        # Default behaviour must not change: colours are floored to multiples of 16.
        _save([[(0xDE, 0x88, 0x6D, 255)] * 4], self.path)
        svg2frames.snap_pixel_art(self.path)
        out = _load(self.path)
        self.assertEqual(tuple(out[0, 0][:3]), (0xD0, 0x80, 0x60))

    def test_legacy_snap_collapses_rich_palettes(self):
        # Documents why the exact mode exists: >12 colours cannot survive the legacy path.
        palette = [(i * 12, 255 - i * 12, 40) for i in range(20)]
        _save([[c + (255,) for c in palette]], self.path)
        svg2frames.snap_pixel_art(self.path)
        out = _load(self.path)
        self.assertLessEqual(len({tuple(px[:3]) for px in out[0]}), 12)


if __name__ == "__main__":
    unittest.main()
