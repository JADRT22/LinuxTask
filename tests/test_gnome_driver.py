# -*- coding: utf-8 -*-
"""
LinuxTask - test_gnome_driver.py
Description: headless tests for the GNOME driver's cursor bridge
             (org.linuxtask.cursorbridge extension in
             extensions/gnome-shell/) and the relative-delta fallback.
Author: JADRT22 (https://github.com/JADRT22)
License: MIT
No display, no dbus session bus and no ydotoold are needed: the driver
subclass methods that touch the outside world are patched per test.
"""

import unittest
from unittest.mock import patch

import drivers.gnome as gnome_mod
from drivers.gnome import GnomeDriver


def _make_driver(bridge_ready=False, bridge_mode=None):
    """Builds a GnomeDriver that never touches xrandr/ydotoold/DBus.

    bridge_ready=False leaves the driver exactly as a machine without
    the extension would be: supports_absolute_positioning False.
    """
    def fake_setup(self):
        self._bridge_mode = bridge_mode
        self._bridge_ready = bridge_ready
    with patch.object(GnomeDriver, '_bridge_setup', fake_setup), \
         patch.object(GnomeDriver, '_detect_resolution',
                      lambda self: None), \
         patch.object(GnomeDriver, 'ensure_daemon', lambda self: None):
        driver = GnomeDriver()
    driver.supports_absolute_positioning = bridge_ready
    # Assume a normal single monitor so _clamp keeps real coordinates.
    driver.screen_width, driver.screen_height = 1920, 1080
    return driver


def _no_legacy_read(driver):
    """Kills the xdotool/tkinter fallback chain (this box HAS a desktop,
    so the real chain would return true live coordinates and mask the
    bridge path under test)."""
    return patch.object(GnomeDriver, '_legacy_get_cursor_pos',
                        lambda self: None)


def _gdbus_fake(output=None, fail=True):
    """check_output stub for gdbus mode.

    Returns `output` for every call; with fail=True it raises
    CalledProcessError instead (bridge dead).
    """
    import subprocess
    calls = []

    def _run(cmd, *args, **kwargs):
        calls.append(cmd)
        if fail:
            raise subprocess.CalledProcessError(1, cmd)
        if callable(output):
            return output(cmd)
        return output

    _run.calls = calls
    return _run


class TestBridgeDetection(unittest.TestCase):
    def test_no_bridge_means_relative_mode(self):
        driver = _make_driver()
        self.assertFalse(driver._bridge_ready)
        self.assertFalse(driver.supports_absolute_positioning)

    def test_bridge_ready_means_absolute_mode(self):
        driver = _make_driver(bridge_ready=True, bridge_mode='gdbus')
        self.assertTrue(driver._bridge_ready)
        self.assertTrue(driver.supports_absolute_positioning)

    def test_gdbus_parse(self):
        parse = GnomeDriver._gdbus_parse
        self.assertEqual(parse("(-1, 340)"), [-1, 340])
        self.assertEqual(parse("(857,340)"), [857, 340])
        self.assertIsNone(parse("Error: nothing"))
        self.assertIsNone(parse("()"))


class TestBridgeReads(unittest.TestCase):
    def test_get_cursor_pos_prefers_bridge(self):
        driver = _make_driver(bridge_ready=True, bridge_mode='gdbus')
        stub = _gdbus_fake(b"(857, 340)", fail=False)
        with patch("subprocess.check_output", stub):
            self.assertEqual(driver.get_cursor_pos(), (857, 340))
        self.assertEqual(len(stub.calls), 1)
        self.assertIn("GetPointer", " ".join(stub.calls[0]))

    def test_failed_reads_degrade_then_skip(self):
        driver = _make_driver(bridge_ready=True, bridge_mode='gdbus')
        stub = _gdbus_fake(None, fail=True)
        with patch("subprocess.check_output", stub), \
             _no_legacy_read(driver):
            for _ in range(gnome_mod.BRIDGE_FAIL_SKIP_AFTER):
                self.assertIsNone(driver.get_cursor_pos())
            calls_after_degrade = len(stub.calls)
            self.assertGreater(
                calls_after_degrade, gnome_mod.BRIDGE_FAIL_SKIP_AFTER - 1)
            # Degraded: next reads skip the bridge entirely
            for _ in range(gnome_mod.BRIDGE_SKIP_READS):
                self.assertIsNone(driver.get_cursor_pos())
            self.assertEqual(len(stub.calls), calls_after_degrade)

    def test_position_degrade_fires_warn_once(self):
        driver = _make_driver(bridge_ready=True, bridge_mode='gdbus')
        warnings = []
        driver.warn_fn = warnings.append
        stub = _gdbus_fake(None, fail=True)
        with patch("subprocess.check_output", stub), \
             _no_legacy_read(driver):
            for _ in range(gnome_mod.BRIDGE_FAIL_SKIP_AFTER + 2):
                driver.get_cursor_pos()
        self.assertEqual(len(warnings), 1)
        self.assertIn("bridge", warnings[0])


