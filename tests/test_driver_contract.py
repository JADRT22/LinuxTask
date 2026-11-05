# -*- coding: utf-8 -*-
"""
LinuxTask - test_driver_contract.py
Description: Contract tests for the DesktopManager driver surface. These
             assert the shape every driver must keep (bool-returning
             move_cursor, clamping inside the detected layout box) without
             touching a compositor: each driver runs against mocked
             subprocess/D-Bus/Xlib, the same way its own suite does.
Author: JADRT22 (https://github.com/JADRT22)
License: MIT
"""

import json
import unittest
from unittest.mock import MagicMock, patch

from drivers.base import FALLBACK_RESOLUTION, DesktopManager


class TestMoveCursorContract(unittest.TestCase):
    """A driver must answer True/False, never None (see base.py).

    playback.py decides whether to fall back to the UInput warp with
    `if move_cursor(...) is False`. A driver returning None made that
    comparison never fire, so an absolute macro was silently dropped
    instead of being replayed through the virtual device.
    """

    def assert_bool(self, result, label):
        self.assertIsInstance(
            result, bool,
            "%s must return bool from move_cursor, got %r" % (label, result))

    @patch('drivers.x11.Display')
    def test_x11_success_and_failure(self, mock_display_cls):
        from drivers.x11 import X11Driver
        display = MagicMock()
        screen = MagicMock()
        screen.width_in_pixels = 1920
        screen.height_in_pixels = 1080
        screen.root = MagicMock()
        display.screen.return_value = screen
        mock_display_cls.return_value = display

        driver = X11Driver()
        self.assert_bool(driver.move_cursor(10, 10), "X11Driver")
        self.assertTrue(driver.move_cursor(10, 10))

        display.xtest_fake_input.side_effect = RuntimeError("X connection lost")
        result = driver.move_cursor(10, 10)
        self.assert_bool(result, "X11Driver")
        self.assertFalse(result)

    @patch('drivers.hyprland.subprocess.run')
    @patch('drivers.hyprland.subprocess.check_output')
    def test_hyprland_success_and_failure(self, mock_output, mock_run):
        from drivers.hyprland import HyprlandDriver
        mock_output.return_value = b'[]'
        mock_run.return_value = MagicMock(stdout="ok\n", returncode=0)
        driver = HyprlandDriver()
        result = driver.move_cursor(10, 10)
        self.assert_bool(result, "HyprlandDriver")
        self.assertTrue(result)

        # Both dispatch forms refused -> the warp is reported as failed.
        mock_run.side_effect = FileNotFoundError("hyprctl not found")
        result = driver.move_cursor(10, 10)
        self.assert_bool(result, "HyprlandDriver")
        self.assertFalse(result)

    def test_sway_success_and_failure(self):
        from drivers.sway import SwayDriver
        with patch.object(SwayDriver, '_command', return_value=[
                {"name": "seat0"}]), \
                patch.object(SwayDriver, '_detect_seat',
                             return_value="seat0"):
            driver = SwayDriver.__new__(SwayDriver)
            DesktopManager.__init__(driver)
            driver.swaymsg_path = "/usr/bin/swaymsg"
            driver._seat = "seat0"
            driver.screen_width, driver.screen_height = FALLBACK_RESOLUTION
            driver.bounds = None

        driver._seat_cmd = MagicMock(return_value=True)
        result = driver.move_cursor(10, 10)
        self.assert_bool(result, "SwayDriver")
        self.assertTrue(result)

        driver._seat_cmd = MagicMock(return_value=False)
        result = driver.move_cursor(10, 10)
        self.assert_bool(result, "SwayDriver")
        self.assertFalse(result)

    def test_gnome_success_and_failure(self):
        from drivers.gnome import GnomeDriver
        driver = GnomeDriver.__new__(GnomeDriver)
        DesktopManager.__init__(driver)
        driver.screen_width, driver.screen_height = FALLBACK_RESOLUTION
        driver.bounds = None
        driver._bridge_ready = True
        driver._bridge_warp_fail_count = 0
        driver._warned = set()
        driver.warn_fn = None

        driver._bridge_warp = MagicMock(return_value=True)
        result = driver.move_cursor(10, 10)
        self.assert_bool(result, "GnomeDriver")
        self.assertTrue(result)

        # Bridge refuses and the position cannot be read: the legacy
        # relative emulation cannot run either, so playback must be told.
        driver._bridge_warp = MagicMock(return_value=False)
        driver.get_cursor_pos = MagicMock(return_value=None)
        result = driver.move_cursor(10, 10)
        self.assert_bool(result, "GnomeDriver")
        self.assertFalse(result)

        driver._bridge_warp = MagicMock(return_value=False)
        driver.get_cursor_pos = MagicMock(return_value=(1, 1))
        driver.move_relative = MagicMock(return_value=True)
        self.assertTrue(driver.move_cursor(10, 10))
        driver.move_relative = MagicMock(return_value=False)
        self.assertFalse(driver.move_cursor(10, 10))

    def test_kde_wayland_reports_refusal(self):
        from drivers.kde_wayland import KdeWaylandDriver
        driver = KdeWaylandDriver.__new__(KdeWaylandDriver)
        DesktopManager.__init__(driver)
        driver.warn_fn = None
        driver._warned = set()
        driver._portal_ready = False
        # Portal not ready is the refusal path the fallback exists for.
        self.assertFalse(driver.move_cursor(10, 10))


