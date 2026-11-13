#!/usr/bin/env python3
"""Run: python3 scripts/test_make_cover.py (needs macOS Optima / Avenir Next, Pillow, numpy, opencv-python)."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import numpy as np
from PIL import Image, ImageDraw

import grade_cover_photo as grade
import make_cover

FONTS = all(Path(f["path"]).exists() for f in make_cover.DEFAULT_FONTS.values())


class CoverSizeChecks(unittest.TestCase):
    def test_defaults_and_explicit_landscape_sizes(self):
        self.assertEqual(make_cover.Cover({}, Path(".")).size, (2560, 1440))
        for size in ([1920, 1080], [2560, 1440], [3840, 2160], (1600, 900)):
            with self.subTest(size=size):
                self.assertEqual(make_cover.Cover({"size": size}, Path(".")).size, tuple(size))

    def test_rejects_wrong_aspect_ratios_before_opening_photo(self):
        for size in ([1080, 1920], [1500, 2000], [1500, 1125], [2560, 1441]):
            with self.subTest(size=size), mock.patch.object(make_cover.Image, "open") as open_image:
                with self.assertRaisesRegex(ValueError, "English landscape 16:9.*Chinese 3:4 and 4:3"):
                    make_cover.Cover({"size": size, "photo": "missing.jpg"}, Path(".")).render()
                open_image.assert_not_called()

    def test_rejects_invalid_dimension_types_and_values(self):
        invalid = [
            None, True, 2560, "2560x1440", {}, [], [2560], [2560, 1440, 1],
            [0, 0], [0, 900], [1600, 0], [-1600, -900],
            [1600.0, 900.0], [1600, 900.0], [True, 9], [16, True],
            ["1600", 900], [float("nan"), 900], [float("inf"), 900],
        ]
        for size in invalid:
            with self.subTest(size=size):
                with self.assertRaisesRegex(ValueError, "two positive integers.*landscape 16:9"):
                    make_cover.Cover({"size": size}, Path("."))


@unittest.skipUnless(FONTS, "macOS cover fonts not installed")
class CoverChecks(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        Image.new("RGB", (1694, 1270), (225, 215, 200)).save(self.root / "photo.jpg")
        logo = Image.new("RGBA", (600, 160))
        d = ImageDraw.Draw(logo)
        d.ellipse((10, 30, 110, 130), fill=(255, 255, 255, 255))
        d.rectangle((150, 40, 590, 120), fill=(255, 255, 255, 255))
        logo.save(self.root / "logo.png")
        mark = Image.new("RGBA", (500, 110))
        ImageDraw.Draw(mark).rectangle((150, 10, 490, 100), fill=(10, 10, 10, 255))
        mark.save(self.root / "inline.png")
        self.cfg = {
            "photo": "photo.jpg", "crop": [0, 160, 1440],
            "lockup": {"logo": {"path": "logo.png"}, "text": ["Interview", "Guest Name"]},
            "title": {"lines": ["This {brand} Maintainer", "Is Buying a University"], "accent": ["University"]},
            "inline_logos": {"brand": {"path": "inline.png", "word_height": 100}},
        }

    def render(self, **changes):
        return make_cover.Cover({**self.cfg, **changes}, self.root).render()

    def test_renders_full_size_inside_safe_area(self):
        image, boxes = self.render()
        self.assertEqual(image.size, (2560, 1440))
        self.assertLess(boxes["lockup"][3], boxes["title"][1])
        self.assertGreater(boxes["title"][2] - boxes["title"][0], 1500)   # inline logo widened line 1

    def test_halo_lifts_area_around_dark_inline_logo(self):
        plain, boxes = self.render()
        lit = self.render(inline_logos={"brand": {**self.cfg["inline_logos"]["brand"],
                                                  "halo": {"peak": 200, "spread": 12, "blur": 22}}})[0]
        x0, y0 = boxes["title"][0], boxes["title"][1]
        region = (x0, y0 - 40, x0 + 900, y0 + 10)
        self.assertGreater(np.asarray(lit.crop(region)).mean(), np.asarray(plain.crop(region)).mean() + 2)

    def test_rejects_crop_outside_photo_and_soft_upscale(self):
        with self.assertRaisesRegex(ValueError, "leaves"):
            self.render(crop=[400, 160, 1440])
        with self.assertRaisesRegex(ValueError, "upscale"):
            self.render(crop=[0, 160, 1100])

    def test_rejects_text_over_protected_face(self):
        with self.assertRaisesRegex(ValueError, "protected face"):
            self.render(protect=[[100, 760, 400, 900]])

    def test_overlong_title_is_an_error_not_a_shrink(self):
        title = {**self.cfg["title"], "lines": ["This {brand} Maintainer Is Definitely", "Buying a University"]}
        with self.assertRaisesRegex(ValueError, "safe area"):
            self.render(title=title)


class GradeChecks(unittest.TestCase):
    def test_grade_is_global_and_presets_step_down(self):
        rgb = np.full((60, 80, 3), 0.35, np.float32)
        rgb[:, :40] = 0.7
        outs = {k: grade.grade(rgb, **{**p, "glow": 0}) for k, p in grade.PRESETS.items()}
        for out in outs.values():
            self.assertTrue(np.allclose(out[:, 45], out[:, 75]))          # same input, same output anywhere
        mid = {k: float(v[:, 60].mean()) for k, v in outs.items()}
        self.assertGreater(mid["bright"], mid["a"])
        self.assertGreater(mid["a"], mid["b"])


if __name__ == "__main__":
    unittest.main()
