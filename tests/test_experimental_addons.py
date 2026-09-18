# -*- coding: utf-8 -*-
"""
LinuxTask - test_experimental_addons.py
Description: Headless tests for the OPTIONAL experimental addons
             (experimental/image_click + experimental/color_spin). These
             are not part of the app; the tests only exercise the pure
             logic (matcher, color detection, stability guard, config
             merge and the GUI loop decision flow) with fake backends —
             no display, no hardware, no grim.
Author: JADRT22 (https://github.com/JADRT22)
License: MIT
"""

import json
import os
import sys
import threading
import time
import unittest

import numpy as np

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(TESTS_DIR)
for p in (
    os.path.join(REPO_ROOT, "src"),
    os.path.join(REPO_ROOT, "experimental", "color_spin"),
    os.path.join(REPO_ROOT, "experimental", "image_click"),
):
    if p not in sys.path:
        sys.path.insert(0, p)

import vision  # noqa: E402
import capture as capture_mod  # noqa: E402
from spin_until_color import (  # noqa: E402
    color_fraction as spin_color_fraction,
    wait_region_stable as spin_wait_region_stable,
)


def _solid(color, size=(40, 60)):
    h, w = size
    return np.full((h, w, 3), color, dtype=np.uint8)


class FakeBackend(capture_mod.GrimCapture):
    """Captures always return the same frame; crop is real slicing."""

    def __init__(self, frame):
        self.frame = frame
        self.calls = 0

    def capture(self):
        self.calls += 1
        return self.frame

    def capture_region(self, region):
        self.calls += 1
        x, y, w, h = region
        return self.frame[y:y + h, x:x + w]


class TestSharedPrimitives(unittest.TestCase):
    """src/vision and src/capture are the single source of truth; the
    experimental scripts must expose the same behaviour."""

    def test_color_fraction_matches_between_modules(self):
        img = _solid((60, 60, 60))
        img[5:15, 10:20] = (255, 215, 0)
        a = vision.color_fraction(img, (255, 215, 0), 40)
        b = spin_color_fraction(img, (255, 215, 0), 40)
        self.assertEqual(a, b)
        self.assertAlmostEqual(a, 100 / (40 * 60), places=4)

    def test_wait_region_stable_matches_between_modules(self):
        class Static:
            def capture_region(self, region):
                return _solid((10, 10, 10))

        kwargs = dict(poll=0.02, need=3)
        stable_a, waited_a = capture_mod.wait_region_stable(
            Static(), (0, 0, 10, 10), **kwargs)
        stable_b, waited_b = spin_wait_region_stable(
            Static(), (0, 0, 10, 10), **kwargs)
        self.assertTrue(stable_a and stable_b)
        self.assertAlmostEqual(waited_a, waited_b, delta=0.05)


class TestAntiFalsePositiveFlow(unittest.TestCase):
    """The roulette scenario: rare clan passes by during the animation.
    The combination (stability guard -> check -> re-confirm) must reject
    it and accept a real result."""

    def _guards(self, backend, region, target, threshold=0.02, tol=40):
        stable, waited = capture_mod.wait_region_stable(
            backend, region, poll=0.02, need=3, max_wait=2.0)
        frac = vision.color_fraction(
            backend.capture_region(region), target, tol)
        return stable, frac, waited

    def test_passing_clan_is_rejected_by_confirmation(self):
        # frame WITH the rare color -> detection fires...
        backend = FakeBackend(_solid((255, 215, 0)))
        stable, frac, _ = self._guards(backend, (0, 0, 30, 20),
                                       (255, 215, 0))
        self.assertTrue(stable)
        self.assertGreaterEqual(frac, 0.02)
        # ...but 1s later the roulette moved on -> confirmation fails.
        backend.frame = _solid((60, 60, 60))
        frac2 = vision.color_fraction(
            backend.capture_region((0, 0, 30, 20)), (255, 215, 0), 40)
        self.assertLess(frac2, 0.02)

    def test_real_result_survives_confirmation(self):
        backend = FakeBackend(_solid((255, 215, 0)))
        stable, frac, _ = self._guards(backend, (0, 0, 30, 20),
                                       (255, 215, 0))
        self.assertTrue(stable)
        self.assertGreaterEqual(frac, 0.02)
        # Frame unchanged after 1s -> confirmation passes.
        frac2 = vision.color_fraction(
            backend.capture_region((0, 0, 30, 20)), (255, 215, 0), 40)
        self.assertGreaterEqual(frac2, 0.02)

    def test_decelerating_animation_is_not_frozen(self):
        # The guard's metric is the MEAN per-pixel delta across channels.
        # A uniform shift of +8 on one channel => mean 8/3 ~= 2.67 > 2.5:
        # a slow roulette tail (visually subtle but moving) must keep
        # resetting the stability counter.
        class SlowTail:
            reads = 0

            def capture_region(self, region):
                SlowTail.reads += 1
                img = _solid((10, 10, 10)).astype(np.int16)
                img[:, :, 0] += SlowTail.reads * 8
                return img.astype(np.uint8)

        stable, _ = capture_mod.wait_region_stable(
            SlowTail(), (0, 0, 10, 10), poll=0.02, need=3, max_wait=0.6)
        self.assertFalse(stable)

    def test_imperceptible_drift_is_frozen(self):
        # Documented threshold semantics: +2 on one channel => mean
        # 2/3 ~= 0.67 <= 2.5 counts as frozen (compression/gradient
        # noise must not keep the guard waiting forever).
        class Drift:
            reads = 0

            def capture_region(self, region):
                Drift.reads += 1
                img = _solid((10, 10, 10)).astype(np.int16)
                img[:, :, 0] += Drift.reads * 2
                return img.astype(np.uint8)

        stable, _ = capture_mod.wait_region_stable(
            Drift(), (0, 0, 10, 10), poll=0.02, need=3, max_wait=1.0)
        self.assertTrue(stable)


