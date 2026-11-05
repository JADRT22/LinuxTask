# -*- coding: utf-8 -*-
"""
LinuxTask - base.py
Description: Abstract base class for compositor drivers.
Author: JADRT22 (https://github.com/JADRT22)
License: MIT
"""

from abc import ABC, abstractmethod

# Fallback screen resolution used by drivers when detection fails.
FALLBACK_RESOLUTION = (1920, 1080)


class DesktopManager(ABC):
    """Base class for compositor drivers.

    Contract each driver keeps, because playback.py branches on it:

    * get_cursor_pos() returns (x, y) or None when the compositor cannot
      say (recorder and playback both have to degrade).
    * move_cursor(x, y) and move_relative(dx, dy) return True when the
      compositor handled the move, False when it refused — False is what
      makes playback fall back to the virtual device.
    * mouse_button() and scroll() return False by default, which means
      "use UInput instead"; drivers that can do it natively override them.
    * Coordinates are clamped to `bounds`, the union of every output the
      driver detected, so a multi-monitor layout replays where it was
      recorded.
    """

    def __init__(self):
        self.screen_width = 0
        self.screen_height = 0
        # Virtual layout bounding box as (min_x, min_y, max_x, max_y) in
        # compositor-global coordinates, inclusive-exclusive like a rect.
        # None means "one output at the origin", so _clamp falls back to
        # (0, 0, screen_width, screen_height). Drivers that can enumerate
        # every output set it to the union of all of them; without that,
        # coordinates on a second or larger monitor get clipped (#6, #7).
        self.bounds = None
        self.supports_absolute_positioning = True

    def set_screen_size(self, width, height, bounds=None):
        """Records detected geometry, and the layout box to clamp into.

        Single-output drivers pass no bounds; multi-output drivers pass the
        union of every enabled output (offsets included, which can be
        negative).
        """
        self.screen_width = int(width)
        self.screen_height = int(height)
        self.bounds = bounds or self._default_bounds()

    def _default_bounds(self):
        """The primary-output box, used when no layout was detected.

        A driver whose detection left the size at 0 falls back to
        FALLBACK_RESOLUTION instead of a zero-sized box: clamping to
        (0, 0) would pin the whole macro to one pixel in silence.
        """
        width = int(self.screen_width)
        height = int(self.screen_height)
        if width <= 0 or height <= 0:
            width, height = FALLBACK_RESOLUTION
        return (0, 0, max(width, 1), max(height, 1))

    def _layout_box(self):
        """Returns (min_x, min_y, max_x, max_y) to clamp coordinates into.

        Always at least 1x1, so a driver whose detection failed cannot clamp
        every coordinate to (0, 0).
        """
        bounds = getattr(self, 'bounds', None)
        if bounds:
            min_x, min_y, max_x, max_y = bounds
            if max_x > min_x and max_y > min_y:
                return int(min_x), int(min_y), int(max_x), int(max_y)
        return self._default_bounds()

    def _clamp(self, x, y):
        """Clamps (x, y) to the detected layout bounds.

        The upper edge is exclusive, so the last reachable coordinate is
        max - 1 (matching the historical screen_width - 1 behaviour). A
        layout with a monitor left/above the origin has a negative min,
        and those coordinates are then legal instead of being pinned to 0.
        """
        min_x, min_y, max_x, max_y = self._layout_box()
        return (
            max(min_x, min(int(x), max_x - 1)),
            max(min_y, min(int(y), max_y - 1))
        )

    @abstractmethod
    def get_cursor_pos(self):
        """Returns (x, y) coordinates."""
        pass

    @abstractmethod
    def move_cursor(self, x, y):
        """Moves cursor to absolute (x, y).

        Must return True if the compositor handled the warp, and False when
        it refused or failed. Playback treats False as "try the UInput
        fallback" (see playback.py warp_uinput), and a None return would
        silently disable that fallback, so every driver has to return a
        bool.
        """
        pass

    @abstractmethod
    def move_relative(self, dx, dy):
        """Moves cursor by relative offset (dx, dy).
        Must return True if handled by compositor, or False to fallback to UInput.
        """
        pass

    def mouse_button(self, button, pressed):
        """Handles mouse button press/release.

        Args:
            button: evdev button code (e.g. BTN_LEFT=272).
            pressed: True for press, False for release.

        Returns:
            True if handled by driver, False to fall back to UInput.
        """
        return False

    def scroll(self, direction, clicks=1):
        """Performs scroll action. Override in subclass if supported.

        Args:
            direction: 'up' or 'down'.
            clicks: number of scroll steps.

        Returns:
            True if handled by driver, False to fall back to UInput.
        """
        return False
