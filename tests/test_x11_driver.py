# -*- coding: utf-8 -*-
"""
LinuxTask - test_x11_driver.py
Description: Unit tests for X11 driver.
Author: JADRT22 (https://github.com/JADRT22)
License: MIT
"""

import unittest
from unittest.mock import patch, MagicMock
import subprocess
import sys
import os

# Adjust path to import drivers
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../src')))

from drivers.x11 import X11Driver


class TestX11Driver(unittest.TestCase):

    @patch('shutil.which', return_value='/usr/bin/xdotool')
    @patch('subprocess.check_output')
    def test_detect_resolution(self, mock_output, mock_which):
        xrandr_output = (
            "Screen 0: minimum 8 x 8, current 1920 x 1080, maximum 32767 x 32767\n"
            "eDP-1 connected primary 1920x1080+0+0\n"
            "   1920x1080     60.00*+  59.97    59.96\n"
            "   1366x768      59.79    60.00\n"
        )
        mock_output.return_value = xrandr_output.encode()

        driver = X11Driver()
        self.assertEqual(driver.screen_width, 1920)
        self.assertEqual(driver.screen_height, 1080)

    @patch('shutil.which', return_value='/usr/bin/xdotool')
    @patch('subprocess.check_output')
    def test_get_cursor_pos(self, mock_output, mock_which):
        # First call: xrandr for __init__
        # Second call: xdotool getmouselocation
        mock_output.side_effect = [
            b"   1920x1080     60.00*+\n",
            b"x:350 y:200 screen:0 window:12345678\n"
        ]

        driver = X11Driver()
        x, y = driver.get_cursor_pos()
        self.assertEqual(x, 350)
        self.assertEqual(y, 200)

    @patch('subprocess.run')
    @patch('shutil.which', return_value='/usr/bin/xdotool')
    @patch('subprocess.check_output')
    def test_move_cursor(self, mock_output, mock_which, mock_run):
        mock_output.return_value = b"   1920x1080     60.00*+\n"
        mock_run.return_value = MagicMock(returncode=0)

        driver = X11Driver()
        driver.move_cursor(500, 600)

        mock_run.assert_called_once_with(
            ['xdotool', 'mousemove', '500', '600'],
            capture_output=True, check=True
        )

    @patch('subprocess.run')
    @patch('shutil.which', return_value='/usr/bin/xdotool')
    @patch('subprocess.check_output')
    def test_move_relative(self, mock_output, mock_which, mock_run):
        mock_output.return_value = b"   1920x1080     60.00*+\n"
        mock_run.return_value = MagicMock(returncode=0)

        driver = X11Driver()
        result = driver.move_relative(10, -5)

        # Should return False to trigger UInput fallback
        self.assertFalse(result)
        # Should NOT call subprocess.run
        mock_run.assert_not_called()

    @patch('subprocess.run')
    @patch('shutil.which', return_value='/usr/bin/xdotool')
    @patch('subprocess.check_output')
    def test_scroll_up(self, mock_output, mock_which, mock_run):
        mock_output.return_value = b"   1920x1080     60.00*+\n"
        mock_run.return_value = MagicMock(returncode=0)

        driver = X11Driver()
        driver.scroll('up', 3)

        mock_run.assert_called_once_with(
            ['xdotool', 'click', '--repeat', '3', '4'],
            capture_output=True, check=True
        )

    @patch('subprocess.run')
    @patch('shutil.which', return_value='/usr/bin/xdotool')
    @patch('subprocess.check_output')
    def test_scroll_down(self, mock_output, mock_which, mock_run):
        mock_output.return_value = b"   1920x1080     60.00*+\n"
        mock_run.return_value = MagicMock(returncode=0)

        driver = X11Driver()
        driver.scroll('down', 1)

        mock_run.assert_called_once_with(
            ['xdotool', 'click', '--repeat', '1', '5'],
            capture_output=True, check=True
        )

    @patch('shutil.which', return_value=None)
    def test_missing_xdotool_raises(self, mock_which):
        with self.assertRaises(RuntimeError) as ctx:
            X11Driver()
        self.assertIn("xdotool not found", str(ctx.exception))

    @patch('shutil.which', return_value='/usr/bin/xdotool')
    @patch('subprocess.check_output')
    def test_fallback_resolution(self, mock_output, mock_which):
        # xrandr fails
        mock_output.side_effect = subprocess.CalledProcessError(1, 'xrandr')

        driver = X11Driver()
        self.assertEqual(driver.screen_width, 1920)
        self.assertEqual(driver.screen_height, 1080)


class TestAutoDetectDriver(unittest.TestCase):

    @patch.dict(os.environ, {
        'XDG_CURRENT_DESKTOP': 'X-Cinnamon',
        'DISPLAY': ':0'
    }, clear=False)
    @patch('shutil.which', return_value='/usr/bin/xdotool')
    @patch('subprocess.check_output')
    def test_cinnamon_returns_x11(self, mock_output, mock_which):
        mock_output.return_value = b"   1920x1080     60.00*+\n"
        # Remove Hyprland signature if present
        os.environ.pop('HYPRLAND_INSTANCE_SIGNATURE', None)

        from drivers.factory import AutoDetectDriver
        driver = AutoDetectDriver()
        self.assertIsInstance(driver, X11Driver)


if __name__ == '__main__':
    unittest.main()
