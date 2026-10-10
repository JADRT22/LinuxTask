# -*- coding: utf-8 -*-
"""
LinuxTask - test_appimage_smoke_coverage.py
Description: Keeps the AppImage smoke guard covering every driver.
Author: JADRT22 (https://github.com/JADRT22)
License: MIT
"""

import os
import re
import unittest

REPO = os.path.abspath(
    os.path.join(os.path.dirname(__file__), '..')
)
BUILD_SH = os.path.join(REPO, 'tools', 'appimage', 'build.sh')
DRIVERS_DIR = os.path.join(REPO, 'src', 'drivers')


def smoke_guard_source():
    """Returns the python source passed to the bundled interpreter."""
    with open(BUILD_SH, encoding='utf-8') as fh:
        text = fh.read()
    match = re.search(r'python3\.12" -c "\n(.*?)\n" > ', text, re.S)
    assert match, "smoke guard block not found in build.sh"
    return match.group(1)


class SmokeGuardCoverage(unittest.TestCase):
    """The guard must import every module the app can load at runtime."""

    def test_every_driver_module_is_imported(self):
        source = smoke_guard_source()
        missing = []
        for name in sorted(os.listdir(DRIVERS_DIR)):
            if name.startswith('_') or not name.endswith('.py'):
                continue
            module = name[:-3]
            if module in ('base', '__init__'):
                continue  # loaded indirectly by 'from .base import ...'
            # A driver absent from the bundle's dependency list is allowed
            # to be missing; nothing else is.
            if 'drivers.%s' % module not in source:
                missing.append('drivers.%s' % module)
        self.assertEqual(
            missing, [],
            "drivers missing from the AppImage smoke guard: %s"
            % ', '.join(missing)
        )

    def test_guard_checks_the_version_constant(self):
        self.assertIn('APP_VERSION', smoke_guard_source())


if __name__ == '__main__':
    unittest.main()
