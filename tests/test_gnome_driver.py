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
import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../src')))

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


if __name__ == '__main__':
    unittest.main()
