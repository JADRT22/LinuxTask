# -*- coding: utf-8 -*-
"""
LinuxTask - test_ci_workflow.py
Description: Guards the GitHub workflows against the failures only a runner
             can show: a job whose interpreter is missing a system package
             the suite imports at collection time, and a test that hard
             imports a distro-only binding instead of skipping. Both were
             real, and both came from the first run of the redesigned CI.
Author: JADRT22 (https://github.com/JADRT22)
License: MIT
"""

import os
import subprocess
import sys
import unittest

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
WORKFLOWS = os.path.join(REPO, '.github', 'workflows')


def read_workflow(name):
    path = os.path.join(WORKFLOWS, name)
    with open(path, encoding='utf-8') as fh:
        return fh.read()


def job_block(text, job_name, next_job_name):
    """One job's YAML, from its key to the next job's key.

    Scoping the assertions keeps a package added to the wrong job from
    passing a test that means a different one.
    """
    start = text.index(f'  {job_name}:')
    end = text.index(f'  {next_job_name}:', start)
    return text[start:end]


class TestDistroBindingsJob(unittest.TestCase):
    """The only job where the distro-binding suites really run."""

    def setUp(self):
        self.job = job_block(
            read_workflow('python-app.yml'),
            'distro-bindings', 'lint',
        )

    def test_installs_python3_tk(self):
        # customtkinter imports tkinter, and the runner's distribution
        # CPython ships no _tkinter, so the job used to die during
        # collection with "Missing core dependencies". The matrix jobs do
        # not see it because actions/setup-python builds Tk in.
        self.assertIn('python3-tk', self.job)

    def test_installs_the_dbus_and_gobject_bindings(self):
        for pkg in ('python3-dbus', 'python3-gi'):
            self.assertIn(pkg, self.job)

    def test_creates_a_system_site_packages_venv(self):
        # Without this the apt-installed bindings are invisible to the venv
        # and every guarded suite skips, which would make the job useless.
        self.assertIn('--system-site-packages', self.job)


class TestMatrixJob(unittest.TestCase):

    def setUp(self):
        self.text = read_workflow('python-app.yml')

    def test_covers_every_supported_python(self):
        # requires-python in pyproject.toml promises >=3.10; a floor that
        # no job exercises is a claim, not a fact.
        for version in ('"3.10"', '"3.11"', '"3.12"', '"3.13"', '"3.14"'):
            self.assertIn(version, self.text)

    def test_still_checks_the_unittest_entry_point(self):
        # README documents `python -m unittest discover` as the no-pytest
        # path, so it has to keep working in CI and not only locally.
        self.assertIn('unittest discover', self.text)


class TestOptionalBindingSuites(unittest.TestCase):
    """A missing distro binding must skip, never error.

    These run the suites in a child interpreter with the module blocked,
    which is the only way to reproduce a runner that has no python3-dbus
    from a machine that does.
    """

    def _run_with_blocked_module(self, module, target):
        code = (
            f"import sys; sys.modules[{module!r}] = None; "
            f"import pytest; sys.exit(pytest.main(['-q', {target!r}]))"
        )
        return subprocess.run(
            [sys.executable, '-c', code],
            cwd=REPO, capture_output=True, text=True, timeout=300,
        )

    def test_contract_suite_skips_the_kde_case(self):
        proc = self._run_with_blocked_module(
            'dbus', 'tests/test_driver_contract.py')
        output = proc.stdout + proc.stderr
        self.assertEqual(proc.returncode, 0, output)
        self.assertIn('skipped', output.lower(), output)
        self.assertNotIn('ModuleNotFoundError', output, output)

    def test_kde_suite_skips_whole_module(self):
        proc = self._run_with_blocked_module(
            'dbus', 'tests/test_kde_wayland.py')
        output = proc.stdout + proc.stderr
        # 5 is pytest's "no tests were collected": the module raises
        # SkipTest at import, so nothing runs. Either way it must not be
        # an import error, which is what a hard `import dbus` produces.
        self.assertIn(proc.returncode, (0, 5), output)
        self.assertIn('skipped', output.lower(), output)
        self.assertNotIn('ModuleNotFoundError', output, output)


if __name__ == '__main__':
    unittest.main()
