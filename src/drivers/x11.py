import logging
import time
import os
import threading
from Xlib.display import Display
from Xlib import X
from .base import DesktopManager

logger = logging.getLogger(__name__)


class X11Driver(DesktopManager):
    """X11 desktop driver using XWarpPointer + XTest via python-xlib."""

    def __init__(self):
        super().__init__()
        self._lock = threading.RLock()
        self.display = Display(os.environ.get('DISPLAY', ':0'))
        self._root = self.display.screen().root
        self._detect_resolution()

    def _detect_resolution(self):
        screen = self.display.screen()
        self.screen_width = screen.width_in_pixels
        self.screen_height = screen.height_in_pixels
        logger.info(
            "X11 resolution detected: %dx%d",
            self.screen_width, self.screen_height
        )

    def get_cursor_pos(self):
        with self._lock:
            try:
                data = self._root.query_pointer()._data
                return int(data["root_x"]), int(data["root_y"])
            except Exception as exc:
                logger.error("get_cursor_pos failed: %s", exc)
                return 0, 0

    def _clamp(self, x, y):
        return (
            max(0, min(int(x), self.screen_width - 1)),
            max(0, min(int(y), self.screen_height - 1))
        )

    def move_cursor(self, x, y):
        with self._lock:
            try:
                cx, cy = self._clamp(x, y)
                self.display.xtest_fake_input(
                    X.MotionNotify, root=self._root.id, x=cx, y=cy
                )
                self.display.sync()
            except Exception as exc:
                logger.error("move_cursor(%d, %d) failed: %s", x, y, exc)

    def move_relative(self, dx, dy):
        with self._lock:
            try:
                real_x, real_y = self.get_cursor_pos()
                cx, cy = self._clamp(real_x + int(dx), real_y + int(dy))
                self.display.xtest_fake_input(
                    X.MotionNotify, root=self._root.id, x=cx, y=cy
                )
                self.display.sync()
                return True
            except Exception as exc:
                logger.error("move_relative(%d, %d) failed: %s", dx, dy, exc)
                return False

    def mouse_button(self, button, pressed):
        x11_btn = None
        if button == 272:
            x11_btn = 1
        elif button == 273:
            x11_btn = 3
        elif button == 274:
            x11_btn = 2
        if not x11_btn:
            return False
        with self._lock:
            try:
                event_type = X.ButtonPress if pressed else X.ButtonRelease
                self.display.xtest_fake_input(event_type, detail=x11_btn)
                self.display.sync()
                return True
            except Exception as exc:
                logger.error("mouse_button(%d, %s) failed: %s", button, pressed, exc)
                return False

    def scroll(self, direction, clicks=1):
        button = 4 if direction == 'up' else 5
        with self._lock:
            try:
                for _ in range(clicks):
                    self.display.xtest_fake_input(X.ButtonPress, detail=button)
                    self.display.xtest_fake_input(X.ButtonRelease, detail=button)
                self.display.sync()
            except Exception as exc:
                logger.error("scroll(%s, %d) failed: %s", direction, clicks, exc)

    def self_test(self):
        print("--- X11Driver Self-Test ---")
        try:
            print(f"Resolution: {self.screen_width}x{self.screen_height}")
            pos = self.get_cursor_pos()
            print(f"Current Position: {pos}")
            new_x, new_y = pos[0] + 10, pos[1] + 10
            self.move_cursor(new_x, new_y)
            print(f"Cursor moved toward: ({new_x}, {new_y})")
            time.sleep(0.1)
            new_pos = self.get_cursor_pos()
            print(f"New Position: {new_pos}")
            return True
        except Exception as exc:
            print(f"Self-Test failed: {exc}")
            return False


if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    X11Driver().self_test()
