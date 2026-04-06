# Changelog

All notable changes to the LinuxTask project will be documented in this file.

## [2.5.0] - Cinnamon Edition - 2026-04-06

### Added
- **Full Cinnamon/X11 Support**: New driver using `xdotool` for absolute and relative movement on X11 desktops (Cinnamon, MATE, XFCE, etc.).
- **Mouse Scroll Recording**: Hardware-level capture of `REL_WHEEL` events and playback support for all drivers.
- **Improved Hotkey Configuration**: Added "Esc" to cancel hotkey remapping and instant UI feedback for new keys.
- **Gnome Driver Fallback**: Implemented mouse button handling via `ydotool` for better reliability when UInput is unavailable.

### Changed
- **UI Refresh**: Increased window width to `420px` to prevent text overlap and refactored internal component structure.
- **Cross-Distro Installation**: `install.sh` and `fix_linuxtask_perms.sh` now support `apt`, `pacman`, and `dnf` automatically.
- **Enhanced Core Precison**: Refactored relative movement accumulation logic to eliminate coordinate drift and stuttering during playback.
- **Cleanup**: Removed obsolete legacy "virtual coordinates" system in favor of native compositor drivers.

### Fixed
- **Double Movement Bug**: Corrected driver return values that were causing double-firing of events through UInput in Hyprland and GNOME.
- **Permission Management**: Improved detection of input devices and automated permission granting via `setfacl`.
- **Theme Consistency**: Fixed settings window hardcoded background color to respect user theme.
