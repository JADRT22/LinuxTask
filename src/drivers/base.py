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
    """
    
    def __init__(self):
        self.virtual_x = 0
        self.virtual_y = 0
        self.screen_width = 0
        self.screen_height = 0
    
    @abstractmethod
    def get_cursor_pos(self):
        """Returns (x, y) coordinates."""
        pass
        
    @abstractmethod
    def move_cursor(self, x, y):
        """Moves cursor to (x, y)."""
        pass

    def sync_delta(self, dx, dy):
        """Updates internal virtual position based on relative movements."""
        self.virtual_x += dx
        self.virtual_y += dy
