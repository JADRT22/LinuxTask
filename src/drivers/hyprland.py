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
        """Returns current (x, y) coordinates via hyprctl.

        Unlike xdotool-on-XWayland, hyprctl reports synthetic moves
        back truthfully, so this is safe to call between moves.
        """
        try:
            out = subprocess.check_output(
                ["hyprctl", "cursorpos"],
                stderr=subprocess.DEVNULL
            ).decode().strip()
            x, y = [p.strip() for p in out.split(",")]
            return int(x), int(y)
        except (subprocess.CalledProcessError, FileNotFoundError,
                ValueError) as exc:
            logger.error("get_cursor_pos failed: %s", exc)
            return 0, 0

    def _clamp(self, x, y):
        return (
            max(0, min(int(x), self.screen_width - 1)),
            max(0, min(int(y), self.screen_height - 1))
        )

    def move_cursor(self, x, y):
        """Moves cursor to absolute coordinates.

        Hyprland >= 0.55 uses Lua dispatchers
        (hl.dsp.cursor.move); older releases use the legacy
        'dispatch movecursor X Y' form. Try new first.
        """
        cx, cy = self._clamp(x, y)
        try:
            out = subprocess.run(
                ["hyprctl", "dispatch",
                 "hl.dsp.cursor.move({ x = %d, y = %d })" % (cx, cy)],
                capture_output=True, text=True, check=False,
            )
            if out.stdout.strip() == "ok":
                return
            logger.debug(
                "new-style dispatch failed (%r), trying legacy",
                out.stdout.strip(),
            )
            subprocess.run(
                ["hyprctl", "dispatch", "movecursor", f"{cx} {cy}"],
                capture_output=True, check=True,
            )
        except subprocess.CalledProcessError as exc:
            logger.error("move_cursor(%d, %d) failed: %s", cx, cy, exc)

    def move_relative(self, dx, dy):
        """Moves cursor by relative offset via hyprctl.

        Reads the live position first (hyprctl reports synthetic
        moves truthfully) and delegates to the absolute move.
        """
        try:
            pos = self.get_cursor_pos()
            self.move_cursor(pos[0] + dx, pos[1] + dy)
            return True
        except Exception as exc:
            logger.error("move_relative(%d, %d) failed: %s", dx, dy, exc)
            return False

    def scroll(self, direction, clicks=1):
        """Scroll is handled by the virtual UInput device (see main.py).

        Returns False so the caller falls back to UInput REL_WHEEL events.
        """
        logger.debug(
            "Hyprland scroll (%s, %d) — delegating to UInput fallback.",
            direction, clicks
        )
        return False

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