class TestBridgeWarp(unittest.TestCase):
    def test_move_cursor_warp_calls_bridge(self):
        driver = _make_driver(bridge_ready=True, bridge_mode='gdbus')
        stub = _gdbus_fake(b"(0, 0)", fail=False)
        with patch("subprocess.check_output", stub), \
             patch.object(driver, 'move_relative') as rel:
            driver.move_cursor(857, 340)
        self.assertEqual(len(stub.calls), 1)
        joined = " ".join(stub.calls[0])
        self.assertIn("WarpPoint", joined)
        self.assertIn("857", joined)
        self.assertIn("340", joined)
        rel.assert_not_called()

    def test_warp_degrade_disables_absolute(self):
        driver = _make_driver(bridge_ready=True, bridge_mode='gdbus')
        stub = _gdbus_fake(None, fail=True)
        warnings = []
        driver.warn_fn = warnings.append
        with patch("subprocess.check_output", stub):
            for _ in range(gnome_mod.BRIDGE_FAIL_SKIP_AFTER):
                driver._bridge_warp(100, 100)
        self.assertFalse(driver._bridge_ready)
        self.assertFalse(driver.supports_absolute_positioning)

    def test_move_cursor_delta_fallback_without_bridge(self):
        driver = _make_driver(bridge_ready=False)
        deltas = []
        with patch.object(GnomeDriver, 'get_cursor_pos',
                          lambda self: (10, 20)), \
             patch.object(GnomeDriver, 'move_relative',
                          lambda self, dx, dy: deltas.append((dx, dy)) or True):
            driver._warned.clear()
            driver.move_cursor(857, 340)
        self.assertEqual(deltas, [(847, 320)])


class TestBridgeLayout(unittest.TestCase):
    """#6/#7 on GNOME: the clamp box is the monitor union, not the stage.

    GetScreenSize alone describes a single rectangle anchored at (0, 0), so
    a monitor placed above or left of the primary one had its coordinates
    folded back onto it. GetLayout returns [x, y, w, h] of the union.
    """

    def _detect(self, replies, bridge_ready=True):
        driver = _make_driver(bridge_ready=bridge_ready, bridge_mode='dbus')

        def fake_call(self, method, args, timeout):
            return replies.get(method)

        with patch.object(GnomeDriver, '_bridge_call', fake_call):
            driver._detect_resolution()
        return driver

    def test_negative_origin_is_kept(self):
        driver = self._detect({
            'GetScreenSize': (2560, 1440),
            'GetLayout': (0, -180, 4480, 1620),
        })
        self.assertEqual((driver.screen_width, driver.screen_height),
                         (2560, 1440))
        self.assertEqual(driver.bounds, (0, -180, 4480, 1440))
        self.assertEqual(driver._clamp(4000, 700), (4000, 700))
        self.assertEqual(driver._clamp(-5, -181), (0, -180))
        self.assertEqual(driver._clamp(9999, 9999), (4479, 1439))

    def test_old_bridge_without_getlayout_keeps_the_stage_box(self):
        """GetLayout is unknown there: degrade to the previous behaviour."""
        driver = self._detect({'GetScreenSize': (1920, 1080),
                               'GetLayout': None})
        self.assertEqual(driver.bounds, (0, 0, 1920, 1080))

    def test_garbage_layout_is_ignored(self):
        for reply in ((0, 0, 0, 0), ('a', 'b', 'c', 'd'), (1, 1, 1), ()):
            driver = self._detect({'GetScreenSize': (1920, 1080),
                                   'GetLayout': reply})
            self.assertEqual(driver.bounds, (0, 0, 1920, 1080),
                             "bad GetLayout reply %r changed the box"
                             % (reply,))

    def test_xrandr_fallback_sets_a_real_box(self):
        """No bridge: bounds must still be a tuple, not None."""
        driver = _make_driver(bridge_ready=False)
        listing = (b'Screen 0: minimum 320 x 200, current 3840 x 1080\n'
                   b'  1920x1080 60.00*+\n')
        with patch('subprocess.check_output',
                   return_value=listing):
            driver._detect_resolution()
        self.assertEqual((driver.screen_width, driver.screen_height),
                         (1920, 1080))
        self.assertEqual(driver.bounds, (0, 0, 1920, 1080))

    def test_everything_failing_falls_back(self):
        driver = _make_driver(bridge_ready=False)
        import subprocess as _sp
        with patch('subprocess.check_output',
                   side_effect=_sp.CalledProcessError(1, 'x')):
            driver._detect_resolution()
        self.assertEqual(driver.bounds, (0, 0, 1920, 1080))


if __name__ == '__main__':
    unittest.main()
