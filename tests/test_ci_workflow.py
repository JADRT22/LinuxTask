# -*- coding: utf-8 -*-
"""
LinuxTask - test_ci_workflow.py
Description: Guards the GitHub workflows against the failures only a runner
             can show: a job whose interpreter is missing a system package
             the suite imports at collection time, a test that hard imports
             a distro-only binding instead of skipping, and a dependency pin
             that cannot install on an interpreter the matrix promises. All
             three came from the first runs of the redesigned CI, and none
             was visible from a machine with one Python and one Pillow.
Author: JADRT22 (https://github.com/JADRT22)
License: MIT
"""

import os
import re
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

    def test_installs_pil_imagetk(self):
        # The distribution splits Pillow in two: python3-pil has PIL, but
        # PIL.ImageTk lives in python3-pil.imagetk. Without it the
        # experimental color_spin suite errors instead of passing, and only
        # this job sees it -- a pip interpreter installs the whole wheel.
        self.assertIn('python3-pil.imagetk', self.job)

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


def _version_tuple(text):
    return tuple(int(part) for part in text.split('.'))


# What PyPI says each pinned release needs. The first entry is not theory:
# the 3.10 matrix job died in "Install dependencies" with "Could not find a
# version that satisfies the requirement evdev==2.0.0 (from versions: ...1.9.3)
# ... 2.0.0 Requires-Python >=3.11". Update this when a pin is bumped; a pin
# whose floor nobody verified is a support claim CI has to disprove.
PIN_PYTHON_FLOORS = {
    ('evdev', '2.0.0'): (3, 11),
}


class TestPinsResolveOnEveryPromisedPython(unittest.TestCase):
    """Each interpreter CI promises must be able to install the runtime pins.

    requirements.txt carried a single evdev==2.0.0, and that release declares
    Requires-Python >=3.11, so the matrix job for 3.10 died before running a
    test. Nothing local could show it: a developer machine has one interpreter
    and one resolution, and the file itself looks fine. The pins now split by
    python_version, and this checks the promise (the matrix, requires-python)
    against the pins in both files that carry them.
    """

    def setUp(self):
        self.text = read_workflow('python-app.yml')
        for attr, name in (('requirements', 'requirements.txt'),
                           ('pyproject', 'pyproject.toml')):
            with open(os.path.join(REPO, name), encoding='utf-8') as fh:
                setattr(self, attr, fh.read())

    def _matrix_versions(self):
        entry = re.search(r'python-version:\s*\[([^\]]+)\]', self.text).group(1)
        return re.findall(r'["\']([0-9.]+)["\']', entry)

    def _floor(self):
        return re.search(r'requires-python = ">=([0-9.]+)"',
                         self.pyproject).group(1)

    def _runtime_pins(self, label):
        """[(name, version, line)] the resolver can actually install.

        Comment lines restate pins to explain them, so a comment must never
        satisfy a guard. In pyproject the install source is only the
        [project] dependencies array; elsewhere that file pins build tools.
        """
        text = getattr(self, label)
        if label == 'pyproject':
            text = text.split('dependencies = [')[1].split(']')[0]
        rows = []
        for line in text.splitlines():
            if line.lstrip().startswith('#'):
                continue
            match = re.search(r'([a-zA-Z0-9_.-]+)==([0-9][0-9.]*)', line)
            if match:
                rows.append((match.group(1).lower(), match.group(2), line))
        return rows

    @staticmethod
    def _applies(line, version):
        marker = re.search(
            r"python_version\s*(>=|<=|>|<|==)\s*[\"']([0-9.]+)[\"']", line)
        if not marker:
            return True
        ops = {'>=': lambda a, b: a >= b, '>': lambda a, b: a > b,
               '<=': lambda a, b: a <= b, '<': lambda a, b: a < b,
               '==': lambda a, b: a == b}
        return ops[marker.group(1)](
            _version_tuple(version), _version_tuple(marker.group(2)))

    def test_no_pin_needs_more_than_the_floor_without_a_marker(self):
        # The bug this guards: one evdev==2.0.0 line, no marker, advertising
        # an interpreter that cannot install it.
        floor = _version_tuple(self._floor())
        for label in ('requirements', 'pyproject'):
            for name, version, line in self._runtime_pins(label):
                requires = PIN_PYTHON_FLOORS.get((name, version))
                if requires is None or requires <= floor:
                    continue
                self.assertIn(
                    'python_version', line,
                    f'{label} pins {name}=={version}, which needs python >= '
                    f'{".".join(map(str, requires))}, but the project floor is '
                    f'{self._floor()} and the line carries no marker: '
                    f'{line.strip()!r}')

    def test_every_promised_python_resolves_exactly_one_pin(self):
        # Nothing applicable is the 3.10 failure; two applicable lines let the
        # resolver choose by luck. Both files carry the pins, so both check.
        promised = list(self._matrix_versions())
        floor = self._floor()
        if floor not in promised:
            promised.append(floor)
        for label in ('requirements', 'pyproject'):
            pins = self._runtime_pins(label)
            names = sorted({name for name, _v, _l in pins})
            for version in promised:
                for name in names:
                    applicable = [line for _n, _v, line in pins
                                  if _n == name and self._applies(line, version)]
                    self.assertEqual(
                        len(applicable), 1,
                        f'{label} offers {len(applicable)} {name} pins for '
                        f'Python {version}: exactly one must apply')

    def test_the_declared_floor_has_a_ci_job(self):
        # requires-python is a support claim; with no job behind it, it is a
        # promise nobody tests.
        self.assertIn(self._floor(), self._matrix_versions(),
                      'the requires-python floor has no CI job')


class TestOptionalBindingSuites(unittest.TestCase):
    """A missing distro binding must skip, never error.

    These run the suites in a child interpreter with the module blocked,
    which is the only way to reproduce a runner that has no python3-dbus
    from a machine that does. The distributions split bindings across
    packages in ways pip never does -- python3-dbus apart from python3-gi,
    python3-pil apart from python3-pil.imagetk -- so every one of them can
    be present for the import check and missing for the attribute.
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

    def test_addon_suite_skips_without_imagetk(self):
        # python3-pil makes `import PIL` work while PIL.ImageTk still lives
        # in python3-pil.imagetk, so the add-on suite errored on the runner
        # that had only the first package. Blocking the submodule reproduces
        # exactly that half-installed state.
        proc = self._run_with_blocked_module(
            'PIL.ImageTk', 'tests/test_experimental_addons.py')
        output = proc.stdout + proc.stderr
        self.assertEqual(proc.returncode, 0, output)
        self.assertIn('skipped', output.lower(), output)
        self.assertNotIn('ImportError', output, output)


if __name__ == '__main__':
    unittest.main()
