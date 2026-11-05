# -*- coding: utf-8 -*-
"""
LinuxTask - test_release_version.py
Description: Guards the version plumbing tools/release.py owns: APP_VERSION
             as the source of truth, the pyproject mirrors, and the semver
             bump arithmetic. A release that writes the version into only
             some of these files is how 3.4.0 shipped a stale bundle.
Author: JADRT22 (https://github.com/JADRT22)
License: MIT
"""

import os
import re
import sys
import tempfile
import unittest

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
# release.py lives in tools/, which is not an importable package; the
# path insert below is the same bootstrap the tool scripts use.
sys.path.insert(0, os.path.join(REPO, 'tools'))

import release

ROOT_PYPROJECT = os.path.join(REPO, 'pyproject.toml')
APPIMAGE_PYPROJECT = os.path.join(REPO, 'tools', 'appimage', 'pyproject.toml')
MAIN_PY = os.path.join(REPO, 'src', 'main.py')

VERSION_KEY = re.compile(r'^version\s*=\s*["\']([\d.]+)["\']', re.MULTILINE)


def declared_version(path):
    with open(path, encoding='utf-8') as fh:
        match = VERSION_KEY.search(fh.read())
    assert match, 'no version key in %s' % path
    return match.group(1)


class VersionSourcesAgree(unittest.TestCase):
    """Every place the version is written must say the same thing."""

    def test_app_version_is_the_source_of_truth(self):
        with open(MAIN_PY, encoding='utf-8') as fh:
            current = release.APP_VERSION_RE.search(fh.read())
        self.assertIsNotNone(current, 'APP_VERSION constant not found')
        self.assertEqual(current.group(1), declared_version(ROOT_PYPROJECT))
        self.assertEqual(current.group(1), declared_version(APPIMAGE_PYPROJECT))


class MirrorVersionToPyproject(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def write(self, text, name='pyproject.toml'):
        path = os.path.join(self.tmp.name, name)
        with open(path, 'w', encoding='utf-8') as fh:
            fh.write(text)
        return path

    def test_rewrites_the_version_key(self):
        path = self.write('[project]\nname = "linuxtask"\nversion = "1.0.0"\n')
        self.assertTrue(release._mirror_version_to_pyproject(path, '3.4.2'))
        self.assertEqual(declared_version(path), '3.4.2')

    def test_touches_only_the_version_key(self):
        path = self.write(
            '[project]\nname = "linuxtask"\nversion = "1.0.0"\n'
            'description = "version = \\"not me\\""\n')
        release._mirror_version_to_pyproject(path, '3.4.2')
        with open(path, encoding='utf-8') as fh:
            text = fh.read()
        self.assertIn('description = "version = \\"not me\\""', text)
        self.assertEqual(len(VERSION_KEY.findall(text)), 1)

    def test_single_quoted_value_is_normalised(self):
        path = self.write("[project]\nversion = '1.0.0'\n")
        self.assertTrue(release._mirror_version_to_pyproject(path, '3.4.2'))
        self.assertIn('version = "3.4.2"', open(path, encoding='utf-8').read())

    def test_missing_file_is_a_warning_not_a_crash(self):
        path = os.path.join(self.tmp.name, 'gone.toml')
        self.assertFalse(
            release._mirror_version_to_pyproject(path, '3.4.2'))
        self.assertFalse(
            release._mirror_version_to_pyproject(path, '3.4.2', required=True))
        self.assertFalse(os.path.exists(path))

    def test_file_without_a_version_key_is_left_alone(self):
        path = self.write('[tool.ruff]\nline-length = 90\n')
        self.assertFalse(release._mirror_version_to_pyproject(path, '3.4.2'))
        self.assertEqual(
            open(path, encoding='utf-8').read(),
            '[tool.ruff]\nline-length = 90\n')


class BumpVersion(unittest.TestCase):

    def test_patch_minor_major(self):
        self.assertEqual(release.bump_version('3.4.1', 'patch'), '3.4.2')
        self.assertEqual(release.bump_version('3.4.1', 'minor'), '3.5.0')
        self.assertEqual(release.bump_version('3.4.1', 'major'), '4.0.0')

    def test_two_part_versions_are_padded(self):
        self.assertEqual(release.bump_version('3.4', 'minor'), '3.5.0')
        self.assertEqual(release.bump_version('3', 'major'), '4.0.0')

    def test_unknown_bump_type_leaves_the_number_unchanged(self):
        # Documented behaviour of the else-less branch: the caller checks
        # the CLI argument, so an unknown type must not silently corrupt.
        self.assertEqual(release.bump_version('3.4.1', 'bugfix'), '3.4.1')


class AppVersionPattern(unittest.TestCase):

    def test_accepts_both_quote_styles(self):
        for line in ('APP_VERSION = "3.4.1"', "APP_VERSION = '3.4.1'"):
            self.assertEqual(
                release.APP_VERSION_RE.search(line).group(1), '3.4.1')

    def test_ignores_a_prefixed_name(self):
        self.assertIsNone(
            release.APP_VERSION_RE.search('PRE_APP_VERSION = "3.4.1"'))


if __name__ == '__main__':
    unittest.main()