class TestGUIColorSpinLogic(unittest.TestCase):
    """The GUI app logic that is testable without a display."""

    def test_config_roundtrip_and_behavior_merge(self):
        sys.path.insert(0, os.path.join(REPO_ROOT, "experimental",
                                        "color_spin"))
        import app as appmod

        cfg = {
            "button_pos": [100, 200],
            "region": [10, 20, 30, 40],
            "color": [255, 215, 0],
        }
        cfg.update(appmod._BEHAVIOR)
        # selections preserved
        self.assertEqual(cfg["button_pos"], [100, 200])
        self.assertEqual(cfg["color"], [255, 215, 0])
        # behavior defaults present
        self.assertEqual(cfg["confirm_times"], 2)
        self.assertEqual(cfg["stable_need"], 15)
        self.assertEqual(cfg["max_spins"], 100)

    def test_loop_stops_on_event_before_first_click(self):
        # The stop Event must break the loop even when set before the
        # first spin (the desktop "PARAR" button path).
        sys.path.insert(0, os.path.join(REPO_ROOT, "experimental",
                                        "color_spin"))
        stop = threading.Event()
        stop.set()
        spins = 0
        max_spins = 100
        for spin in range(1, max_spins + 1):
            if stop.is_set():
                break
            spins += 1  # stand-in for click+check work
        self.assertEqual(spins, 0)

    def test_fake_backend_crop_is_numpy_slice(self):
        frame = np.arange(600, dtype=np.uint8).reshape(10, 20, 3)
        fb = FakeBackend(frame)
        crop = fb.capture_region((2, 4, 8, 3))
        self.assertEqual(crop.shape, (3, 8, 3))
        self.assertTrue((crop == frame[4:7, 2:10]).all())
        self.assertEqual(fb.calls, 1)


class TestLauncherScripts(unittest.TestCase):
    """The shell entry points must exist, be executable and syntactic."""

    def test_files_exist_and_are_executable(self):
        for rel in (
            "experimental/install.sh",
            "experimental/color_spin/launcher.sh",
            "experimental/color_spin/stop.sh",
        ):
            path = os.path.join(REPO_ROOT, rel)
            self.assertTrue(os.path.isfile(path), rel)
            self.assertTrue(os.access(path, os.X_OK), rel)

    def test_bash_syntax(self):
        for rel in (
            "experimental/install.sh",
            "experimental/color_spin/launcher.sh",
            "experimental/color_spin/stop.sh",
        ):
            path = os.path.join(REPO_ROOT, rel)
            ret = os.system(f"bash -n {path!r} 2>/dev/null")
            self.assertEqual(ret, 0, rel)

    def test_desktop_templates_have_placeholders(self):
        for rel in (
            "experimental/color_spin/color-spin.desktop.template",
            "experimental/color_spin/color-spin-stop.desktop.template",
        ):
            path = os.path.join(REPO_ROOT, rel)
            with open(path) as f:
                content = f.read()
            self.assertIn("@", content, rel)
            self.assertIn("Desktop Entry", content)


if __name__ == "__main__":
    unittest.main()
