# -*- coding: utf-8 -*-
"""
LinuxTask - test_kde_wayland_driver.py
Description: Headless tests for the KDE Wayland portal driver (portal and
             DBus init mocked out): clicks must reach the portal as evdev
             button codes 272/273/274, per the RemoteDesktop portal spec.
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


if __name__ == '__main__':
    unittest.main()
