# -*- coding: utf-8 -*-
"""
LinuxTask - test_input_devices.py
Description: Unit tests for LinuxTaskApp.get_input_devices() in src/main.py.
             Covers the python-evdev 2.x behavior change: list_devices()
             only returns readable+WRITABLE devices by default, while the
             project udev rule grants event* READ-ONLY on purpose. No display
             or hardware required (mocked evdev).
Author: JADRT22 (https://github.com/JADRT22)
License: MIT
"""

import os
import sys
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../src')))

import main  # noqa: E402  (imports customtkinter/evdev, but no display touched)


def make_app():
    """Builds a bare LinuxTaskApp without running CTk.__init__ (no display)."""
    return main.LinuxTaskApp.__new__(main.LinuxTaskApp)


class TestGetInputDevices(unittest.TestCase):
    def test_readonly_devices_listed(self):
        """evdev >= 2.0 path: readable-only devices must be requested."""
        app = make_app()
        with patch.object(main.evdev, "list_devices",
                          return_value=["/dev/input/event0"]) as mock_list, \
             patch.object(main.evdev, "InputDevice",
                          return_value=MagicMock()):
            devices = app.get_input_devices()
        mock_list.assert_called_once_with(writable=False)
        self.assertEqual(len(devices), 1)

    def test_old_evdev_without_kwarg(self):
        """evdev 1.x path: list_devices() takes no kwarg, fall back."""
        app = make_app()

        def fake_list(*args, **kwargs):
            if kwargs:
                raise TypeError("list_devices() takes no keyword arguments")
            return ["/dev/input/event1"]

        with patch.object(main.evdev, "list_devices",
                          side_effect=fake_list), \
             patch.object(main.evdev, "InputDevice",
                          return_value=MagicMock()):
            devices = app.get_input_devices()
        self.assertEqual(len(devices), 1)

    def test_unreadable_device_skipped(self):
        """A device that cannot be opened is skipped, not fatal."""
        app = make_app()
        with patch.object(main.evdev, "list_devices",
                          return_value=["/dev/input/event9"]), \
             patch.object(main.evdev, "InputDevice",
                          side_effect=PermissionError(13, "denied")):
            devices = app.get_input_devices()
        self.assertEqual(devices, [])

class TestOwnVirtualDeviceSkipped(unittest.TestCase):
    def test_own_uinput_device_excluded(self):
        """Replayed events must not be read back (uinput echo)."""
        app = make_app()
        fake_uinput = MagicMock()
        fake_uinput.name = "LinuxTask-Virtual"
        app.uinput_device = fake_uinput

        own_dev = MagicMock()
        own_dev.name = "LinuxTask-Virtual"
        real_dev = MagicMock()
        real_dev.name = "AT Translated Set 2 keyboard"

        def fake_input(path):
            return {"event99": own_dev, "event0": real_dev}[path]

        with patch.object(main.evdev, "list_devices",
                          return_value=["event99", "event0"]), \
             patch.object(main.evdev, "InputDevice",
                          side_effect=fake_input):
            devices = app.get_input_devices()
        self.assertEqual(devices, [real_dev])

    def test_no_filter_without_uinput(self):
        """No virtual device -> everything listed, no crash on bare app."""
        app = make_app()  # __new__: no uinput_device attr at all
        dev = MagicMock()
        dev.name = "Logitech USB Receiver"
        with patch.object(main.evdev, "list_devices",
                          return_value=["event5"]), \
             patch.object(main.evdev, "InputDevice",
                          return_value=dev):
            devices = app.get_input_devices()
        self.assertEqual(devices, [dev])



if __name__ == "__main__":
    unittest.main()
