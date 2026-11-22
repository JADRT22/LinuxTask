# -*- coding: utf-8 -*-
"""
LinuxTask - test_ui_theme.py
Description: Guards the visual redesign's two invariants: every colour is a
             cited token, and the palette meets the contrast budget. Runs
             headless -- ui_theme and the scan are pure Python.
Author: JADRT22 (https://github.com/JADRT22)
License: MIT
"""

import os
import re
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "src"))

import ui_theme

SRC_DIR = os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "src")

# #rrggbb literals are only allowed in ui_theme.py. Anywhere else means a
# surface was painted from memory instead of from a token.
HEX_LITERAL = re.compile(r"#[0-9a-fA-F]{6}\b")


class TestTokenCitations(unittest.TestCase):
    def test_every_token_names_its_source(self):
        for name, (value, citation) in ui_theme.TOKENS.items():
            with self.subTest(token=name):
                self.assertTrue(value)
                self.assertIn("gtk.css", citation)

    def test_citations_cover_the_derived_surfaces(self):
        palette = ui_theme.Palette(accent="#3584e4")
        for key in ("window_bg", "accent", "raised_bg", "hover", "active",
                    "border", "radius"):
            with self.subTest(key=key):
                self.assertIn(key, palette.citations)

    def test_palette_is_deterministic_when_accent_is_pinned(self):
        # The capture harness pins the accent; two runs must agree or the
        # before/after PNGs would differ for a reason nobody can see.
        first = ui_theme.Palette(accent="#3584e4")
        second = ui_theme.Palette(accent="#3584e4")
        self.assertEqual(first.window_bg, second.window_bg)
        self.assertEqual(first.hover, second.hover)
        self.assertEqual(first.border, second.border)


class TestContrastBudget(unittest.TestCase):
    def test_every_pair_meets_its_threshold(self):
        palette = ui_theme.Palette(accent="#3584e4")
        for label, fg, bg, threshold, _kind in palette.pairs():
            with self.subTest(pair=label):
                ratio = ui_theme.contrast_ratio(fg, bg)
                self.assertGreaterEqual(
                    round(ratio, 2), threshold,
                    "%s is %.2f:1, needs %.1f:1" % (label, ratio, threshold))

    def test_contrast_helper_matches_known_values(self):
        # White on black is the 21:1 anchor of the WCAG formula.
        self.assertAlmostEqual(
            ui_theme.contrast_ratio("#ffffff", "#000000"), 21.0, places=2)
        self.assertAlmostEqual(
            ui_theme.contrast_ratio("#ffffff", "#ffffff"), 1.0, places=2)


class TestNoStrayColours(unittest.TestCase):
    def test_no_hex_outside_ui_theme(self):
        offenders = []
        for name in sorted(os.listdir(SRC_DIR)):
            if not name.endswith(".py") or name == "ui_theme.py":
                continue
            path = os.path.join(SRC_DIR, name)
            with open(path, encoding="utf-8") as handle:
                for number, line in enumerate(handle, 1):
                    for match in HEX_LITERAL.finditer(line):
                        offenders.append("%s:%d %s" % (name, number,
                                                       match.group(0)))
        self.assertEqual(
            offenders, [],
            "color literals outside ui_theme.py: %s" % ", ".join(offenders))


if __name__ == "__main__":
    unittest.main()
