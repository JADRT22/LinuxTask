# -*- coding: utf-8 -*-
"""
LinuxTask - test_hyprland_driver.py
Description: Unit tests for Hyprland driver.
Author: JADRT22 (https://github.com/JADRT22)
License: MIT
"""

import unittest
from unittest.mock import patch, MagicMock
import subprocess
import json
import sys
import os

# Adjust path to import drivers
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../src')))

from drivers.hyprland import HyprlandDriver


class TestHyprlandDriver(unittest.TestCase):

    @patch('subprocess.check_output')
    def test_detect_resolution(self, mock_output):
        # Mock monitors info
        mock_monitors = [
            {"id": 0, "name": "eDP-1", "width": 1920, "height": 1080, "focused": True},
            {"id": 1, "name": "HDMI-A-1", "width": 2560, "height": 1440, "focused": False}
        ]
        mock_output.return_value = json.dumps(mock_monitors).encode()

        driver = HyprlandDriver()
        self.assertEqual(driver.screen_width, 1920)
        self.assertEqual(driver.screen_height, 1080)

    @patch('subprocess.check_output')
    def test_get_cursor_pos(self, mock_output):
        # First call for __init__ (resolution detection)
        # Second call for get_cursor_pos
        mock_output.side_effect = [
            b'[]',  # Empty monitors list for __init__
            b'100, 200\n'
        ]

        driver = HyprlandDriver()
        # Default resolution fallback
        self.assertEqual(driver.screen_width, 1920)

        x, y = driver.get_cursor_pos()
        self.assertEqual(x, 100)
        self.assertEqual(y, 200)

    @patch('subprocess.run')
    @patch('subprocess.check_output')
    def test_move_cursor(self, mock_output, mock_run):
        mock_output.return_value = b'[]'  # __init__
        mock_run.return_value = MagicMock(returncode=0)

        driver = HyprlandDriver()
        driver.move_cursor(500, 600)

        mock_run.assert_called_once_with(
            ["hyprctl", "dispatch", "movecursor", "500 600"],
            capture_output=True, check=True
        )

    @patch('subprocess.run')
    @patch('subprocess.check_output')
    def test_move_relative(self, mock_output, mock_run):
        # __init__ resolution detection
        mock_output.side_effect = [
            b'[]',       # monitors for __init__
            b'100, 200'  # cursorpos for move_relative
        ]
        mock_run.return_value = MagicMock(returncode=0)

        driver = HyprlandDriver()
        driver.move_relative(10, -5)

        # Should call move_cursor with (110, 195)
        mock_run.assert_called_once_with(
            ["hyprctl", "dispatch", "movecursor", "110 195"],
            capture_output=True, check=True
        )

    @patch('subprocess.check_call')
    @patch('subprocess.run')
    @patch('subprocess.check_output')
    def test_self_test_success(self, mock_output, mock_run, mock_call):
        # 1. Monitors for __init__
        # 2. cursorpos for self_test
        # 3. cursorpos for self_test (verify)
        mock_output.side_effect = [
            b'[]',
            b'10, 10',
            b'20, 20'
        ]
        mock_call.return_value = 0  # command -v hyprctl
        mock_run.return_value = MagicMock(returncode=0)

        driver = HyprlandDriver()
        success = driver.self_test()
        self.assertTrue(success)


if __name__ == '__main__':
    unittest.main()
