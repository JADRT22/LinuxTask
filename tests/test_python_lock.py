# -*- coding: utf-8 -*-
"""
LinuxTask - test_python_lock.py
Description: Keeps the AppImage interpreter pin coherent: the lock file,
             the shell that reads it in build.sh, and the script that
             rewrites it must agree on the same format and the same
             series as the wheels.
Author: JADRT22 (https://github.com/JADRT22)
License: MIT
"""

import os
import re
import sys
import unittest

REPO = os.path.abspath(
    os.path.join(os.path.dirname(__file__), '..')
)
APPIMAGE_DIR = os.path.join(REPO, 'tools', 'appimage')
LOCK_PATH = os.path.join(APPIMAGE_DIR, 'python-build-standalone.lock')
BUILD_SH = os.path.join(APPIMAGE_DIR, 'build.sh')
STAGE_PYPROJECT = os.path.join(APPIMAGE_DIR, 'pyproject.toml')

# build.sh reads the lock by hand; update_python_lock.py writes it. Both
# live in tools/appimage, which is not on the test import path, so the
# script is imported the same way the tooling scripts do.
sys.path.insert(0, APPIMAGE_DIR)
import update_python_lock


def parse_lock(text):
    """Same KEY=VALUE reading build.sh does with sed."""
    values = {}
    for line in text.splitlines():
        if '=' in line and not line.startswith('#'):
            key, value = line.split('=', 1)
            values[key] = value
    return values


def lock_values():
    with open(LOCK_PATH, encoding='utf-8') as fh:
        return parse_lock(fh.read())


class LockFileShape(unittest.TestCase):

    def test_lock_exists_with_every_field(self):
        values = lock_values()
        for key in ('TAG', 'PYTHON_VERSION', 'URL', 'SHA256', 'SIZE'):
            self.assertIn(key, values)
            self.assertTrue(values[key], '%s is empty' % key)

    def test_digest_is_sha256_hex(self):
        self.assertRegex(lock_values()['SHA256'], r'^[0-9a-f]{64}$')

    def test_url_is_the_pinned_release_asset(self):
        values = lock_values()
        url = values['URL']
        self.assertTrue(url.startswith('https://'), url)
        self.assertIn(
            '/releases/download/%s/' % values['TAG'], url,
            'URL must come from the release TAG names')
        self.assertIn('x86_64-unknown-linux-gnu-install_only_stripped', url)
        self.assertNotIn('freethreaded', url)

    def test_python_version_matches_tag_and_url(self):
        values = lock_values()
        self.assertRegex(values['PYTHON_VERSION'], r'^\d+\.\d+\.\d+$')
        url = values['URL'].replace('+', '%2B')
        self.assertIn(
            'cpython-%s%%2B%s-' % (values['PYTHON_VERSION'], values['TAG']),
            url,
            'the asset name must carry the version and tag the lock claims')

    def test_series_matches_the_bundle_pyproject(self):
        """The tarball and [tool.appimage] python must be one series: the
        wheels are source-built against the bundled ABI."""
        with open(STAGE_PYPROJECT, encoding='utf-8') as fh:
            text = fh.read()
        match = re.search(r'^python\s*=\s*"(\d+\.\d+)"', text, re.M)
        self.assertIsNotNone(match, '[tool.appimage] python not found')
        series = match.group(1)
        self.assertTrue(
            lock_values()['PYTHON_VERSION'].startswith(series + '.'),
            'pin is CPython %s, the bundle builds for %s'
            % (lock_values()['PYTHON_VERSION'], series))


