# -*- coding: utf-8 -*-
"""
LinuxTask - hyprland.py
Description: Hyprland compositor driver.
Author: JADRT22 (https://github.com/JADRT22)
License: MIT
"""

import subprocess
import json
import time
from .base import DesktopManager

class HyprlandDriver(DesktopManager):
    """Hyprland compositor driver using hyprctl."""
    
    def __init__(self):
        super().__init__()
        self._detect_resolution()
    
    def _detect_resolution(self):
        """Populates screen resolution via hyprctl monitors."""
        try:
            out = subprocess.check_output(
                "hyprctl monitors -j", shell=True
            ).decode().strip()
            monitors = json.loads(out)
            if monitors:
                focused = next((m for m in monitors if m.get("focused")), monitors[0])
                self.screen_width = int(focused.get("width", 0))
                self.screen_height = int(focused.get("height", 0))
                return
        except Exception as e:
            print(f"Hyprland Error (_detect_resolution): {e}")
        
        self.screen_width, self.screen_height = 1920, 1080
    
    def get_cursor_pos(self):
        """Returns current (x, y) coordinates."""
        try:
            out = subprocess.check_output(
                "hyprctl cursorpos", shell=True
            ).decode().strip()
            x, y = out.split(", ")
            return int(x), int(y)
        except Exception as e:
            print(f"Hyprland Error (get_cursor_pos): {e}")
            return 0, 0
            
    def move_cursor(self, x, y):
        """Moves cursor to absolute coordinates."""
        try:
            subprocess.run(
                ["hyprctl", "dispatch", "movecursor", f"{x} {y}"],
                capture_output=True
            )
        except Exception as e:
            print(f"Hyprland Error (move_cursor): {e}")

    def self_test(self):
        """Performs driver verification."""
        print("--- HyprlandDriver Self-Test ---")
        try:
            subprocess.check_call("command -v hyprctl >/dev/null 2>&1", shell=True)
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
        except Exception as e:
            print(f"Self-Test failed: {e}")
            return False

if __name__ == "__main__":
    HyprlandDriver().self_test()
