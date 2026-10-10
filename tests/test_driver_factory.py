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
import types

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../src')))

from drivers.factory import AutoDetectDriver

# Every module the factory can import, with the class it exposes.
DRIVER_MODULES = {
    "drivers.sway": "SwayDriver",
    "drivers.hyprland": "HyprlandDriver",
    "drivers.gnome": "GnomeDriver",
    "drivers.kde_wayland": "KdeWaylandDriver",
    "drivers.x11": "X11Driver",
}


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
            with patch.dict(sys.modules, self._stubbed_modules()):
                with patch("drivers.factory._ensure_importable"):
                    return AutoDetectDriver()

    def _stubbed_modules(self):
        """Builds stand-ins for every driver module.

        No real driver module is imported: drivers.kde_wayland needs
        dbus-python and PyGObject at import time, which CI does not have.
        Only the class each factory branch returns matters, so one stub
        per module is enough.
        """
        stubs = {}
        for module_name, class_name in DRIVER_MODULES.items():
            stub = types.ModuleType(module_name)
            setattr(stub, class_name,
                    type(class_name, (), {"__init__": lambda self: None}))
            stubs[module_name] = stub
        return stubs

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
