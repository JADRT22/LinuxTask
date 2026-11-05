# -*- coding: utf-8 -*-
"""
LinuxTask - hyprland.py
Description: Hyprland compositor driver using hyprctl.
Author: JADRT22 (https://github.com/JADRT22)
License: MIT
"""

import json
import logging
import subprocess
import time

from .base import FALLBACK_RESOLUTION, DesktopManager

logger = logging.getLogger(__name__)


class HyprlandDriver(DesktopManager):
    """Hyprland compositor driver using hyprctl."""

    def __init__(self):
        super().__init__()
        self._detect_resolution()

    def _detect_resolution(self):
        """Populates screen resolution and layout bounds via hyprctl monitors.

        Hyprland reports every monitor's x/y offset in the global layout, so
        the union of all active monitors is used as the clamp box: a macro
        recorded on a second or above/left monitor keeps those coordinates
        instead of being pinned to the primary output (#6, #7).
        """
        try:
            out = subprocess.check_output(
                ["hyprctl", "monitors", "-j"],
                stderr=subprocess.DEVNULL
            ).decode().strip()
            # Filter before use: the `focused` scan below calls .get() on
            # every entry, and one unexpected scalar in the array would
            # raise AttributeError out of a block that only catches
            # subprocess/JSON failures.
            monitors = [m for m in json.loads(out) if isinstance(m, dict)]
            if monitors:
                focused = next(
                    (m for m in monitors if m.get("focused")),
                    monitors[0]
                )
                self.screen_width = int(focused.get("width", 0))
                self.screen_height = int(focused.get("height", 0))
                # set_screen_size keeps `bounds` consistent with the size:
                # a layout that could not be read falls back to the primary
                # box rather than staying None behind.
                self.set_screen_size(
                    self.screen_width, self.screen_height,
                    self._union_bounds(monitors))
                # Same "layout WxH+X+Y" shape the GNOME and KDE drivers
                # print, so one grep works across desktops when a reporter
                # is asked for the line that proves the union was read.
                min_x, min_y, max_x, max_y = self.bounds
                logger.info(
                    "Hyprland resolution: %dx%d, layout %dx%d%+d%+d",
                    self.screen_width, self.screen_height,
                    max_x - min_x, max_y - min_y, min_x, min_y
                )
                return
        except (subprocess.CalledProcessError, FileNotFoundError,
                json.JSONDecodeError) as exc:
            logger.warning("hyprctl monitors failed: %s", exc)

        self.set_screen_size(*FALLBACK_RESOLUTION)
        logger.warning("Using fallback resolution: 1920x1080")

    @staticmethod
    def _union_bounds(monitors):
        """Bounding box (min_x, min_y, max_x, max_y) of enabled monitors.

        The keys below are what hyprctl emits for `monitors` in JSON mode
        (x/y are the layout position, disabled marks an output the
        compositor is not driving). An older payload without offsets
        collapses every output onto the origin, which is the historical
        single-monitor behaviour — better than refusing the layout.
        """
        boxes = []
        for m in monitors:
            if not isinstance(m, dict) or m.get("disabled"):
                continue
            try:
                x, y = int(m.get("x", 0)), int(m.get("y", 0))
                w, h = int(m.get("width", 0)), int(m.get("height", 0))
            except (TypeError, ValueError):
                continue
            if w > 0 and h > 0:
                boxes.append((x, y, x + w, y + h))
        if not boxes:
            return None
        return (
            min(b[0] for b in boxes), min(b[1] for b in boxes),
            max(b[2] for b in boxes), max(b[3] for b in boxes)
        )

    def get_cursor_pos(self):
        """Returns current (x, y) coordinates via hyprctl, or None on failure.

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
            return None

    def move_cursor(self, x, y):
        """Moves cursor to absolute coordinates. True if hyprctl accepted it.

        Hyprland >= 0.55 uses Lua dispatchers
        (hl.dsp.cursor.move); older releases use the legacy
        'dispatch movecursor X Y' form. Try new first, and only fall back to
        the legacy form when the new one is actually rejected — otherwise a
        typo in the Lua call would silently do nothing.
        """
        cx, cy = self._clamp(x, y)
        try:
            out = subprocess.run(
                ["hyprctl", "dispatch",
                 "hl.dsp.cursor.move({ x = %d, y = %d })" % (cx, cy)],
                capture_output=True, text=True, check=False,
            )
            if out.stdout.strip() == "ok":
                return True
            logger.debug(
                "new-style dispatch failed (%r), trying legacy",
                out.stdout.strip(),
            )
            subprocess.run(
                ["hyprctl", "dispatch", "movecursor", f"{cx} {cy}"],
                capture_output=True, check=True,
            )
            return True
        except (subprocess.CalledProcessError, FileNotFoundError, OSError) as exc:
            logger.error("move_cursor(%d, %d) failed: %s", cx, cy, exc)
            return False

    def move_relative(self, dx, dy):
        """Moves cursor by relative offset via hyprctl.

        Reads the live position first (hyprctl reports synthetic
        moves truthfully) and delegates to the absolute move.
        """
        try:
            pos = self.get_cursor_pos()
            if pos is None:
                logger.error("move_relative aborted: cursor pos unknown")
                return False
            return self.move_cursor(pos[0] + dx, pos[1] + dy)
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
        logger.info("--- HyprlandDriver Self-Test ---")
        try:
            subprocess.check_call(
                "command -v hyprctl >/dev/null 2>&1", shell=True
            )
            logger.info("hyprctl found.")
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
        except subprocess.CalledProcessError:
            logger.info("Error: hyprctl command not found.")
            return False
        except Exception as exc:
            logger.info("Self-Test failed: %s", exc)
            return False


if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    HyprlandDriver().self_test()
