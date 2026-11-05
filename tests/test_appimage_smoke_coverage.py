# -*- coding: utf-8 -*-
"""
LinuxTask - test_appimage_smoke_coverage.py
Description: Keeps the AppImage smoke guard covering every driver, and
             keeps the published artifact path identical in build.sh's own
             documentation, the copy it performs, and release.yml.
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


class PublishedArtifactPath(unittest.TestCase):
    """The path release.yml attaches must be the path build.sh writes.

    build.sh documents `build/appimage/dist/LinuxTask-x86_64.AppImage` as
    its output while the builder actually leaves the file in the staging
    project's own `proj/dist/`; release.yml took the documented path, so
    the appimage job would have failed at "Verify the artifact exists" and
    published v3.5.0 with no AppImage attached -- the exact bug the job was
    added to fix. Nothing but a tag push shows this, so the three files
    that mention the artifact are compared here instead.
    """

    def _expand(self, value, variables):
        for _ in range(4):
            for key, replacement in variables.items():
                value = value.replace(key, replacement)
        return value

    def test_build_sh_publishes_at_its_documented_output_path(self):
        with open(BUILD_SH, encoding='utf-8') as fh:
            text = fh.read()
        documented = re.search(r'^# Output: (\S+)', text, re.M).group(1)
        variables = {
            '$REPO_ROOT': REPO,
            '$STAGE': self._expand(
                re.search(r'^STAGE="([^"]+)"', text, re.M).group(1),
                {'$REPO_ROOT': REPO}),
        }
        variables['"$STAGE"'] = variables['$STAGE']
        match = re.search(r'^cp -f "([^"]+)" "([^"]+)/"$', text, re.M)
        assert match, "build.sh never copies the artifact anywhere"
        source = self._expand(match.group(1), variables)
        destination = os.path.join(
            self._expand(match.group(2), variables),
            os.path.basename(source))
        self.assertEqual(destination, os.path.join(REPO, documented),
                         'build.sh publishes somewhere else than it documents')

    def test_release_workflow_attaches_the_documented_path(self):
        path = os.path.join(REPO, '.github', 'workflows', 'release.yml')
        with open(path, encoding='utf-8') as fh:
            workflow = fh.read()
        with open(BUILD_SH, encoding='utf-8') as fh:
            documented = re.search(r'^# Output: (\S+)', fh.read(),
                                   re.M).group(1)
        referenced = re.findall(r'\S*LinuxTask-x86_64\.AppImage', workflow)
        self.assertTrue(referenced, 'release.yml attaches no AppImage')
        for ref in referenced:
            self.assertEqual(
                ref, documented,
                'release.yml references %s, which build.sh does not produce'
                % ref)


if __name__ == '__main__':
    unittest.main()
