from abc import ABC, abstractmethod

class DesktopManager(ABC):
    """
    Base class for desktop environment-specific cursor interactions.
    """
    
    @abstractmethod
    def get_cursor_pos(self):
        """
        Returns the current cursor position as a tuple (x, y).
        """
        pass
    
    @abstractmethod
    def move_cursor(self, x, y):
        """
        Moves the cursor to the absolute position (x, y).
        """
        pass
