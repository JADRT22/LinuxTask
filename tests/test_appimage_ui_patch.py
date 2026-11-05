# -*- coding: utf-8 -*-
"""
LinuxTask - test_appimage_ui_patch.py
Description: Guards the AppImage staging patch. build.sh rewrites the toolbar
             labels of the staged main.py before bundling; those anchors are
             plain strings from the UI source and used to rot silently (the
             font line grew a width= argument and the build died at staging
             with no test able to see it). Here the anchors are checked
             against the real src/main.py, and the patched output is
             compiled and verified to be ASCII-only for the labels.
Author: JADRT22 (https://github.com/JADRT22)
License: MIT
"""

import ast
import os
import sys
import unittest

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, os.path.join(REPO, 'tools', 'appimage'))

import patch_ui

MAIN_PY = os.path.join(REPO, 'src', 'main.py')
BUILD_SH = os.path.join(REPO, 'tools', 'appimage', 'build.sh')


def source():
    with open(MAIN_PY, encoding='utf-8') as fh:
        return fh.read()


class TestAnchorsMatchSource(unittest.TestCase):
    """Every pattern has to exist in main.py, or staging must fail."""

    def test_all_label_patterns_are_present(self):
        src = source()
        missing = [old for old, _ in patch_ui.ASCII_SUBS if old not in src]
        self.assertEqual(
            missing, [],
            "src/main.py no longer contains the staged label patterns: %s"
            % ', '.join(missing))

    def test_font_anchor_matches_the_current_line(self):
        self.assertIsNotNone(patch_ui.FONT_ANCHOR.search(source()))

    def test_font_anchor_survives_extra_keyword_arguments(self):
        """Regression: the line grew ', width=40' and broke an exact match."""
        line = '        self.btns[1].configure(font=("DejaVu Sans", 10), width=40)\n'
        self.assertIsNotNone(patch_ui.FONT_ANCHOR.search(line))


class TestPatchedOutput(unittest.TestCase):

    def setUp(self):
        self.patched = patch_ui.patch_source(source())

    def test_symbols_are_gone_from_the_widget_labels(self):
        for glyph in ('●', '▶', '↻', '⚙', '■'):
            self.assertNotIn('text="%s"' % glyph, self.patched)

    def test_ascii_labels_are_used(self):
        for label in ('"REC"', '"PLAY"', '"LOOP"', '"SET"', '"STOP"'):
            self.assertIn(label, self.patched)

    def test_font_loop_is_inserted_after_the_anchor(self):
        marker = ('self.btns[1].configure(font=("DejaVu Sans", 10)')
        index = self.patched.index(marker)
        tail = self.patched[index:index + 400]
        self.assertIn('for b in self.btns[2:5]:', tail)
        self.assertIn('b.configure(font=("DejaVu Sans", 10))', tail)

    def test_inserted_lines_keep_the_method_indentation(self):
        """Patching a class body with the wrong indent is a syntax error."""
        for line in self.patched.splitlines():
            if 'for b in self.btns[2:5]:' in line:
                self.assertEqual(len(line) - len(line.lstrip()), 8)
                break
        else:
            self.fail('font loop not inserted')

    def test_patched_source_still_parses(self):
        ast.parse(self.patched)

    def test_patch_is_idempotent_on_labels(self):
        """A second pass must not find the patterns it just replaced."""
        with self.assertRaises(ValueError):
            patch_ui.patch_source(self.patched)


class TestPatchFailureIsLoud(unittest.TestCase):

    # All seven label patterns, and deliberately no font anchor line.
    LABELS_ONLY = (
        'buttons = [("●", 1), ("▶", 2), ("↻", 3)]\n'
        'a.configure(text="⚙")\n'
        'b.configure(text="▶")\n'
        'c.configure(text="■")\n'
        'd.configure(text="●")\n'
        'e.configure(text="↻")\n'
    )

    def test_loop_state_change_is_patched(self):
        """toggle_loop() repaints the glyph; tofu came back on first click."""
        patched = patch_ui.patch_source(source())
        self.assertNotIn('text="↻"', patched)
        self.assertIn('text="LOOP"', patched)

    def test_missing_label_raises(self):
        with self.assertRaises(ValueError) as ctx:
            patch_ui.patch_source('text="⚙"\n')
        self.assertIn('●', str(ctx.exception))

    def test_missing_font_anchor_raises(self):
        with self.assertRaises(ValueError) as ctx:
            patch_ui.patch_source(self.LABELS_ONLY)
        self.assertIn('font anchor', str(ctx.exception))


class TestBuildScriptUsesTheModule(unittest.TestCase):
    """build.sh must call patch_ui.py, not re-inline a heredoc nobody tests."""

    def test_staging_calls_the_patch_module(self):
        with open(BUILD_SH, encoding='utf-8') as fh:
            text = fh.read()
        self.assertIn('tools/appimage/patch_ui.py', text)
        self.assertNotIn("'(\"●\",', '(\"REC\",')", text)


if __name__ == '__main__':
    unittest.main()