class TestClampContract(unittest.TestCase):
    """_clamp must keep coordinates inside the detected layout box."""

    class _Driver(DesktopManager):
        def get_cursor_pos(self):
            return (0, 0)

        def move_cursor(self, x, y):
            return True

        def move_relative(self, dx, dy):
            return True

    def setUp(self):
        self.driver = self._Driver()
        self.driver.set_screen_size(1920, 1080)

    def test_single_output_clamps_to_the_primary_box(self):
        self.assertEqual(self.driver._clamp(-50, 2000), (0, 1079))
        self.assertEqual(self.driver._clamp(5000, 500), (1919, 500))

    def test_layout_box_allows_negative_origins(self):
        """A monitor placed left/above the origin has negative coordinates."""
        self.driver.set_screen_size(1920, 1080, (-2560, -1440, 1920, 1080))
        self.assertEqual(self.driver._clamp(-3000, -2000), (-2560, -1440))
        self.assertEqual(self.driver._clamp(5000, 4000), (1919, 1079))

    def test_zero_sized_detection_keeps_the_fallback_box(self):
        """A failed detection must not collapse every coordinate to (0, 0)."""
        self.driver.screen_width = 0
        self.driver.screen_height = 0
        self.driver.bounds = None
        # Inside the 1920x1080 fallback box: unchanged, not pinned to the
        # top-left corner the way a zero-sized box clamped it.
        self.assertEqual(self.driver._clamp(400, 300), (400, 300))
        self.assertEqual(self.driver._clamp(5000, 5000),
                         (FALLBACK_RESOLUTION[0] - 1,
                          FALLBACK_RESOLUTION[1] - 1))

    def test_degenerate_bounds_fall_back_to_the_primary_box(self):
        self.driver.bounds = (500, 500, 10, 10)  # max <= min: unusable
        self.assertEqual(self.driver._layout_box(), (0, 0, 1920, 1080))


