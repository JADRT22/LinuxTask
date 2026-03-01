import os
from .hyprland import HyprlandDriver
from .gnome import GnomeDriver

def AutoDetectDriver():
    """
    Detects the current desktop environment and returns the appropriate driver.
    """
    
    # 1. Check for Hyprland-specific signature
    if os.environ.get("HYPRLAND_INSTANCE_SIGNATURE"):
        print("Detected environment: Hyprland")
        return HyprlandDriver()
        
    # 2. Check for XDG_CURRENT_DESKTOP
    current_desktop = os.environ.get("XDG_CURRENT_DESKTOP", "").upper()
    
    if "GNOME" in current_desktop:
        print(f"Detected environment: GNOME ({current_desktop})")
        return GnomeDriver()
    elif "HYPRLAND" in current_desktop:
        print("Detected environment: Hyprland (via XDG)")
        return HyprlandDriver()
        
    # Default fallback
    print(f"Unknown or unsupported environment: {current_desktop}. Falling back to default (Hyprland for now).")
    return HyprlandDriver()
