# -*- coding: utf-8 -*-
"""
LinuxTask - sway.py
Description: Sway (wlroots) compositor driver using swaymsg IPC.
Author: JADRT22 (https://github.com/JADRT22)
License: MIT
"""

import json
import logging
import shlex
import shutil
import subprocess

from evdev.ecodes import BTN_LEFT, BTN_MIDDLE, BTN_RIGHT

from .base import FALLBACK_RESOLUTION, DesktopManager

logger = logging.getLogger(__name__)

# evdev button code -> sway x11-style button name (cursor press/release).
BTN_MAP = {BTN_LEFT: "button1", BTN_RIGHT: "button3", BTN_MIDDLE: "button2"}

# Sway maps button4..button7 to the scroll axes (see sway/commands/seat/cursor.c).
SCROLL_BUTTON = {"up": "button4", "down": "button5"}


class SwayDriver(DesktopManager):
    """Sway compositor driver using standards-based wlroots IPC."""

    def __init__(self):
        super().__init__()
        # The sway IPC exposes command-only cursor movement; it has no query
        # for the current position, so the recorder records relative deltas.
        # move_cursor() still warps to absolute coordinates when a macro
        # carries 'pos' events.
        self.supports_absolute_positioning = False
        self.swaymsg_path = shutil.which("swaymsg")
        self._seat = self._detect_seat()
        self._detect_resolution()

    # --- IPC helpers ---------------------------------------------------

    def _command(self, command, check=False):
        """Sends a swaymsg IPC command. Returns parsed JSON or None.

        swaymsg's getopt permutes the argv and eats negative coordinates
        (`cursor move -30 40`), so a '--' separator is added whenever the
        command carries one. It must stay off for '-t <type>' queries, where
        the leading '-t' is the option itself.
        """
        try:
            args = shlex.split(command)
            argv = [self.swaymsg_path]
            if any(a[1:].isdigit() for a in args if a.startswith("-")):
                argv.append("--")
            argv.extend(args)
            out = subprocess.run(
                argv,
                capture_output=True, text=True, check=check, timeout=5
            )
            try:
                return json.loads(out.stdout)
            except json.JSONDecodeError:
                return None
        except (subprocess.CalledProcessError, FileNotFoundError,
                subprocess.TimeoutExpired, OSError) as exc:
            logger.error("swaymsg command failed (%s): %s", command, exc)
            return None

    def _detect_seat(self):
        """Resolves the primary seat name (usually 'seat0')."""
        seats = self._command("-t get_seats")
        if isinstance(seats, list) and seats:
            name = seats[0].get("name")
            if name:
                return name
        logger.warning("Could not resolve the sway seat name; using 'seat0'.")
        return "seat0"

    def _detect_resolution(self):
        """Reads output geometry from swaymsg get_outputs.

        'rect' holds the layout-space position and size the cursor warps in
        ('current_mode' is the physical mode and differs under fractional
        scaling), so the primary size and the clamp box both come from the
        rects of all enabled outputs (#6, #7).
        """
        try:
            outputs = self._command("-t get_outputs")
            # Same reason as in the Hyprland driver: the `focused` scan
            # below would raise AttributeError on a non-dict entry.
            if isinstance(outputs, list):
                outputs = [o for o in outputs if isinstance(o, dict)]
            if outputs:
                output = next(
                    (o for o in outputs if o.get("focused")), outputs[0]
                )
                rect = output.get("rect") or {}
                mode = output.get("current_mode") or {}
                width = rect.get("width") or mode.get("width")
                height = rect.get("height") or mode.get("height")
                if width and height:
                    self.set_screen_size(
                        int(width), int(height),
                        self._union_bounds(outputs))
                    # See the Hyprland driver: one "layout WxH+X+Y" shape
                    # for every driver, so support can ask for it and
                    # compare across desktops.
                    min_x, min_y, max_x, max_y = self.bounds
                    logger.info(
                        "Sway resolution: %dx%d, layout %dx%d%+d%+d",
                        self.screen_width, self.screen_height,
                        max_x - min_x, max_y - min_y, min_x, min_y
                    )
                    return
        except Exception as exc:
            logger.warning("swaymsg get_outputs failed: %s", exc)

        self.set_screen_size(*FALLBACK_RESOLUTION)
        logger.warning("Using fallback resolution: 1920x1080")

    @staticmethod
    def _union_bounds(outputs):
        """Bounding box (min_x, min_y, max_x, max_y) of enabled outputs."""
        boxes = []
        for output in outputs:
            if not isinstance(output, dict):
                continue
            if not output.get("enabled", True):
                continue
            rect = output.get("rect") or {}
            try:
                x, y = int(rect.get("x", 0)), int(rect.get("y", 0))
                width, height = int(rect.get("width")), int(rect.get("height"))
            except (TypeError, ValueError):
                continue
            if width > 0 and height > 0:
                boxes.append((x, y, x + width, y + height))
        if not boxes:
            return None
        return (
            min(b[0] for b in boxes), min(b[1] for b in boxes),
            max(b[2] for b in boxes), max(b[3] for b in boxes)
        )

    # --- Driver API ----------------------------------------------------

    def get_cursor_pos(self):
        """Not supported: the sway IPC cannot report the cursor position.

        The recorder does not call this (the driver records relative
        motion); it stays available for callers that check the driver
        surface and must degrade gracefully.
        """
        logger.debug(
            "get_cursor_pos is unsupported on Sway (IPC has no query)."
        )
        return None

    def _seat_cmd(self, sub, *args):
        """Runs 'seat <seat> cursor <sub> <args...>' and reports success.

        swaymsg answers commands with a JSON payload; for commands that can
        be repeated in one request it is a list of result objects. Accept a
        bare object too, so a single-result reply still counts as success.
        """
        command = "seat {} cursor {} {}".format(
            self._seat, sub, " ".join(str(a) for a in args)
        )
        reply = self._command(command)
        results = reply if isinstance(reply, list) else [reply]
        return any(
            isinstance(r, dict) and r.get("success") is True for r in results
        )

    def move_cursor(self, x, y):
        """Warps the cursor to absolute coordinates ('cursor set').

        Returns True when swaymsg reported the command as successful, so
        playback can tell a refused warp from a done one.
        """
        cx, cy = self._clamp(x, y)
        if self._seat_cmd("set", cx, cy):
            return True
        logger.error("move_cursor(%d, %d) failed", cx, cy)
        return False

    def move_relative(self, dx, dy):
        """Moves the cursor by a relative offset ('cursor move')."""
        if self._seat_cmd("move", int(dx), int(dy)):
            return True
        logger.error("move_relative(%d, %d) failed", int(dx), int(dy))
        return False

    def mouse_button(self, button, pressed):
        """Presses/releases a mouse button ('cursor press|release')."""
        name = BTN_MAP.get(button)
        if not name:
            return False
        return self._seat_cmd(
            "press" if pressed else "release", name
        )

    def scroll(self, direction, clicks=1):
        """Scrolls via the sway button4/button5 axis buttons.

        Sway fires both press and release for axis buttons and ignores the
        state, so one call per click is enough.
        """
        name = SCROLL_BUTTON.get(direction)
        if not name:
            return False
        handled = True
        for _ in range(clicks):
            handled = self._seat_cmd("press", name) and handled
        return handled

    def self_test(self):
        """Performs driver verification."""
        logger.info("--- SwayDriver Self-Test ---")
        if not self.swaymsg_path:
            logger.error("seat command not found in PATH.")
            return False
        logger.info("seat: %s", self._seat)
        logger.info("Resolution: %dx%d", self.screen_width, self.screen_height)

        # A cursor position cannot be read back on Sway, so verify movement
        # by asking Sway to warp to the clamped origin and checking the reply.
        return self._seat_cmd("set", 0, 0)


if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    SwayDriver().self_test()
