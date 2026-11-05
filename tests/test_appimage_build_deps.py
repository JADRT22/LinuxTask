# -*- coding: utf-8 -*-
"""
LinuxTask - test_appimage_build_deps.py
Description: Keeps the AppImage build's host dependencies coherent across
             the three files that have to agree: the pkg-config preflight
             in build.sh, the Ubuntu package list in
             install-build-deps.sh, and the two workflows that call it.
Author: JADRT22 (https://github.com/JADRT22)
License: MIT
"""

import os
import re
import subprocess
import tempfile
import textwrap
import unittest

REPO = os.path.abspath(
    os.path.join(os.path.dirname(__file__), '..')
)
APPIMAGE_DIR = os.path.join(REPO, 'tools', 'appimage')
BUILD_SH = os.path.join(APPIMAGE_DIR, 'build.sh')
DEPS_SH = os.path.join(APPIMAGE_DIR, 'install-build-deps.sh')
WORKFLOWS = os.path.join(REPO, '.github', 'workflows')
RELEASE_YML = os.path.join(WORKFLOWS, 'release.yml')
CI_YML = os.path.join(WORKFLOWS, 'python-app.yml')

# Each module below is a `dependency()` call in the sdist of the version
# pyproject.toml pins, and the package is the one whose Ubuntu 26.04
# (resolute) file list contains the matching .pc -- checked against
# packages.ubuntu.com, because guessing a -dev package name is exactly the
# mistake that cost v3.5.1 its AppImage: the list installed
# libgirepository1.0-dev, whose file list contains no .pc at all, while
# girepository-2.0.pc ships in libgirepository-2.0-dev.
MODULE_TO_PACKAGE = {
    'dbus-1': 'libdbus-1-dev',
    'glib-2.0': 'libglib2.0-dev',
    'gobject-2.0': 'libglib2.0-dev',
    'gio-2.0': 'libglib2.0-dev',
    'girepository-2.0': 'libgirepository-2.0-dev',
    'gobject-introspection-1.0': 'gobject-introspection',
    'cairo': 'libcairo2-dev',
    'cairo-gobject': 'libcairo2-dev',
    'libffi': 'libffi-dev',
}

# The package that was in the list when the build broke. Nothing in the
# four pinned sdists asks for girepository-1.0.pc, so keeping it would only
# re-hide the gap behind a name that looks right.
LEGACY_PACKAGE = 'libgirepository1.0-dev'


def read(path):
    with open(path, encoding='utf-8') as fh:
        return fh.read()


def module_checks():
    """{binding: [(module, minimum_or_'')]} from build.sh's MODULE_CHECKS."""
    block = re.search(r'MODULE_CHECKS=\(\n(.*?)\n\)', read(BUILD_SH), re.S)
    assert block, 'MODULE_CHECKS array not found in build.sh'
    checks = {}
    for entry in re.findall(r'"([^"]*)"', block.group(1)):
        parts = entry.split()
        assert len(parts) > 1, 'entry without modules: %r' % entry
        checks[parts[0]] = [
            (p.split(':', 1) + [''])[:2] if ':' in p else (p, '')
            for p in parts[1:]
        ]
    return checks


def apt_list():
    """The package names install-build-deps.sh asks apt for."""
    block = re.search(r'apt_list=\(\n(.*?)\n\)', read(DEPS_SH), re.S)
    assert block, 'apt_list array not found in install-build-deps.sh'
    body = re.sub(r'#[^\n]*', '', block.group(1))
    return body.split()


def job_section(workflow_path, job_name):
    """One job's YAML block, from its key to the next job at the same
    indentation. Used because the workflow files legitimately contain a
    second apt list (the distro-bindings job's runtime bindings)."""
    text = read(workflow_path)
    block = re.search(
        r'\n  %s:\n(.*?)(?=\n  [a-z_][a-z0-9_-]*:\n|\Z)' % re.escape(job_name),
        text, re.S)
    assert block, 'job %r not found in %s' % (job_name, workflow_path)
    return block.group(1)


