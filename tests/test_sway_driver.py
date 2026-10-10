# -*- coding: utf-8 -*-
"""
LinuxTask - test_sway_driver.py
Description: Unit tests for the Sway driver.
Author: JADRT22 (https://github.com/JADRT22)
License: MIT
"""

import unittest
from unittest.mock import patch, MagicMock
import sys
import os
import subprocess

# Adjust path to import drivers
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../src')))

from drivers.sway import SwayDriver

OUTPUTS = [{
    "name": "eDP-1",
    "focused": True,
    "rect": {"width": 2560, "height": 1440},
    "current_mode": {"width": 2560, "height": 1440},
}]


class TestSwayDriver(unittest.TestCase):

    def _make_driver(self, seats=None, outputs=None):
        """Builds a driver with the IPC reads stubbed out."""
        seats = [{"name": "seat0"}] if seats is None else seats
        outputs = OUTPUTS if outputs is None else outputs
        with patch("shutil.which", return_value="/usr/bin/swaymsg"), \
                patch.object(SwayDriver, "_command") as cmd:
            cmd.side_effect = [seats, outputs]
            driver = SwayDriver()
        return driver

    def test_records_relative_motion(self):
        # The sway IPC cannot report the cursor position, so the recorder
        # must fall back to relative events.
        driver = self._make_driver()
        self.assertFalse(driver.supports_absolute_positioning)

    def test_resolution_comes_from_output_rect(self):
        driver = self._make_driver()
        self.assertEqual((driver.screen_width, driver.screen_height),
                         (2560, 1440))

    def test_resolution_falls_back_to_current_mode(self):
        outputs = [{"name": "eDP-1", "focused": True,
                    "rect": {}, "current_mode": {"width": 1920, "height": 1080}}]
        driver = self._make_driver(outputs=outputs)
        self.assertEqual((driver.screen_width, driver.screen_height),
                         (1920, 1080))

    def test_resolution_fallback_when_no_outputs(self):
        driver = self._make_driver(seats=[], outputs=[])
        self.assertEqual((driver.screen_width, driver.screen_height),
                         (1920, 1080))

    def test_seat_defaults_to_seat0_when_query_fails(self):
        driver = self._make_driver(seats=[])
        self.assertEqual(driver._seat, "seat0")

    def test_get_cursor_pos_returns_none(self):
        driver = self._make_driver()
        with patch.object(driver, "_command") as cmd:
            self.assertIsNone(driver.get_cursor_pos())
            cmd.assert_not_called()

    def test_seat_cursor_set_warps_absolute(self):
        driver = self._make_driver()
        with patch.object(driver, "_command") as cmd:
            cmd.return_value = {"success": True}
            driver.move_cursor(100, 200)
            cmd.assert_called_once_with("seat seat0 cursor set 100 200")

    def test_move_cursor_is_clamped(self):
        driver = self._make_driver()
        with patch.object(driver, "_command") as cmd:
            cmd.return_value = {"success": True}
            driver.move_cursor(99999, 99999)
            cmd.assert_called_once_with("seat seat0 cursor set 2559 1439")

    def test_seat_cursor_move_is_relative(self):
        driver = self._make_driver()
        with patch.object(driver, "_command") as cmd:
            cmd.return_value = {"success": True}
            self.assertTrue(driver.move_relative(-30, 40))
            cmd.assert_called_once_with("seat seat0 cursor move -30 40")

    def test_move_relative_returns_false_when_ipc_fails(self):
        driver = self._make_driver()
        with patch.object(driver, "_command") as cmd:
            cmd.return_value = None
            self.assertFalse(driver.move_relative(10, 10))

    def test_accepts_swaymsg_array_reply(self):
        # swaymsg answers 'cursor' commands with a list of result objects:
        #   [{"success": true}]
        driver = self._make_driver()
        with patch.object(driver, "_command") as cmd:
            cmd.return_value = [{"success": True}]
            self.assertTrue(driver.move_relative(10, 10))

    def test_move_relative_returns_false_on_failed_command(self):
        driver = self._make_driver()
        with patch.object(driver, "_command") as cmd:
            cmd.return_value = [{"success": False, "parse_error": "..."}]
            self.assertFalse(driver.move_relative(10, 10))

    def test_mouse_button_maps_evdev_to_sway_names(self):
        from evdev.ecodes import BTN_LEFT, BTN_RIGHT, BTN_MIDDLE, BTN_SIDE
        driver = self._make_driver()
        cases = [(BTN_LEFT, "press", "button1"),
                 (BTN_LEFT, "release", "button1"),
                 (BTN_RIGHT, "press", "button3"),
                 (BTN_MIDDLE, "press", "button2")]
        for code, state, name in cases:
            with patch.object(driver, "_command") as cmd:
                cmd.return_value = {"success": True}
                self.assertTrue(driver.mouse_button(code, state == "press"))
                cmd.assert_called_once_with(
                    "seat seat0 cursor %s %s" % (state, name))

    def test_unknown_button_is_not_handled(self):
        from evdev.ecodes import BTN_SIDE
        driver = self._make_driver()
        with patch.object(driver, "_command") as cmd:
            self.assertFalse(driver.mouse_button(BTN_SIDE, True))
            cmd.assert_not_called()

    def test_scroll_uses_axis_buttons_one_call_per_click(self):
        driver = self._make_driver()
        with patch.object(driver, "_command") as cmd:
            cmd.return_value = {"success": True}
            self.assertTrue(driver.scroll("down", 2))
            self.assertEqual(cmd.call_count, 2)
            cmd.assert_called_with("seat seat0 cursor press button5")

    def test_scroll_up(self):
        driver = self._make_driver()
        with patch.object(driver, "_command") as cmd:
            cmd.return_value = {"success": True}
            self.assertTrue(driver.scroll("up"))
            cmd.assert_called_once_with("seat seat0 cursor press button4")

    def test_scroll_unknown_direction_is_not_handled(self):
        driver = self._make_driver()
        with patch.object(driver, "_command") as cmd:
            self.assertFalse(driver.scroll("sideways"))
            cmd.assert_not_called()

    def test_command_reports_failure_without_raising(self):
        with patch("shutil.which", return_value="/usr/bin/swaymsg"), \
                patch("subprocess.run") as run:
            run.side_effect = OSError("no sway")
            with patch.object(SwayDriver, "_command") as cmd:
                cmd.side_effect = [[{"name": "seat0"}], OUTPUTS]
                driver = SwayDriver()
            with patch("subprocess.run", side_effect=OSError("no sway")):
                self.assertFalse(driver.move_relative(1, 1))

    def test_negative_coordinates_survive_getopt(self):
        # 'swaymsg cursor move -30 40' loses '-30' to getopt; a '--' separator
        # keeps the coordinate on the command side.
        driver = self._make_driver()
        with patch("subprocess.run") as run:
            run.return_value = subprocess.CompletedProcess(
                run.call_args, 0, '[{"success": true}]', ""
            )
            driver.move_relative(-30, 40)
            self.assertEqual(
                run.call_args[0][0],
                [driver.swaymsg_path, "--", "seat", "seat0", "cursor",
                 "move", "-30", "40"],
            )

    def test_query_type_is_not_separated(self):
        # Adding '--' before a '-t get_x' query turns the type into a
        # command name, so get_seats/get_outputs must reach getopt bare.
        driver = self._make_driver()
        with patch("subprocess.run") as run:
            run.return_value = subprocess.CompletedProcess(
                run.call_args, 0, "[]", ""
            )
            driver._command("-t get_seats")
            self.assertEqual(
                run.call_args[0][0],
                [driver.swaymsg_path, "-t", "get_seats"],
            )

    def test_self_test_reports_success(self):
        driver = self._make_driver()
        with patch.object(driver, "_command") as cmd:
            cmd.return_value = {"success": True}
            self.assertTrue(driver.self_test())

    def test_self_test_fails_without_swaymsg(self):
        driver = self._make_driver()
        driver.swaymsg_path = None
        self.assertFalse(driver.self_test())


if __name__ == '__main__':
    unittest.main()
