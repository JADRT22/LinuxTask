# -*- coding: utf-8 -*-
"""
LinuxTask - test_kde_wayland.py
Description: Headless tests for the KDE Wayland portal driver (portal and
             DBus init mocked out): clicks must reach the portal as evdev
             button codes 272/273/274, per the RemoteDesktop portal spec,
             and skipped input must surface as WARNING + a UI notice.
Author: JADRT22 (https://github.com/JADRT22)
License: MIT
"""

import os
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../src')))

import dbus

from drivers.kde_wayland import (  # noqa: E402
    BTN_MAP,
    _KWIN_SCRIPT_NAME as KWIN_SCRIPT_NAME,
    KdeWaylandDriver,
)


def make_driver(portal_ready=True):
    """Driver with DBus/portal init patched out and a mock portal."""
    with patch.object(KdeWaylandDriver, '_detect_resolution'), \
            patch.object(KdeWaylandDriver, '_portal_init'):
        driver = KdeWaylandDriver()
    driver._portal = MagicMock()
    driver._portal_ready = portal_ready
    driver._session_handle = "/org/freedesktop/portal/desktop/session/1"
    return driver


class TestKdeWaylandButtons(unittest.TestCase):

    def test_map_is_evdev_codes(self):
        self.assertEqual(BTN_MAP, {272: 272, 273: 273, 274: 274})

    def test_mouse_button_sends_evdev_code_to_portal(self):
        driver = make_driver()
        for code in (272, 273, 274):
            self.assertTrue(driver.mouse_button(code, True))
            args = driver._portal.NotifyPointerButton.call_args.args
            self.assertEqual(args[2], code, "portal must get the evdev code")
            self.assertEqual(args[3], 1)
        self.assertTrue(driver.mouse_button(272, False))
        self.assertEqual(
            driver._portal.NotifyPointerButton.call_args.args[3], 0)

    def test_unknown_button_is_declined(self):
        driver = make_driver()
        self.assertFalse(driver.mouse_button(999, True))
        driver._portal.NotifyPointerButton.assert_not_called()

    def test_portal_not_ready_warns_and_declines(self):
        driver = make_driver(portal_ready=False)
        with self.assertLogs('drivers.kde_wayland', level='WARNING') as logs:
            self.assertFalse(driver.mouse_button(272, True))
            self.assertFalse(driver.move_cursor(10, 20))
            self.assertFalse(driver.move_relative(1, 1))
            self.assertFalse(driver.scroll('down'))
        self.assertTrue(any('not ready' in m for m in logs.output))
        driver._portal.NotifyPointerButton.assert_not_called()

    def test_failed_portal_call_warns_and_declines(self):
        driver = make_driver()
        driver._portal.NotifyPointerButton.side_effect = RuntimeError('boom')
        with self.assertLogs('drivers.kde_wayland', level='WARNING') as logs:
            self.assertFalse(driver.mouse_button(272, True))
        self.assertTrue(any('failed' in m for m in logs.output))

    def test_warns_only_once_per_reason(self):
        driver = make_driver(portal_ready=False)
        with self.assertLogs('drivers.kde_wayland', level='WARNING') as logs:
            driver.mouse_button(272, True)
        self.assertEqual(len(logs.output), 1)
        # Repeats are demoted to DEBUG so long macros do not flood the log.
        with self.assertLogs('drivers.kde_wayland', level='DEBUG') as logs2:
            driver.mouse_button(272, True)
        self.assertEqual(len(logs2.output), 1)


class TestKdeWaylandVisibility(unittest.TestCase):
    """Skip points must log a WARNING and register one UI notice."""

    def test_portal_not_ready_warns_and_registers_ui_notice(self):
        driver = make_driver(portal_ready=False)
        notices = []
        driver.warn_fn = notices.append
        with self.assertLogs('drivers.kde_wayland', level='WARNING') as logs:
            self.assertFalse(driver.move_cursor(10, 20))
        self.assertTrue(any('not ready' in m for m in logs.output))
        self.assertEqual(len(notices), 1)
        self.assertIn('not ready', notices[0])
        # Repeats of the same reason must not queue another notice.
        self.assertFalse(driver.move_cursor(30, 40))
        self.assertEqual(len(notices), 1)

    def test_failed_mouse_call_warns_and_registers_ui_notice(self):
        driver = make_driver()
        driver._portal.NotifyPointerButton.side_effect = RuntimeError('boom')
        notices = []
        driver.warn_fn = notices.append
        with self.assertLogs('drivers.kde_wayland', level='WARNING') as logs:
            self.assertFalse(driver.mouse_button(272, True))
        self.assertTrue(any('failed' in m for m in logs.output))
        self.assertEqual(len(notices), 1)
        self.assertIn('failed', notices[0])


def make_kwin_driver(load_result=7, probe_payload='123,456',
                     wait_result=True):
    """Driver with the KWin cursor-read plumbing pre-wired to mocks
    (no real D-Bus in tests): scripting interface, probe and script
    path are MagicModels so every read path is exercised offline."""
    driver = make_driver()
    driver._bus = MagicMock()
    driver._dbus_loop = MagicMock()
    driver._kwin_ready = True
    driver._kwin_scripting = MagicMock()
    driver._kwin_scripting.loadScript.return_value = load_result
    driver._kwin_script_path = '/tmp/fake.js'
    driver._kwin_probe = MagicMock()
    driver._kwin_probe.wait.return_value = wait_result
    driver._kwin_probe.payload.return_value = probe_payload
    return driver