class BuildScriptReadsThePin(unittest.TestCase):
    """Rules checked against build.sh with whole-line comments removed:
    the comments are where the old, wrong behaviour is explained."""

    def setUp(self):
        with open(BUILD_SH, encoding='utf-8') as fh:
            self.source = '\n'.join(
                line for line in fh.read().splitlines()
                if not line.lstrip().startswith('#')
            )

    def test_no_floating_latest_lookup(self):
        self.assertNotIn(
            'releases/latest', self.source,
            'build.sh must not resolve "latest": two builds of one commit '
            'would ship two different interpreters.')

    def test_lock_is_read_and_its_fields_used(self):
        self.assertIn('python-build-standalone.lock', self.source)
        for field in ('TAG', 'PYTHON_VERSION', 'URL', 'SHA256'):
            self.assertIn(
                "s/^%s=//p" % field, self.source,
                'build.sh should extract %s with the same KEY=VALUE format '
                'update_python_lock.py writes.' % field)

    def test_download_is_verified_before_publishing_the_cache(self):
        start = self.source.index('sha256sum --check')
        end = self.source.index('mv "$PYTARBALL.tmp" "$PYTARBALL"')
        window = self.source[start:end]
        # A failed check must remove the temp file and abort, so nothing
        # but a verified archive can ever become the cache entry. Both the
        # download failure and the digest failure take that path.
        self.assertEqual(window.count('rm -f "$PYTARBALL.tmp"'), 2)
        self.assertEqual(window.count('exit 1'), 2)
        self.assertIn('rm -f "$PYTARBALL.tmp"', window)
        self.assertIn('exit 1', window)
        self.assertLess(
            window.index('rm -f "$PYTARBALL.tmp"'), window.index('exit 1'))

    def test_every_field_is_required(self):
        self.assertIn('for _pbs_var in PBS_TAG PBS_PYVER PBS_URL PBS_SHA256',
                      self.source)


class UpdateScriptAssetRule(unittest.TestCase):
    """The rule that picks the asset is what makes the pin reproducible."""

    def _release(self, *names):
        return {
            'tag_name': '20261026',
            'assets': [
                {
                    'name': name,
                    'browser_download_url':
                        'https://github.com/astral-sh/python-build-standalone'
                        '/releases/download/20261026/' + name,
                    'size': 1,
                    'digest': 'sha256:%s' % ('ab' * 32),
                }
                for name in names
            ],
        }

    def test_picks_the_stripped_install_only_build(self):
        wanted = ('cpython-3.12.16+20261026-x86_64-unknown-linux-gnu-'
                  'install_only_stripped.tar.gz')
        asset = update_python_lock.pick_asset(self._release(
            'cpython-3.12.16+20261026-aarch64-unknown-linux-gnu.tar.gz',
            wanted,
        ))
        self.assertEqual(asset['name'], wanted)

    def test_ignores_other_series_and_freethreaded(self):
        with self.assertRaises(update_python_lock.NoMatchingAsset):
            update_python_lock.pick_asset(self._release(
                'cpython-3.13.1+20261026-x86_64-unknown-linux-gnu-'
                'install_only_stripped.tar.gz',
            ))
        with self.assertRaises(update_python_lock.NoMatchingAsset):
            update_python_lock.pick_asset(self._release(
                'cpython-3.12.16t+20261026-x86_64-unknown-linux-gnu-'
                'install_only_stripped-freethreaded.tar.gz',
            ))

    def test_digest_and_version_parsing(self):
        asset = update_python_lock.pick_asset(self._release(
            'cpython-3.12.16+20261026-x86_64-unknown-linux-gnu-'
            'install_only_stripped.tar.gz'))
        self.assertEqual(update_python_lock.digest_of(asset), 'ab' * 32)
        self.assertEqual(update_python_lock.version_of(asset), '3.12.16')
        self.assertIsNone(
            update_python_lock.digest_of({'digest': 'sha1:deadbeef'}))
        self.assertIsNone(update_python_lock.digest_of({}))

    def test_rendered_lock_is_readable_by_the_bash_side(self):
        asset = update_python_lock.pick_asset(self._release(
            'cpython-3.12.16+20261026-x86_64-unknown-linux-gnu-'
            'install_only_stripped.tar.gz'))
        values = parse_lock(
            update_python_lock.render_lock(
                {'tag_name': '20261026'}, asset, 'ab' * 32))
        self.assertEqual(values['TAG'], '20261026')
        self.assertEqual(values['PYTHON_VERSION'], '3.12.16')
        self.assertEqual(values['SHA256'], 'ab' * 32)
        self.assertIn('URL', values)


