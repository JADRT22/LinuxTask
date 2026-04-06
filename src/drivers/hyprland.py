# -*- coding: utf-8 -*-
"""
LinuxTask - hyprland.py
Description: Hyprland compositor driver using hyprctl.
Author: JADRT22 (https://github.com/JADRT22)
License: MIT
"""

import subprocess
import json
import time
import logging
from .base import DesktopManager

logger = logging.getLogger(__name__)


class HyprlandDriver(DesktopManager):
    """Hyprland compositor driver using hyprctl."""

    def __init__(self):
        super().__init__()
        self._detect_resolution()

    def _detect_resolution(self):
        """Populates screen resolution via hyprctl monitors."""
        try:
            out = subprocess.check_output(
                ["hyprctl", "monitors", "-j"],
                stderr=subprocess.DEVNULL
            ).decode().strip()
            monitors = json.loads(out)
            if monitors:
                focused = next(
                    (m for m in monitors if m.get("focused")),
                    monitors[0]
                )
                self.screen_width = int(focused.get("width", 0))
                self.screen_height = int(focused.get("height", 0))
                logger.info(
                    "Hyprland resolution: %dx%d",
                    self.screen_width, self.screen_height
                )
                return
        except (subprocess.CalledProcessError, FileNotFoundError,
                json.JSONDecodeError) as exc:
            logger.warning("hyprctl monitors failed: %s", exc)

        self.screen_width, self.screen_height = 1920, 1080
        logger.warning("Using fallback resolution: 1920x1080")

    def get_cursor_pos(self):
        """Returns current (x, y) coordinates via hyprctl."""
        try:
            out = subprocess.check_output(
                ["hyprctl", "cursorpos"],
                stderr=subprocess.DEVNULL
            ).decode().strip()
            x, y = out.split(", ")
            return int(x), int(y)
        except (subprocess.CalledProcessError, FileNotFoundError,
                ValueError) as exc:
            logger.error("get_cursor_pos failed: %s", exc)
            return 0, 0

    def move_cursor(self, x, y):
        """Moves cursor to absolute coordinates."""
        try:
            subprocess.run(
                ["hyprctl", "dispatch", "movecursor", f"{x} {y}"],
                capture_output=True, check=True
            )
        except subprocess.CalledProcessError as exc:
            logger.error("move_cursor(%d, %d) failed: %s", x, y, exc)

    def move_relative(self, dx, dy):
        """Moves cursor by relative offset via hyprctl."""
        try:
            pos = self.get_cursor_pos()
            new_x = max(0, min(pos[0] + dx, self.screen_width - 1))
            new_y = max(0, min(pos[1] + dy, self.screen_height - 1))
            self.move_cursor(new_x, new_y)
            return True
        except Exception as exc:
            logger.error("move_relative(%d, %d) failed: %s", dx, dy, exc)
            return False

    def scroll(self, direction, clicks=1):
        """Performs scroll via hyprctl dispatch."""
        try:
            # Hyprland doesn't have native scroll dispatch;
            # use the virtual UInput from main.py instead.
            # This is a no-op placeholder — scroll is handled by UInput.
            logger.debug(
                "Hyprland scroll (%s, %d) — handled by UInput.",
                direction, clicks
            )
        except Exception as exc:
            logger.error("scroll failed: %s", exc)

    def self_test(self):
        """Performs driver verification."""
        print("--- HyprlandDriver Self-Test ---")
        try:
            subprocess.check_call(
                "command -v hyprctl >/dev/null 2>&1", shell=True
            )
            print("hyprctl found.")
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
            print("Error: hyprctl command not found.")
            return False
        except Exception as exc:
            print(f"Self-Test failed: {exc}")
            return False


if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    HyprlandDriver().self_test()