def mock_xdotool(x=5, y=6):
    """Patch the xdotool read to return a known position (bytes, as
    subprocess.check_output would)."""
    return patch('drivers.kde_wayland.subprocess.check_output',
                 return_value=f'x:{x} y:{y} screen:0 window:9'.encode())


class TestKdeWaylandCursorRead(unittest.TestCase):
    """KWin scripting read (kdotool mechanism): exact position source,
    with xdotool as fallback. All D-Bus is mocked out."""

    def test_kwin_read_parses_payload(self):
        driver = make_kwin_driver(probe_payload='123,456')
        self.assertEqual(driver._kwin_cursor_pos(), (123, 456))
        driver._kwin_scripting.loadScript.assert_called_with(
            '/tmp/fake.js', KWIN_SCRIPT_NAME, signature='ss')
        driver._kwin_probe.reset.assert_called_once()
        driver._kwin_probe.wait.assert_called_once_with(2.0)

    def test_load_script_failure_falls_back_to_xdotool(self):
        driver = make_kwin_driver(load_result=-1)
        with mock_xdotool(5, 6):
            self.assertEqual(driver.get_cursor_pos(), (5, 6))
        # The -1 load must trigger the stale-script recovery unload.
        self.assertTrue(driver._kwin_scripting.unloadScript.called)

    def test_timeout_unloads_script_and_falls_back(self):
        driver = make_kwin_driver(wait_result=False)
        self.assertIsNone(driver._kwin_cursor_pos())
        # Even on timeout the script must be unloaded (no leak).
        driver._kwin_scripting.unloadScript.assert_called_with(
            KWIN_SCRIPT_NAME)
        with mock_xdotool(8, 9):
            self.assertEqual(driver.get_cursor_pos(), (8, 9))

    def test_kwin_absent_falls_back_and_never_raises(self):
        # No plumbing at all (bus/loop absent): setup bails out.
        driver = make_driver()
        self.assertIsNone(driver._kwin_cursor_pos())
        with mock_xdotool(1, 2):
            self.assertEqual(driver.get_cursor_pos(), (1, 2))
        # KWin scripting raising mid-read must also degrade cleanly.
        driver = make_kwin_driver()
        driver._kwin_scripting.loadScript.side_effect = RuntimeError('boom')
        with mock_xdotool(3, 4):
            self.assertEqual(driver.get_cursor_pos(), (3, 4))

    def test_sequential_reads_do_not_collide_on_script_name(self):
        driver = make_kwin_driver()
        self.assertEqual(driver._kwin_cursor_pos(), (123, 456))
        self.assertEqual(driver._kwin_cursor_pos(), (123, 456))
        # Same name both times, and unloaded after each read, so the
        # second load can never collide with a leftover script.
        load_calls = driver._kwin_scripting.loadScript.call_args_list
        self.assertEqual(len(load_calls), 2)
        self.assertEqual(load_calls[0], load_calls[1])
        self.assertEqual(
            driver._kwin_scripting.unloadScript.call_count, 2)

    def test_kwin_is_primary_over_xdotool(self):
        driver = make_kwin_driver(probe_payload='40,50')
        with mock_xdotool(5, 6) as mock_out:
            self.assertEqual(driver.get_cursor_pos(), (40, 50))
            mock_out.assert_not_called()

    def test_sync_tracked_pos_uses_kwin(self):
        driver = make_kwin_driver(probe_payload='11,22')
        driver._sync_tracked_pos()
        self.assertEqual((driver._cur_x, driver._cur_y), (11, 22))
        self.assertTrue(driver._pos_initialized)

    def test_setup_partial_failure_is_retryable(self):
        # Scripting stage fails after the probe/temp file were built:
        # the next attempt must reuse them (no re-registration error)
        # and fail clean again instead of raising or half-succeeding.
        driver = make_driver()
        driver._bus = MagicMock()
        driver._dbus_loop = MagicMock()
        driver._bus.request_name.return_value = (
            dbus.bus.REQUEST_NAME_REPLY_PRIMARY_OWNER)
        with patch('drivers.kde_wayland._KwinCursorProbe'), \
                patch('drivers.kde_wayland.dbus.Interface'):
            driver._bus.get_object.side_effect = RuntimeError('no KWin')
            self.assertFalse(driver._kwin_read_setup())
            self.assertFalse(driver._kwin_ready)
            self.assertFalse(driver._kwin_read_setup())
        self.assertEqual(driver._bus.request_name.call_count, 1)
        driver._kwin_cleanup()  # unlink the temp file the setup created

    def test_temp_script_write_failure_leaves_no_orphan(self):
        # ENOSPC / fdopen failure in the temp-script stage: setup is
        # retried on every read, so the mkstemp file must be unlinked
        # (and its fd closed when fdopen itself raised) instead of
        # leaking one file per cursor read.
        driver = make_driver()
        driver._bus = MagicMock()
        driver._dbus_loop = MagicMock()
        driver._bus.request_name.return_value = (
            dbus.bus.REQUEST_NAME_REPLY_PRIMARY_OWNER)
        real_mkstemp = tempfile.mkstemp
        seen = {}

        def tracking_mkstemp(*args, **kwargs):
            fd, path = real_mkstemp(*args, **kwargs)
            seen['fd'], seen['path'] = fd, path
            return fd, path

        with patch('drivers.kde_wayland.tempfile.mkstemp',
                   side_effect=tracking_mkstemp), \
                patch('drivers.kde_wayland.os.fdopen',
                      side_effect=OSError('no space left on device')), \
                patch('drivers.kde_wayland._KwinCursorProbe'):
            self.assertFalse(driver._kwin_read_setup())
        self.assertFalse(driver._kwin_ready)
        # No orphan temp file and no leaked descriptor.
        self.assertFalse(os.path.exists(seen['path']))
        with self.assertRaises(OSError):
            os.fstat(seen['fd'])
        self.assertIsNone(driver._kwin_script_path)
        # The read must fall back instead of raising; the probe stage
        # bails fast again, so no new temp file appears.
        driver._kwin_probe = None
        driver._bus.request_name.return_value = (
            dbus.bus.REQUEST_NAME_REPLY_IN_QUEUE)
        with mock_xdotool(7, 8):
            self.assertEqual(driver.get_cursor_pos(), (7, 8))

    def test_repeated_timeouts_degrade_and_recover(self):
        # After 3 consecutive timeouts every read would otherwise stall
        # the full 2 s wait; the driver must skip KWin for 8 reads, then
        # probe once (a failed probe restarts the window), and a success
        # must re-enable normal KWin reads.
        driver = make_kwin_driver(wait_result=False)
        for _ in range(3):
            self.assertIsNone(driver._kwin_cursor_pos())
        self.assertEqual(driver._kwin_probe.wait.call_count, 3)
        # Skip window: no KWin attempt, so no 2 s stall.
        for _ in range(8):
            self.assertIsNone(driver._kwin_cursor_pos())
        self.assertEqual(driver._kwin_probe.wait.call_count, 3)
        # Window over: one probe attempt, which fails -> new window.
        self.assertIsNone(driver._kwin_cursor_pos())
        self.assertEqual(driver._kwin_probe.wait.call_count, 4)
        for _ in range(8):
            self.assertIsNone(driver._kwin_cursor_pos())
        self.assertEqual(driver._kwin_probe.wait.call_count, 4)
        # Success resets the streak and re-enables KWin immediately.
        driver._kwin_probe.wait.return_value = True
        self.assertEqual(driver._kwin_cursor_pos(), (123, 456))
        self.assertEqual(driver._kwin_probe.wait.call_count, 5)
        driver._kwin_probe.wait.return_value = False
        self.assertIsNone(driver._kwin_cursor_pos())
        self.assertEqual(driver._kwin_probe.wait.call_count, 6)

    def test_request_name_not_primary_fails_fast(self):
        # Name owned by another process: setup must bail out without
        # queueing (no 2 s stall on every read).
        driver = make_driver()
        driver._bus = MagicMock()
        driver._dbus_loop = MagicMock()
        driver._bus.request_name.return_value = (
            dbus.bus.REQUEST_NAME_REPLY_IN_QUEUE)
        self.assertFalse(driver._kwin_read_setup())
        self.assertFalse(driver._kwin_ready)
        driver._bus.get_object.assert_not_called()

    def test_kwin_failure_warns_once_via_warn_fn(self):
        driver = make_kwin_driver()
        driver._kwin_scripting.loadScript.side_effect = RuntimeError('boom')
        notices = []
        driver.warn_fn = notices.append
        with mock_xdotool(5, 6):
            self.assertEqual(driver.get_cursor_pos(), (5, 6))
            self.assertEqual(driver.get_cursor_pos(), (5, 6))
        self.assertEqual(len(notices), 1)
        self.assertIn('falling back to xdotool', notices[0])

    def test_all_sources_fail_returns_tracked_tuple_never_none(self):
        # KWin absent AND xdotool dead: the recorder relies on a real
        # tuple (guards `is None` separately), so this must never be None.
        driver = make_driver()  # no bus/loop: KWin setup bails out
        driver._pos_initialized = False
        with patch('drivers.kde_wayland.subprocess.check_output',
                   side_effect=OSError('no xdotool')):
            pos = driver.get_cursor_pos()
        self.assertIsInstance(pos, tuple)
        self.assertEqual(len(pos), 2)

    def test_cleanup_unlinks_temp_script_file(self):
        driver = make_kwin_driver()
        fd, path = tempfile.mkstemp(suffix='.js', prefix='test_cursor_')
        with os.fdopen(fd, 'w') as f:
            f.write('// test')
        driver._kwin_script_path = path
        driver._kwin_cleanup()
        self.assertFalse(os.path.exists(path))


if __name__ == '__main__':
    unittest.main()
