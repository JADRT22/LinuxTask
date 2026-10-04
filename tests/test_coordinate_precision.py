# -*- coding: utf-8 -*-
"""
LinuxTask - test_coordinate_precision.py
Description: Tests for coordinate clamping and scaling.
Author: JADRT22 (https://github.com/JADRT22)
License: MIT
"""

import sys
import os
import tempfile
import unittest
from unittest.mock import MagicMock

# Adjust path to import drivers
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../src')))

from drivers.gnome import GnomeDriver

# os.unlink is patched during setUp, so temp files are removed with this
# reference taken before any patch is active.
_real_unlink = os.unlink

# First tempfile use probes TMPDIR by creating and unlinking a scratch file;
# do it now so that unlink never lands on the mock active during setUp.
tempfile.gettempdir()

class TestCoordinatePrecision(unittest.TestCase):
    def setUp(self):
        # ensure_daemon() must run its real path without spawning ydotoold
        # (3s socket wait, Popen ResourceWarning) and without mutating a live
        # /run/user/<uid>/.ydotool_socket: a real unlink there would kill a
        # running ydotoold. gnome.py calls the stdlib os/time modules, so
        # those patches are process-wide; tests run serially and addCleanup
        # unwinds everything even if GnomeDriver() raises below.
        self.patcher_shutil = unittest.mock.patch('shutil.which', return_value='/usr/bin/ydotool')
        self.patcher_shutil.start()
        self.addCleanup(self.patcher_shutil.stop)
        self.patcher_subp = unittest.mock.patch('subprocess.run')
        self.patcher_subp.start()
        self.addCleanup(self.patcher_subp.stop)
        self.patcher_subp_out = unittest.mock.patch('subprocess.check_output', return_value=b"1920x1080")
        self.patcher_subp_out.start()
        self.addCleanup(self.patcher_subp_out.stop)
        self.patcher_popen = unittest.mock.patch('subprocess.Popen')
        self.mock_popen = self.patcher_popen.start()
        self.addCleanup(self.patcher_popen.stop)
        self.patcher_sleep = unittest.mock.patch('drivers.gnome.time.sleep')
        self.patcher_sleep.start()
        self.addCleanup(self.patcher_sleep.stop)
        self.patcher_unlink = unittest.mock.patch('drivers.gnome.os.unlink')
        self.mock_unlink = self.patcher_unlink.start()
        self.addCleanup(self.patcher_unlink.stop)
        self.patcher_chmod = unittest.mock.patch('drivers.gnome.os.chmod')
        self.patcher_chmod.start()
        self.addCleanup(self.patcher_chmod.stop)

        # Initialize driver (it will use the mocks)
        self.driver = GnomeDriver()
        self.driver.screen_width = 1920
        self.driver.screen_height = 1080

    def test_clamping_logic(self):
        """Verify that coordinates logic can be tested in CI."""
        # This is a placeholder test for logic that doesn't require a real display
        self.assertEqual(self.driver.screen_width, 1920)
        self.assertEqual(self.driver.screen_height, 1080)
        # Daemon start path still exercised, only the spawn is mocked.
        self.mock_popen.assert_called_once()

    def test_stale_socket_cleanup_keeps_file(self):
        """The stale-socket unlink path runs, but only against the mock."""
        fd, fake = tempfile.mkstemp(prefix='ydotool_socket_')
        os.close(fd)
        self.addCleanup(lambda: os.path.exists(fake) and _real_unlink(fake))
        self.driver.socket = fake
        self.driver.ensure_daemon()
        # setUp's GnomeDriver() may also hand the live socket path to this
        # mock, so only require that ours went through it too.
        self.mock_unlink.assert_any_call(fake)
        self.assertTrue(os.path.exists(fake), "unlink mock leaked: fake socket was deleted")

if __name__ == "__main__":
    unittest.main()