class RealLockMatchesTheScriptOutput(unittest.TestCase):
    """The committed lock is what this script would write today."""

    def test_committed_lock_parses_to_script_format(self):
        values = lock_values()
        # No extra keys, no missing ones: build.sh and the writer agree.
        self.assertEqual(
            sorted(values),
            ['PYTHON_VERSION', 'SHA256', 'SIZE', 'TAG', 'URL'])


class TestSourceBuiltWheels(unittest.TestCase):
    """The bundle's compiled wheels must not come from pip's global cache.

    PyPI serves evdev as an sdist only, so someone has to compile it. When
    that happens inside appimage.ctl's pip install, pip is free to reuse
    ~/.cache/pip/wheels -- keyed by name and ABI tag, not by whether the
    extensions actually built -- and the AppImage ships an evdev whose
    `import evdev` dies on the user's machine. build.sh therefore builds
    every compiled dependency itself, into the project-local wheels dir.
    """

    def setUp(self):
        with open(BUILD_SH, encoding='utf-8') as fh:
            self.build = fh.read()
        with open(STAGE_PYPROJECT, encoding='utf-8') as fh:
            self.pyproject = fh.read()

    def _wheel_loop(self):
        start = self.build.index('for spec in')
        return self.build[start:self.build.index('BPY=""', start)]

    def test_evdev_is_source_built(self):
        self.assertIn('evdev', self._wheel_loop())

    def test_wheel_builds_skip_the_pip_wheel_cache(self):
        self.assertIn('--no-cache-dir', self._wheel_loop())

    def test_a_wheel_without_extensions_fails_the_build(self):
        # The tag alone cannot tell a good wheel from an empty one.
        self.assertIn(".so", self._wheel_loop())

    def _appimage_packages(self):
        """The [tool.appimage] packages list only.

        Splitting on 'packages = [' from the whole file would hit
        [tool.setuptools] packages = ["drivers"] first and silently test
        nothing, which is worse than failing.
        """
        section = self.pyproject.split('[tool.appimage]')[1]
        return section.split('packages = [')[1].split(']')[0]

    def test_evdev_is_no_longer_left_to_pypi(self):
        deps = self.pyproject.split('dependencies = [')[1].split(']')[0]
        self.assertNotIn('evdev', deps)
        self.assertIn('../wheels/evdev-', self._appimage_packages())

    def test_bundled_evdev_version_matches_the_pinned_one(self):
        with open(os.path.join(REPO, 'requirements.txt'),
                  encoding='utf-8') as fh:
            runtime = fh.read()
        runtime_pin = re.search(r'^evdev==(\S+)$', runtime, re.M).group(1)
        bundled = re.search(
            r'\.\./wheels/evdev-([^/]+?)-cp\d+-cp\d+-',
            self._appimage_packages()).group(1)
        self.assertEqual(
            bundled, runtime_pin,
            "the AppImage would bundle a different evdev than the install "
            "script does; update both pins together")

    def test_every_pinned_wheel_is_in_the_build_loop(self):
        # A wheel listed in pyproject but never built fails at the end of
        # a long build instead of at the start.
        packages = self._appimage_packages()
        loop = self._wheel_loop()
        for wheel in re.findall(r'\.\./wheels/([a-zA-Z_]+)-', packages):
            canonical = {'dbus_python': 'dbus-python',
                         'pygobject': 'PyGObject',
                         'pycairo': 'pycairo'}.get(wheel, wheel)
            self.assertIn(canonical, loop)

    def test_the_build_loop_pins_a_wheel_for_every_bundled_binding(self):
        # The loop above proves the names match; this proves the list has
        # not lost one of the four wheels the app imports in the bundle.
        packages = self._appimage_packages()
        for wheel in ('evdev', 'dbus_python', 'pycairo', 'pygobject'):
            self.assertIn(f'../wheels/{wheel}-', packages)


if __name__ == '__main__':
    unittest.main()
