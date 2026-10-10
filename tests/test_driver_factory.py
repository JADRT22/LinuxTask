# -*- coding: utf-8 -*-
"""
LinuxTask - test_driver_factory.py
Description: Driver auto-detection tests.
Author: JADRT22 (https://github.com/JADRT22)
License: MIT
"""

import unittest
from unittest.mock import patch
import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../src')))

from drivers.factory import AutoDetectDriver


class TestAutoDetectDriver(unittest.TestCase):
    """Lock the desktop -> driver mapping, especially Sway (issue #4)."""

    def _detect(self, env):
        # start from a clean slate: a stray SWAYSOCK or HYPRLAND signature
        # in the developer's shell must not pick the driver under test.
        clean = {k: v for k, v in os.environ.items()
                 if k not in ("SWAYSOCK", "HYPRLAND_INSTANCE_SIGNATURE",
                              "XDG_CURRENT_DESKTOP", "XDG_SESSION_TYPE")}
        clean.update(env)
        with patch.dict(os.environ, clean, clear=True):
            with patch("drivers.sway.SwayDriver.__init__",
                       return_value=None), \
                 patch("drivers.hyprland.HyprlandDriver.__init__",
                       return_value=None), \
                 patch("drivers.gnome.GnomeDriver.__init__",
                       return_value=None), \
                 patch("drivers.kde_wayland.KdeWaylandDriver.__init__",
                       return_value=None), \
                 patch("drivers.x11.X11Driver.__init__",
                       return_value=None):
                return AutoDetectDriver()

    def test_swaysock_wins_over_desktop_name(self):
        driver = self._detect({
            "SWAYSOCK": "/run/user/1000/sway-ipc.1000.1234.sock",
            "XDG_CURRENT_DESKTOP": "KDE",
            "XDG_SESSION_TYPE": "wayland",
            "DISPLAY": ":0",
        })
        self.assertEqual(type(driver).__name__, "SwayDriver")

    def test_sway_via_xdg_current_desktop(self):
        driver = self._detect({
            "XDG_CURRENT_DESKTOP": "sway:wlroots",
            "XDG_SESSION_TYPE": "wayland",
        })
        self.assertEqual(type(driver).__name__, "SwayDriver")

    def test_hyprland_signature_beats_swaysock(self):
        driver = self._detect({
            "HYPRLAND_INSTANCE_SIGNATURE": "abc123",
            "SWAYSOCK": "/run/user/1000/sway-ipc.sock",
        })
        self.assertEqual(type(driver).__name__, "HyprlandDriver")

    def test_kde_wayland_still_detected(self):
        driver = self._detect({
            "XDG_CURRENT_DESKTOP": "KDE",
            "XDG_SESSION_TYPE": "wayland",
        })
        self.assertEqual(type(driver).__name__, "KdeWaylandDriver")

    def test_gnome_wayland_still_detected(self):
        driver = self._detect({
            "XDG_CURRENT_DESKTOP": "GNOME",
            "XDG_SESSION_TYPE": "wayland",
        })
        self.assertEqual(type(driver).__name__, "GnomeDriver")

    def test_unknown_wayland_desktop_without_display_is_rejected(self):
        with self.assertRaises(RuntimeError):
            self._detect({"XDG_CURRENT_DESKTOP": "NIRI", "DISPLAY": ""})

    def test_unknown_desktop_with_display_falls_back_to_x11(self):
        driver = self._detect({
            "XDG_CURRENT_DESKTOP": "SOMETHING-ELSE",
            "DISPLAY": ":0",
        })
        self.assertEqual(type(driver).__name__, "X11Driver")


if __name__ == '__main__':
    unittest.main()
