# -*- coding: utf-8 -*-
"""
LinuxTask - factory.py
Description: Driver factory for auto-detection of desktop environment.
Author: JADRT22 (https://github.com/JADRT22)
License: MIT
"""

import os
import logging

logger = logging.getLogger(__name__)


def AutoDetectDriver():
    """
    Detects the current desktop environment and returns the appropriate driver.

    Detection order:
        1. Hyprland (via HYPRLAND_INSTANCE_SIGNATURE)
        2. XDG_CURRENT_DESKTOP matching
        3. X11 fallback (via DISPLAY env var)
        4. Error if nothing matches
    """

    # 1. Check for Hyprland-specific signature
    if os.environ.get("HYPRLAND_INSTANCE_SIGNATURE"):
        from .hyprland import HyprlandDriver
        logger.info("Detected environment: Hyprland")
        return HyprlandDriver()

    # 2. Check XDG_CURRENT_DESKTOP
    current_desktop = os.environ.get("XDG_CURRENT_DESKTOP", "").upper()

    if "HYPRLAND" in current_desktop:
        from .hyprland import HyprlandDriver
        logger.info("Detected environment: Hyprland (via XDG)")
        return HyprlandDriver()

    if "GNOME" in current_desktop:
        session_type = os.environ.get("XDG_SESSION_TYPE", "").lower()
        if session_type == "wayland":
            from .gnome import GnomeDriver
            logger.info("Detected environment: GNOME Wayland")
            return GnomeDriver()
        else:
            from .x11 import X11Driver
            logger.info("Detected environment: GNOME on X11")
            return X11Driver()

    # X11-based desktops: Cinnamon, MATE, XFCE, KDE on X11, etc.
    x11_desktops = [
        "X-CINNAMON", "CINNAMON", "MATE", "XFCE", "LXDE",
        "LXQT", "BUDGIE", "PANTHEON", "UNITY", "KDE"
    ]
    for desktop in x11_desktops:
        if desktop in current_desktop:
            from .x11 import X11Driver
            logger.info(
                "Detected environment: %s (X11 driver)",
                current_desktop
            )
            return X11Driver()

    # 3. Generic X11 fallback
    if os.environ.get("DISPLAY"):
        from .x11 import X11Driver
        logger.warning(
            "Unknown desktop '%s' but DISPLAY is set. "
            "Using X11 driver as fallback.",
            current_desktop
        )
        return X11Driver()

    # 4. No supported environment detected
    raise RuntimeError(
        f"Unsupported desktop environment: '{current_desktop}'. "
        f"LinuxTask requires X11 (xdotool), Hyprland (hyprctl), "
        f"or GNOME Wayland (ydotool)."
    )
