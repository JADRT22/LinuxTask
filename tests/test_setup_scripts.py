# -*- coding: utf-8 -*-
"""
LinuxTask - test_setup_scripts.py
Description: Locks the invariants of the shell scripts in tools/.
             They run with the user's sudo and, before this suite existed,
             could silently grow back behaviours that were deliberately
             removed (installing packages at app start, eval-expanding a
             username as root).
Author: JADRT22 (https://github.com/JADRT22)
License: MIT
"""

import os
import re
import unittest

REPO = os.path.abspath(
    os.path.join(os.path.dirname(__file__), '..')
)
TOOLS = os.path.join(REPO, 'tools')


def read_script(name):
    path = os.path.join(TOOLS, name)
    with open(path, encoding='utf-8') as fh:
        return fh.read()


def code_only(name):
    """Script text with whole-line comments dropped.

    The scripts explain, in comments, the constructs they deliberately
    avoid; only the executable lines are held to the rules below.
    """
    return '\n'.join(
        line for line in read_script(name).splitlines()
        if not line.lstrip().startswith('#')
    )


class RunScriptDoesNotInstall(unittest.TestCase):
    """Launching the app must never fetch or build code from the network."""

    def test_no_pip_install(self):
        source = code_only('run.sh')
        offenders = [
            line.strip() for line in source.splitlines()
            if re.search(r'\bpip3?(?:\s+\S+)*\s+install\b', line)
        ]
        self.assertEqual(
            offenders, [],
            'run.sh must not install dependencies at startup; the user '
            'clicks a menu entry, they do not expect a package fetch. '
            'Setup belongs in tools/install.sh.')

    def test_missing_deps_point_at_installer(self):
        source = read_script('run.sh')
        self.assertIn('import customtkinter, evdev, Xlib', source)
        self.assertIn('./tools/install.sh', source)
        # The guard has to abort, not fall through to exec main.py.
        guard = source[source.index('import customtkinter, evdev, Xlib'):]
        guard = guard[:guard.index('src/main.py')]
        self.assertIn('exit 1', guard)

    def test_still_forwards_arguments_to_main(self):
        source = read_script('run.sh')
        self.assertIn('exec "$PYTHON_BIN" src/main.py "$@"', source)


class NoEvalOnTheRealUserName(unittest.TestCase):
    """install/uninstall run under pkexec; the username must not be
    re-expanded by the shell."""

    def test_no_eval_echo(self):
        for name in ('install.sh', 'uninstall.sh', 'run.sh'):
            self.assertNotIn(
                'eval echo', code_only(name),
                '%s must read the home directory from the passwd database '
                'instead of `eval echo ~$USER`.' % name)

    def test_home_comes_from_getent(self):
        for name in ('install.sh', 'uninstall.sh'):
            source = code_only(name)
            self.assertIn(
                'getent passwd "$REAL_USER"', source,
                '%s should resolve $REAL_USER through getent.' % name)
            self.assertIn('cut -d: -f6', source)


class GnomeReplayToolsAreInstalled(unittest.TestCase):
    """The GNOME Wayland driver shells out to ydotool/ydotoold; the
    installer used to leave that to the user with no message."""

    def test_ydotool_helper_exists_and_runs(self):
        source = read_script('install.sh')
        self.assertIn('install_ydotool_if_gnome()', source)
        self.assertRegex(
            source, r'(?m)^install_ydotool_if_gnome \|\| true$',
            'the helper must actually be called (best-effort) after the '
            'distro bindings step')

    def test_gnome_only_and_checks_both_binaries(self):
        source = read_script('install.sh')
        body = source[source.index('install_ydotool_if_gnome() {'):]
        body = body[:body.index('\n}')]
        self.assertIn('grep -qi gnome', body)
        for binary in ('ydotool', 'ydotoold'):
            self.assertIn(binary, body)

    def test_no_other_desktop_is_forced_to_install_it(self):
        source = read_script('install.sh')
        body = source[source.index('install_ydotool_if_gnome() {'):]
        body = body[:body.index('\n}')]
        # Non-GNOME desktops return before touching the package manager.
        self.assertLess(
            body.index('grep -qi gnome'), body.index('detect_pkg_manager'))


class InstallerKeepsItsPromises(unittest.TestCase):
    """Small structural checks: the pieces README/CONTRIBUTING document."""

    def test_venv_is_system_site_packages(self):
        source = read_script('install.sh')
        self.assertIn('-m venv --system-site-packages', source)

    def test_pins_come_from_requirements(self):
        source = read_script('install.sh')
        self.assertIn('install -r "$REPO_ROOT/requirements.txt"', source)

    def test_udev_reload_is_fatal_on_failure(self):
        source = read_script('install.sh')
        self.assertIn(
            'udevadm control --reload-rules || fail', source)
        self.assertIn('udevadm trigger || fail', source)


if __name__ == '__main__':
    unittest.main()
