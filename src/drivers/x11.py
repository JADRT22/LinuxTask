# -*- coding: utf-8 -*-
"""
LinuxTask - x11.py
Description: X11 compositor driver (Cinnamon, MATE, XFCE, etc.) using xdotool.
Author: JADRT22 (https://github.com/JADRT22)
License: MIT
"""

import subprocess
import shutil
import time
import logging
from .base import DesktopManager

logger = logging.getLogger(__name__)


class X11Driver(DesktopManager):
    """X11 desktop driver using xdotool for cursor control."""

    def __init__(self):
        super().__init__()
        self._validate_dependencies()
        self._detect_resolution()

    def _validate_dependencies(self):
        """Checks that xdotool is available on the system."""
        if not shutil.which('xdotool'):
            raise RuntimeError(
                "xdotool not found. Install it with: "
                "sudo apt install xdotool"
            )

    def _detect_resolution(self):
        """Detects screen resolution via xrandr."""
        try:
            out = subprocess.check_output(
                ['xrandr'], stderr=subprocess.STDOUT
            ).decode()
            for line in out.splitlines():
                if '*' in line:
                    res = line.split()[0]
                    w, h = res.split('x')
                    self.screen_width = int(w)
                    self.screen_height = int(h)
                    logger.info(
                        "X11 resolution detected: %dx%d",
                        self.screen_width, self.screen_height
                    )
                    return
        except (subprocess.CalledProcessError, FileNotFoundError) as exc:
            logger.warning("xrandr failed: %s", exc)

        # Fallback
        self.screen_width, self.screen_height = 1920, 1080
        logger.warning(
            "Using fallback resolution: %dx%d",
            self.screen_width, self.screen_height
        )

    def get_cursor_pos(self):
        """Returns current (x, y) cursor coordinates via xdotool."""
        try:
            out = subprocess.check_output(
                ['xdotool', 'getmouselocation'], stderr=subprocess.DEVNULL
            ).decode().strip()
            # Output format: x:123 y:456 screen:0 window:12345678
            parts = dict(
                p.split(':') for p in out.split()
                if ':' in p
            )
            return int(parts['x']), int(parts['y'])
        except (subprocess.CalledProcessError, KeyError, ValueError) as exc:
            logger.error("get_cursor_pos failed: %s", exc)
            return 0, 0

    def move_cursor(self, x, y):
        """Moves cursor to absolute (x, y) coordinates."""
        try:
            subprocess.run(
                ['xdotool', 'mousemove', str(int(x)), str(int(y))],
                capture_output=True, check=True
            )
        except subprocess.CalledProcessError as exc:
            logger.error("move_cursor(%d, %d) failed: %s", x, y, exc)

    def move_relative(self, dx, dy):
        """Moves cursor by relative (dx, dy) offset."""
        # Return False to use the superior uinput hardware integration instead
        # This fixes coordinate inaccuracies related to X server mouse scaling
        return False

    def mouse_button(self, button, pressed):
        """Handles mouse button press/release via xdotool."""
        x11_btn = None
        # Maps evdev BTN codes to X11 button codes
        # 272 = BTN_LEFT, 273 = BTN_RIGHT, 274 = BTN_MIDDLE
        if button == 272:
            x11_btn = '1'
        elif button == 273:
            x11_btn = '3'
        elif button == 274:
            x11_btn = '2'

        if not x11_btn:
            return False  # Not a standard mouse button, let UInput try it

        action = 'mousedown' if pressed else 'mouseup'
        try:
            subprocess.run(
                ['xdotool', action, x11_btn],
                capture_output=True, check=True
            )
            return True
        except subprocess.CalledProcessError as exc:
            logger.error("x11 mouse_button(%s, %s) failed: %s", button, action, exc)
            return False

    def scroll(self, direction, clicks=1):
        """Performs scroll action. direction: 'up' or 'down'."""
        button = '4' if direction == 'up' else '5'
        try:
            subprocess.run(
                ['xdotool', 'click', '--repeat', str(clicks), button],
                capture_output=True, check=True
            )
        except subprocess.CalledProcessError as exc:
            logger.error("scroll(%s, %d) failed: %s", direction, clicks, exc)

    def self_test(self):
        """Performs driver verification."""
        print("--- X11Driver Self-Test ---")
        try:
            subprocess.check_call(
                "command -v xdotool >/dev/null 2>&1", shell=True
            )
            print("xdotool found.")
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
        except subprocess.CalledProcessError:
            print("Error: xdotool command not found.")
            return False
        except Exception as exc:
            print(f"Self-Test failed: {exc}")
            return False


if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    X11Driver().self_test()
