# -*- coding: utf-8 -*-
"""
LinuxTask - sway.py
Description: Sway (wlroots) compositor driver using swaymsg IPC.
Author: JADRT22 (https://github.com/JADRT22)
License: MIT
"""

import json
import logging
import shutil
import subprocess
from evdev.ecodes import BTN_LEFT, BTN_MIDDLE, BTN_RIGHT
from .base import DesktopManager, FALLBACK_RESOLUTION

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
        """Sends a swaymsg IPC command. Returns parsed JSON or None."""
        try:
            out = subprocess.run(
                [self.swaymsg_path, command],
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
        """Reads the root output geometry from swaymsg get_outputs."""
        try:
            outputs = self._command("-t get_outputs")
            if isinstance(outputs, list) and outputs:
                output = next(
                    (o for o in outputs if o.get("focused")), outputs[0]
                )
                # 'rect' holds the layout-space size the cursor warps in;
                # 'current_mode' is the physical mode (differs on fractional
                # scaling), so prefer the rect and fall back to the mode.
                rect = output.get("rect") or {}
                mode = output.get("current_mode") or {}
                width = rect.get("width") or mode.get("width")
                height = rect.get("height") or mode.get("height")
                if width and height:
                    self.screen_width = int(width)
                    self.screen_height = int(height)
                    logger.info(
                        "Sway resolution: %dx%d",
                        self.screen_width, self.screen_height
                    )
                    return
        except Exception as exc:
            logger.warning("swaymsg get_outputs failed: %s", exc)

        self.screen_width, self.screen_height = FALLBACK_RESOLUTION
        logger.warning("Using fallback resolution: 1920x1080")

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

        swaymsg answers commands with a JSON object carrying `success`;
        anything else (parse error, IPC failure) counts as not handled.
        """
        command = "seat {} cursor {} {}".format(
            self._seat, sub, " ".join(str(a) for a in args)
        )
        reply = self._command(command)
        return isinstance(reply, dict) and reply.get("success") is True

    def move_cursor(self, x, y):
        """Warps the cursor to absolute coordinates ('cursor set')."""
        cx, cy = self._clamp(x, y)
        if not self._seat_cmd("set", cx, cy):
            logger.error("move_cursor(%d, %d) failed", cx, cy)

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