class PreflightHarness(unittest.TestCase):
    """Runs the extracted preflight against a fake pkg-config."""

    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix='preflight-')
        fragment = re.search(
            r'(MODULE_CHECKS=\(.*?\nfi)\n', read(BUILD_SH), re.S
        )
        assert fragment, 'preflight block (MODULE_CHECKS ... fi) not found'
        self.script = os.path.join(self.dir, 'preflight.sh')
        with open(self.script, 'w', encoding='utf-8') as fh:
            fh.write(
                '#!/usr/bin/env bash\nset -euo pipefail\n'
                + fragment.group(1)
                + '\necho "preflight passed"\n'
            )
        self.shim_dir = os.path.join(self.dir, 'bin')
        os.mkdir(self.shim_dir)
        with open(os.path.join(self.shim_dir, 'pkg-config'), 'w',
                  encoding='utf-8') as fh:
            fh.write(textwrap.dedent('''\
                #!/usr/bin/env bash
                mod=""
                min=""
                for a in "$@"; do
                    case "$a" in
                        --atleast-version=*) min="${a#*=}" ;;
                        --*) ;;
                        *) mod="$a" ;;
                    esac
                done
                for m in $MISSING; do
                    [ "$m" = "$mod" ] && exit 1
                done
                for entry in $TOO_OLD; do
                    if [ "${entry%%:*}" = "$mod" ]; then
                        if [ "$1" = "--modversion" ]; then
                            echo "${entry#*:}"
                            exit 0
                        fi
                        [ -n "$min" ] && exit 1
                        exit 0
                    fi
                done
                if [ "$1" = "--modversion" ]; then echo 9.9.9; fi
                exit 0
            '''))
        os.chmod(os.path.join(self.shim_dir, 'pkg-config'), 0o755)

    def run_preflight(self, missing='', too_old=''):
        env = dict(os.environ, PATH=self.shim_dir + os.pathsep + os.environ['PATH'])
        env['MISSING'] = missing
        env['TOO_OLD'] = too_old
        return subprocess.run(
            ['bash', self.script], env=env, cwd=self.dir,
            capture_output=True, text=True, timeout=60,
        )

    def test_passes_when_every_module_resolves(self):
        proc = self.run_preflight()
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn('preflight passed', proc.stdout)

    def test_missing_module_fails_and_names_the_binding(self):
        proc = self.run_preflight(missing='girepository-2.0')
        self.assertEqual(proc.returncode, 1)
        self.assertIn('PyGObject -> girepository-2.0 (not installed)',
                      proc.stderr)
        # The point of the message is that it tells the reader where the
        # package list lives; a bare "pkg-config failed" is what cost the
        # v3.5.1 job its diagnosis time.
        self.assertIn('install-build-deps.sh', proc.stderr)

    def test_too_old_module_reports_the_versions(self):
        proc = self.run_preflight(too_old='glib-2.0:2.78.0')
        self.assertEqual(proc.returncode, 1)
        self.assertIn('found 2.78.0, needs 2.80', proc.stderr)

    def test_every_module_of_every_binding_is_checked(self):
        missing = ' '.join(
            mod for mods in module_checks().values() for mod, _ in mods
        )
        proc = self.run_preflight(missing=missing)
        self.assertEqual(proc.returncode, 1)
        for binding, mods in module_checks().items():
            for mod, _ in mods:
                self.assertIn('%s -> %s' % (binding, mod), proc.stderr)


class PackageListCoversThePreflight(unittest.TestCase):

    def test_every_preflighted_module_maps_to_a_known_package(self):
        for mods in module_checks().values():
            for mod, _ in mods:
                self.assertIn(
                    mod, MODULE_TO_PACKAGE,
                    '%s is preflighted but has no Ubuntu package mapping'
                    % mod)

    def test_every_mapped_package_is_installed(self):
        installed = set(apt_list())
        needed = {MODULE_TO_PACKAGE[mod]
                  for mods in module_checks().values()
                  for mod, _ in mods}
        self.assertEqual(
            sorted(needed - installed), [],
            'build.sh needs these but install-build-deps.sh does not '
            'install them')

    def test_the_legacy_girepository_package_is_not_the_one_used(self):
        # Regression pin for the v3.5.1 failure: this name satisfies a
        # reader who glances for "girepository" and ships no .pc.
        self.assertNotIn(LEGACY_PACKAGE, apt_list())
        pygobject_modules = [mod for mod, _ in module_checks()['PyGObject']]
        self.assertIn('girepository-2.0', pygobject_modules)

    def test_the_list_carries_no_package_the_preflight_does_not_need(self):
        # Headers cost runner minutes and a false sense of coverage; a
        # package that answers no preflighted module is drift.
        needed = {MODULE_TO_PACKAGE[mod]
                  for mods in module_checks().values()
                  for mod, _ in mods}
        for pkg in apt_list():
            if pkg in ('curl', 'pkg-config') or pkg.startswith('gir1.2-'):
                continue  # downloader, probe, and runtime typelibs
            self.assertIn(pkg, needed, '%s installs nothing build.sh asks '
                                       'for' % pkg)


class WorkflowsShareOneList(unittest.TestCase):
    """Neither AppImage workflow may keep a private copy of the list."""

    def test_a_ci_job_builds_the_appimage_before_any_tag_does(self):
        # Without this job the only runner that ever builds the AppImage
        # is the one triggered by pushing a tag, which is how four
        # packaging faults reached four release attempts.
        self.assertIn('appimage', re.findall(
            r'\n  ([a-z_][a-z0-9_-]*):\n', read(CI_YML)))

    def test_the_ci_appimage_job_builds_and_checks_the_artifact(self):
        block = job_section(CI_YML, 'appimage')
        self.assertIn('./tools/appimage/build.sh', block)
        self.assertIn('build/appimage/dist/LinuxTask-x86_64.AppImage', block)

    def test_both_appimage_steps_install_through_the_script(self):
        blocks = [job_section(CI_YML, 'appimage'),
                  job_section(RELEASE_YML, 'appimage')]
        for block in blocks:
            self.assertIn('tools/appimage/install-build-deps.sh', block)
            self.assertNotIn(
                'apt-get install', block,
                'this job has its own package list again')

    def test_the_release_job_still_attaches_the_artifact_it_builds(self):
        block = job_section(RELEASE_YML, 'appimage')
        self.assertIn('build/appimage/dist/LinuxTask-x86_64.AppImage', block)
        self.assertIn('softprops/action-gh-release', block)


if __name__ == '__main__':
    unittest.main()
