import logging
import time
import os
import threading
from evdev.ecodes import BTN_LEFT, BTN_MIDDLE, BTN_RIGHT
from Xlib.display import Display
from Xlib import X
from .base import DesktopManager

logger = logging.getLogger(__name__)

# evdev button code -> X11 button number.
BTN_MAP = {BTN_LEFT: 1, BTN_RIGHT: 3, BTN_MIDDLE: 2}


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
                return None

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
                pos = self.get_cursor_pos()
                if pos is None:
                    logger.error("move_relative aborted: cursor pos unknown")
                    return False
                real_x, real_y = pos
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
        x11_btn = BTN_MAP.get(button)
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
        """Performs scroll via XTest. Returns True if handled."""
        button = 4 if direction == 'up' else 5
        with self._lock:
            try:
                for _ in range(clicks):
                    self.display.xtest_fake_input(X.ButtonPress, detail=button)
                    self.display.xtest_fake_input(X.ButtonRelease, detail=button)
                self.display.sync()
                return True
            except Exception as exc:
                logger.error("scroll(%s, %d) failed: %s", direction, clicks, exc)
                return False

    def self_test(self):
        logger.info("--- X11Driver Self-Test ---")
        try:
            logger.info("Resolution: %dx%d", self.screen_width, self.screen_height)
            pos = self.get_cursor_pos()
            if pos is None:
                logger.info("Current Position: unknown (read failed)")
                return False
            logger.info("Current Position: %s", pos)
            new_x, new_y = pos[0] + 10, pos[1] + 10
            self.move_cursor(new_x, new_y)
            logger.info("Cursor moved toward: (%d, %d)", new_x, new_y)
            time.sleep(0.1)
            new_pos = self.get_cursor_pos()
            logger.info("New Position: %s", new_pos)
            return True
        except Exception as exc:
            logger.info("Self-Test failed: %s", exc)
            return False


if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    X11Driver().self_test()
