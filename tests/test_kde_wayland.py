# -*- coding: utf-8 -*-
"""
LinuxTask - test_kde_wayland.py
Description: Headless tests for the KDE Wayland portal driver (portal and
             DBus init mocked out): clicks must reach the portal as evdev
             button codes 272/273/274, per the RemoteDesktop portal spec,
             and skipped input must surface as WARNING + a UI notice.
Author: JADRT22 (https://github.com/JADRT22)
License: MIT
"""

import os
import sys
import unittest
from unittest.mock import MagicMock, patch

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../src')))

from drivers.kde_wayland import BTN_MAP, KdeWaylandDriver  # noqa: E402


def make_driver(portal_ready=True):
    """Driver with DBus/portal init patched out and a mock portal."""
    with patch.object(KdeWaylandDriver, '_detect_resolution'), \
            patch.object(KdeWaylandDriver, '_portal_init'):
        driver = KdeWaylandDriver()
    driver._portal = MagicMock()
    driver._portal_ready = portal_ready
    driver._session_handle = "/org/freedesktop/portal/desktop/session/1"
    return driver


class TestKdeWaylandButtons(unittest.TestCase):

    def test_map_is_evdev_codes(self):
        self.assertEqual(BTN_MAP, {272: 272, 273: 273, 274: 274})

    def test_mouse_button_sends_evdev_code_to_portal(self):
        driver = make_driver()
        for code in (272, 273, 274):
            self.assertTrue(driver.mouse_button(code, True))
            args = driver._portal.NotifyPointerButton.call_args.args
            self.assertEqual(args[2], code, "portal must get the evdev code")
            self.assertEqual(args[3], 1)
        self.assertTrue(driver.mouse_button(272, False))
        self.assertEqual(
            driver._portal.NotifyPointerButton.call_args.args[3], 0)

    def test_unknown_button_is_declined(self):
        driver = make_driver()
        self.assertFalse(driver.mouse_button(999, True))
        driver._portal.NotifyPointerButton.assert_not_called()

    def test_portal_not_ready_warns_and_declines(self):
        driver = make_driver(portal_ready=False)
        with self.assertLogs('drivers.kde_wayland', level='WARNING') as logs:
            self.assertFalse(driver.mouse_button(272, True))
            self.assertFalse(driver.move_cursor(10, 20))
            self.assertFalse(driver.move_relative(1, 1))
            self.assertFalse(driver.scroll('down'))
        self.assertTrue(any('not ready' in m for m in logs.output))
        driver._portal.NotifyPointerButton.assert_not_called()

    def test_failed_portal_call_warns_and_declines(self):
        driver = make_driver()
        driver._portal.NotifyPointerButton.side_effect = RuntimeError('boom')
        with self.assertLogs('drivers.kde_wayland', level='WARNING') as logs:
            self.assertFalse(driver.mouse_button(272, True))
        self.assertTrue(any('failed' in m for m in logs.output))

    def test_warns_only_once_per_reason(self):
        driver = make_driver(portal_ready=False)
        with self.assertLogs('drivers.kde_wayland', level='WARNING') as logs:
            driver.mouse_button(272, True)
        self.assertEqual(len(logs.output), 1)
        # Repeats are demoted to DEBUG so long macros do not flood the log.
        with self.assertLogs('drivers.kde_wayland', level='DEBUG') as logs2:
            driver.mouse_button(272, True)
        self.assertEqual(len(logs2.output), 1)


class TestKdeWaylandVisibility(unittest.TestCase):
    """Skip points must log a WARNING and register one UI notice."""

    def test_portal_not_ready_warns_and_registers_ui_notice(self):
        driver = make_driver(portal_ready=False)
        notices = []
        driver.warn_fn = notices.append
        with self.assertLogs('drivers.kde_wayland', level='WARNING') as logs:
            self.assertFalse(driver.move_cursor(10, 20))
        self.assertTrue(any('not ready' in m for m in logs.output))
        self.assertEqual(len(notices), 1)
        self.assertIn('not ready', notices[0])
        # Repeats of the same reason must not queue another notice.
        self.assertFalse(driver.move_cursor(30, 40))
        self.assertEqual(len(notices), 1)

    def test_failed_mouse_call_warns_and_registers_ui_notice(self):
        driver = make_driver()
        driver._portal.NotifyPointerButton.side_effect = RuntimeError('boom')
        notices = []
        driver.warn_fn = notices.append
        with self.assertLogs('drivers.kde_wayland', level='WARNING') as logs:
            self.assertFalse(driver.mouse_button(272, True))
        self.assertTrue(any('failed' in m for m in logs.output))
        self.assertEqual(len(notices), 1)
        self.assertIn('failed', notices[0])


if __name__ == '__main__':
    unittest.main()
