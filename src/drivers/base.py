# -*- coding: utf-8 -*-
"""
LinuxTask - base.py
Description: Abstract base class for compositor drivers.
Author: JADRT22 (https://github.com/JADRT22)
License: MIT
"""

from abc import ABC, abstractmethod


class DesktopManager(ABC):
    """
    Base class for compositor drivers.
    All drivers must implement get_cursor_pos, move_cursor, and move_relative.
    """

    def __init__(self):
        self.screen_width = 0
        self.screen_height = 0

    @abstractmethod
    def get_cursor_pos(self):
        """Returns (x, y) coordinates."""
        pass

    @abstractmethod
    def move_cursor(self, x, y):
        """Moves cursor to absolute (x, y)."""
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
        """
        pass
