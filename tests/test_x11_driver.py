import unittest
from unittest.mock import patch, MagicMock
import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../src')))


class TestX11Driver(unittest.TestCase):

    def _make_mock_display(self):
        display = MagicMock()
        screen = MagicMock()
        screen.width_in_pixels = 1920
        screen.height_in_pixels = 1080
        root = MagicMock()
        pointer_data = {"root_x": 100, "root_y": 200}
        root.query_pointer.return_value._data = pointer_data
        screen.root = root
        display.screen.return_value = screen
        display.xtest_fake_input = MagicMock()
        return display

    @patch('drivers.x11.Display')
    def test_detect_resolution(self, mock_display_cls):
        display = self._make_mock_display()
        mock_display_cls.return_value = display

        from drivers.x11 import X11Driver
        driver = X11Driver()
        self.assertEqual(driver.screen_width, 1920)
        self.assertEqual(driver.screen_height, 1080)

    @patch('drivers.x11.Display')
    def test_get_cursor_pos(self, mock_display_cls):
        display = self._make_mock_display()
        mock_display_cls.return_value = display

        from drivers.x11 import X11Driver
        driver = X11Driver()
        x, y = driver.get_cursor_pos()
        self.assertEqual(x, 100)
        self.assertEqual(y, 200)

    @patch('drivers.x11.Display')
    def test_move_cursor(self, mock_display_cls):
        display = self._make_mock_display()
        mock_display_cls.return_value = display

        from drivers.x11 import X11Driver
        driver = X11Driver()
        driver.move_cursor(500, 600)

        display.xtest_fake_input.assert_called_once()
        args, kwargs = display.xtest_fake_input.call_args
        from Xlib import X
        self.assertEqual(args[0], X.MotionNotify)
        self.assertEqual(kwargs.get('x'), 500)
        self.assertEqual(kwargs.get('y'), 600)
        self.assertIsNotNone(kwargs.get('root'))

    @patch('drivers.x11.Display')
    def test_move_relative(self, mock_display_cls):
        display = self._make_mock_display()
        mock_display_cls.return_value = display

        from drivers.x11 import X11Driver
        driver = X11Driver()
        # query_pointer returns (100, 200)
        result = driver.move_relative(10, -5)

        self.assertTrue(result)
        root = display.screen.return_value.root
        root.query_pointer.assert_called()
        display.xtest_fake_input.assert_called_once()
        args, kwargs = display.xtest_fake_input.call_args
        from Xlib import X
        self.assertEqual(args[0], X.MotionNotify)
        self.assertEqual(kwargs.get('x'), 110)
        self.assertEqual(kwargs.get('y'), 195)
        self.assertIsNotNone(kwargs.get('root'))

    @patch('drivers.x11.Display')
    def test_mouse_button_left(self, mock_display_cls):
        display = self._make_mock_display()
        mock_display_cls.return_value = display

        from drivers.x11 import X11Driver
        driver = X11Driver()

        result = driver.mouse_button(272, True)
        self.assertTrue(result)
        display.xtest_fake_input.assert_called_once()
        args, kwargs = display.xtest_fake_input.call_args
        from Xlib import X
        self.assertEqual(args[0], X.ButtonPress)
        self.assertEqual(kwargs.get('detail'), 1)

        display.xtest_fake_input.reset_mock()
        result = driver.mouse_button(272, False)
        self.assertTrue(result)
        args, kwargs = display.xtest_fake_input.call_args
        self.assertEqual(args[0], X.ButtonRelease)
        self.assertEqual(kwargs.get('detail'), 1)

    @patch('drivers.x11.Display')
    def test_mouse_button_right(self, mock_display_cls):
        display = self._make_mock_display()
        mock_display_cls.return_value = display

        from drivers.x11 import X11Driver
        driver = X11Driver()
        result = driver.mouse_button(273, True)
        self.assertTrue(result)
        args, kwargs = display.xtest_fake_input.call_args
        self.assertEqual(kwargs.get('detail'), 3)

    @patch('drivers.x11.Display')
    def test_mouse_button_unknown(self, mock_display_cls):
        display = self._make_mock_display()
        mock_display_cls.return_value = display

        from drivers.x11 import X11Driver
        driver = X11Driver()
        result = driver.mouse_button(999, True)
        self.assertFalse(result)

    @patch('drivers.x11.Display')
    def test_scroll_up(self, mock_display_cls):
        display = self._make_mock_display()
        mock_display_cls.return_value = display

        from drivers.x11 import X11Driver
        driver = X11Driver()
        driver.scroll('up', 3)

        self.assertEqual(display.xtest_fake_input.call_count, 6)
        calls = display.xtest_fake_input.call_args_list
        from Xlib import X
        for i in range(3):
            args_press, kwargs_press = calls[i * 2]
            self.assertEqual(args_press[0], X.ButtonPress)
            self.assertEqual(kwargs_press.get('detail'), 4)
            args_release, kwargs_release = calls[i * 2 + 1]
            self.assertEqual(args_release[0], X.ButtonRelease)
            self.assertEqual(kwargs_release.get('detail'), 4)

    @patch('drivers.x11.Display')
    def test_scroll_down(self, mock_display_cls):
        display = self._make_mock_display()
        mock_display_cls.return_value = display

        from drivers.x11 import X11Driver
        driver = X11Driver()
        driver.scroll('down', 1)

        self.assertEqual(display.xtest_fake_input.call_count, 2)
        args, kwargs = display.xtest_fake_input.call_args_list[0]
        from Xlib import X
        self.assertEqual(args[0], X.ButtonPress)
        self.assertEqual(kwargs.get('detail'), 5)


class TestAutoDetectDriver(unittest.TestCase):

    @patch('drivers.x11.Display')
    def test_cinnamon_returns_x11(self, mock_display_cls):
        display = MagicMock()
        screen = MagicMock()
        screen.width_in_pixels = 1920
        screen.height_in_pixels = 1080
        root = MagicMock()
        root.query_pointer.return_value._data = {"root_x": 0, "root_y": 0}
        screen.root = root
        display.screen.return_value = screen
        display.xtest_fake_input = MagicMock()
        mock_display_cls.return_value = display

        import os
        os.environ.pop('HYPRLAND_INSTANCE_SIGNATURE', None)
        with patch.dict(os.environ, {
            'XDG_CURRENT_DESKTOP': 'X-Cinnamon',
            'DISPLAY': ':0'
        }, clear=False):
            from drivers.factory import AutoDetectDriver
            from drivers.x11 import X11Driver
            driver = AutoDetectDriver()
            self.assertIsInstance(driver, X11Driver)


if __name__ == '__main__':
    unittest.main()
