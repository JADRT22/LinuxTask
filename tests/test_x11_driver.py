# -*- coding: utf-8 -*-
"""
LinuxTask - test_x11_driver.py
Description: X11 driver behaviour against a mocked python-xlib Display,
             plus the factory's choice of driver on an X11 session.
Author: JADRT22 (https://github.com/JADRT22)
License: MIT
"""

import os
import unittest
from unittest.mock import MagicMock, patch

from Xlib import X

from drivers.x11 import X11Driver


def mock_display(width=1920, height=1080, pointer=(100, 200)):
    """A python-xlib Display stand-in: one screen, one pointer."""
    display = MagicMock()
    screen = MagicMock()
    screen.width_in_pixels = width
    screen.height_in_pixels = height
    root = MagicMock()
    root.query_pointer.return_value._data = {
        'root_x': pointer[0], 'root_y': pointer[1]}
    screen.root = root
    display.screen.return_value = screen
    return display


class X11TestCase(unittest.TestCase):
    """One patched Display and one driver per test, built in setUp."""

    def setUp(self):
        patcher = patch('drivers.x11.Display')
        self.addCleanup(patcher.stop)
        self.display_cls = patcher.start()
        self.display = mock_display()
        self.display_cls.return_value = self.display
        self.driver = X11Driver()

    def xtest_calls(self):
        """Every xtest_fake_input() call the driver has made so far."""
        return self.display.xtest_fake_input.call_args_list


class TestX11Driver(X11TestCase):

    def test_driver_connects_to_the_display_once(self):
        self.display_cls.assert_called_once()

    def test_detect_resolution(self):
        self.assertEqual(self.driver.screen_width, 1920)
        self.assertEqual(self.driver.screen_height, 1080)

    def test_detected_resolution_becomes_the_clamping_box(self):
        # Playback warps inside this box; leaving it unset would clip a
        # coordinate that X11 itself accepts.
        self.assertEqual(self.driver.bounds, (0, 0, 1920, 1080))

    def test_get_cursor_pos(self):
        self.assertEqual(self.driver.get_cursor_pos(), (100, 200))

    def test_move_cursor(self):
        self.assertTrue(self.driver.move_cursor(500, 600))

        call = self.xtest_calls()[-1]
        self.assertEqual(call.args[0], X.MotionNotify)
        self.assertEqual(call.kwargs.get('x'), 500)
        self.assertEqual(call.kwargs.get('y'), 600)
        self.assertIsNotNone(call.kwargs.get('root'))

    def test_move_cursor_clamps_to_the_last_reachable_pixel(self):
        # The upper edge is exclusive, and True means "the compositor did
        # it" — answering False here would make playback warp a second
        # virtual device on top of a move that already happened.
        self.assertTrue(self.driver.move_cursor(5000, 600))
        call = self.xtest_calls()[-1]
        self.assertEqual(call.kwargs.get('x'), 1919)
        self.assertEqual(call.kwargs.get('y'), 600)

    def test_move_cursor_reports_failure_as_false_not_none(self):
        self.display.xtest_fake_input.side_effect = Exception('X error')
        self.assertIs(self.driver.move_cursor(10, 10), False)

    def test_move_relative(self):
        self.assertTrue(self.driver.move_relative(10, -5))

        self.display.screen.return_value.root.query_pointer.assert_called()
        call = self.xtest_calls()[-1]
        self.assertEqual(call.args[0], X.MotionNotify)
        self.assertEqual(call.kwargs.get('x'), 110)
        self.assertEqual(call.kwargs.get('y'), 195)

    def test_move_relative_falls_back_when_the_pointer_is_unknown(self):
        # get_cursor_pos() -> None is the documented "the compositor
        # cannot say" answer; move_relative has to answer False so that
        # playback uses the UInput device instead of a stale position.
        self.display.screen.return_value.root.query_pointer.side_effect = \
            Exception('X error')
        self.assertIsNone(self.driver.get_cursor_pos())
        self.assertIs(self.driver.move_relative(10, 10), False)
        self.display.xtest_fake_input.assert_not_called()

    def test_mouse_button_left(self):
        self.assertTrue(self.driver.mouse_button(272, True))
        press = self.xtest_calls()[-1]
        self.assertEqual(press.args[0], X.ButtonPress)
        self.assertEqual(press.kwargs.get('detail'), 1)

        self.assertTrue(self.driver.mouse_button(272, False))
        release = self.xtest_calls()[-1]
        self.assertEqual(release.args[0], X.ButtonRelease)
        self.assertEqual(release.kwargs.get('detail'), 1)

    def test_mouse_button_right(self):
        self.assertTrue(self.driver.mouse_button(273, True))
        self.assertEqual(self.xtest_calls()[-1].kwargs.get('detail'), 3)

    def test_mouse_button_unknown(self):
        self.assertFalse(self.driver.mouse_button(999, True))
        self.display.xtest_fake_input.assert_not_called()

    def test_scroll_up(self):
        self.driver.scroll('up', 3)

        calls = self.xtest_calls()
        self.assertEqual(len(calls), 6)
        for i in range(3):
            press, release = calls[i * 2], calls[i * 2 + 1]
            self.assertEqual(press.args[0], X.ButtonPress)
            self.assertEqual(press.kwargs.get('detail'), 4)
            self.assertEqual(release.args[0], X.ButtonRelease)
            self.assertEqual(release.kwargs.get('detail'), 4)

    def test_scroll_down(self):
        self.driver.scroll('down', 1)

        calls = self.xtest_calls()
        self.assertEqual(len(calls), 2)
        self.assertEqual(calls[0].args[0], X.ButtonPress)
        self.assertEqual(calls[0].kwargs.get('detail'), 5)

    def test_self_test_reports_failure_when_the_read_fails(self):
        # self_test() backs the diagnostic output; a broken pointer read
        # must answer False instead of raising through the CLI.
        self.display.screen.return_value.root.query_pointer.side_effect = \
            Exception('X error')
        self.assertFalse(self.driver.self_test())


