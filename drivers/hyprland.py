import subprocess
from .base import DesktopManager

class HyprlandDriver(DesktopManager):
    """
    Compositor driver for Hyprland.
    """
    
    def get_cursor_pos(self):
        try:
            out = subprocess.check_output("hyprctl cursorpos", shell=True).decode().strip()
            x, y = out.split(", ")
            return int(x), int(y)
        except Exception as e:
            print(f"Hyprland Error (get_cursor_pos): {e}")
            return 0, 0
            
    def move_cursor(self, x, y):
        try:
            subprocess.run(["hyprctl", "dispatch", "movecursor", f"{x} {y}"], capture_output=True)
        except Exception as e:
            print(f"Hyprland Error (move_cursor): {e}")

if __name__ == "__main__":
    # Self-test if run directly
    driver = HyprlandDriver()
    pos = driver.get_cursor_pos()
    print(f"Current Position: {pos}")
    # Testing move relative (slightly)
    driver.move_cursor(pos[0] + 10, pos[1] + 10)
    print("Cursor moved +10, +10")