class TestHyprlandLayoutBounds(unittest.TestCase):
    """Multi-monitor: the clamp box is the union of every output (#6, #7)."""

    @patch('drivers.hyprland.subprocess.check_output')
    def test_union_of_two_monitors(self, mock_output):
        from drivers.hyprland import HyprlandDriver
        mock_output.return_value = json.dumps([
            {"name": "eDP-1", "x": 0, "y": 0, "width": 1920, "height": 1080,
             "focused": True},
            {"name": "HDMI-A-1", "x": 1920, "y": -180, "width": 2560,
             "height": 1440, "focused": False},
        ]).encode()

        driver = HyprlandDriver()
        self.assertEqual((driver.screen_width, driver.screen_height),
                         (1920, 1080))
        self.assertEqual(driver.bounds, (0, -180, 4480, 1260))
        # A point on the second monitor must survive the clamp.
        self.assertEqual(driver._clamp(3000, 700), (3000, 700))

    @patch('drivers.hyprland.subprocess.check_output')
    def test_missing_geometry_keeps_primary_only_box(self, mock_output):
        from drivers.hyprland import HyprlandDriver
        # Older hyprctl payloads without x/y: size is known, layout is not.
        mock_output.return_value = json.dumps([
            {"name": "eDP-1", "width": 2560, "height": 1440, "focused": True},
        ]).encode()

        driver = HyprlandDriver()
        self.assertEqual(driver.bounds, (0, 0, 2560, 1440))

    @patch('drivers.hyprland.subprocess.check_output')
    def test_disabled_output_is_excluded(self, mock_output):
        """hyprctl lists disabled outputs too, with their stale geometry."""
        from drivers.hyprland import HyprlandDriver
        mock_output.return_value = json.dumps([
            {"name": "eDP-1", "x": 0, "y": 0, "width": 1920, "height": 1080,
             "focused": True, "disabled": False},
            {"name": "DP-3", "x": 1920, "y": 0, "width": 3840, "height": 2160,
             "focused": False, "disabled": True},
        ]).encode()

        driver = HyprlandDriver()
        self.assertEqual(driver.bounds, (0, 0, 1920, 1080))

    @patch('drivers.hyprland.subprocess.check_output')
    def test_junk_entry_does_not_abort_detection(self, mock_output):
        from drivers.hyprland import HyprlandDriver
        mock_output.return_value = json.dumps([
            "not-a-monitor",
            {"name": "eDP-1", "x": 0, "y": 0, "width": 1920, "height": 1080,
             "focused": True},
        ]).encode()

        driver = HyprlandDriver()
        self.assertEqual(driver.bounds, (0, 0, 1920, 1080))


class TestSwayLayoutBounds(unittest.TestCase):
    """Sway reports each output's rect, so the layout box is computable."""

    def _driver_with_outputs(self, outputs):
        from drivers.sway import SwayDriver
        with patch.object(SwayDriver, '_detect_seat', return_value="seat0"), \
                patch.object(SwayDriver, '_detect_resolution'):
            driver = SwayDriver.__new__(SwayDriver)
            DesktopManager.__init__(driver)
            driver.swaymsg_path = "/usr/bin/swaymsg"
            driver._seat = "seat0"
        with patch.object(driver, '_command', return_value=outputs):
            driver._detect_resolution()
        return driver

    def test_union_of_enabled_outputs(self):
        driver = self._driver_with_outputs([
            {"name": "eDP-1", "focused": True, "enabled": True,
             "rect": {"x": 0, "y": 0, "width": 1920, "height": 1080},
             "current_mode": {"width": 1920, "height": 1080}},
            {"name": "HDMI-A-1", "focused": False, "enabled": True,
             "rect": {"x": -2560, "y": 0, "width": 2560, "height": 1440},
             "current_mode": {"width": 2560, "height": 1440}},
        ])
        self.assertEqual(driver.bounds, (-2560, 0, 1920, 1440))
        self.assertEqual(driver._clamp(-2000, 1200), (-2000, 1200))

    def test_disabled_outputs_are_ignored(self):
        driver = self._driver_with_outputs([
            {"name": "eDP-1", "focused": True, "enabled": True,
             "rect": {"x": 0, "y": 0, "width": 1920, "height": 1080},
             "current_mode": {"width": 1920, "height": 1080}},
            {"name": "HDMI-A-1", "focused": False, "enabled": False,
             "rect": {"x": 1920, "y": 0, "width": 3840, "height": 2160},
             "current_mode": {"width": 3840, "height": 2160}},
        ])
        self.assertEqual(driver.bounds, (0, 0, 1920, 1080))


if __name__ == '__main__':
    unittest.main()
