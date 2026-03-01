from abc import ABC, abstractmethod

class DesktopManager(ABC):
    """
    Base class for compositor drivers.
    """
    
    def __init__(self):
        self.virtual_x = 0
        self.virtual_y = 0
    
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
