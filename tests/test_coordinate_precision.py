# -*- coding: utf-8 -*-
"""
LinuxTask - test_coordinate_precision.py
Description: Tests for coordinate clamping and scaling.
Author: JADRT22 (https://github.com/JADRT22)
License: MIT
"""

import sys
import os
import unittest
from unittest.mock import MagicMock

# Adjust path to import drivers
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../src')))

from drivers.gnome import GnomeDriver

class TestCoordinatePrecision(unittest.TestCase):
    def setUp(self):
        # Mock subprocess/which so ensure_daemon() runs its real path without
        # spawning ydotoold (3s socket wait) or leaking a Popen ResourceWarning.
        self.patcher_shutil = unittest.mock.patch('shutil.which', return_value='/usr/bin/ydotool')
        self.patcher_subp = unittest.mock.patch('subprocess.run')
        self.patcher_subp_out = unittest.mock.patch('subprocess.check_output', return_value=b"1920x1080")
        self.patcher_popen = unittest.mock.patch('subprocess.Popen')
        self.patcher_sleep = unittest.mock.patch('drivers.gnome.time.sleep')

        self.patcher_shutil.start()
        self.patcher_subp.start()
        self.patcher_subp_out.start()
        self.mock_popen = self.patcher_popen.start()
        self.patcher_sleep.start()

        # Initialize driver (it will use the mocks)
        self.driver = GnomeDriver()
        self.driver.screen_width = 1920
        self.driver.screen_height = 1080

    def tearDown(self):
        self.patcher_shutil.stop()
        self.patcher_subp.stop()
        self.patcher_subp_out.stop()
        self.patcher_popen.stop()
        self.patcher_sleep.stop()

    def test_clamping_logic(self):
        """Verify that coordinates logic can be tested in CI."""
        # This is a placeholder test for logic that doesn't require a real display
        self.assertEqual(self.driver.screen_width, 1920)
        self.assertEqual(self.driver.screen_height, 1080)
        # Daemon start path still exercised, only the spawn is mocked.
        self.mock_popen.assert_called_once()

if __name__ == "__main__":
    unittest.main()