class TestX11DriverDisplaySelection(unittest.TestCase):
    """The socket comes from DISPLAY, with ':0' as the documented default."""

    def build(self, env):
        with patch.dict(os.environ, env, clear=True), \
                patch('drivers.x11.Display') as display_cls:
            display_cls.return_value = mock_display()
            driver = X11Driver()
        return driver, display_cls

    def test_display_from_the_environment_is_used(self):
        _, display_cls = self.build({'DISPLAY': ':1'})
        display_cls.assert_called_once_with(':1')

    def test_missing_display_falls_back_to_zero(self):
        _, display_cls = self.build({})
        display_cls.assert_called_once_with(':0')

    def test_driver_attribute_holds_the_open_display(self):
        driver, display_cls = self.build({'DISPLAY': ':2'})
        self.assertIs(driver.display, display_cls.return_value)


class TestAutoDetectDriver(unittest.TestCase):

    def test_cinnamon_returns_x11(self):
        # clear=True on purpose: a HYPRLAND_INSTANCE_SIGNATURE or SWAYSOCK
        # leaking in from the developer's own session used to decide which
        # driver this test actually proved.
        with patch.dict(os.environ, {
                'XDG_CURRENT_DESKTOP': 'X-Cinnamon',
                'XDG_SESSION_TYPE': 'x11',
                'DISPLAY': ':0'}, clear=True), \
                patch('drivers.x11.Display') as display_cls:
            display_cls.return_value = mock_display(pointer=(0, 0))
            from drivers.factory import AutoDetectDriver
            driver = AutoDetectDriver()
        self.assertIsInstance(driver, X11Driver)

    def test_gnome_wayland_does_not_build_an_x11_driver(self):
        with patch.dict(os.environ, {
                'XDG_CURRENT_DESKTOP': 'GNOME',
                'XDG_SESSION_TYPE': 'wayland',
                'WAYLAND_DISPLAY': 'wayland-0',
                'DISPLAY': ':0'}, clear=True), \
                patch('drivers.gnome.GnomeDriver.__init__',
                      return_value=None) as gnome_init, \
                patch('drivers.x11.Display') as x11_display:
            from drivers.factory import AutoDetectDriver
            AutoDetectDriver()
        gnome_init.assert_called_once()
        x11_display.assert_not_called()


if __name__ == '__main__':
    unittest.main()
