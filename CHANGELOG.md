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

## [2.4.0] - 2026-03-01
### Added
- EPIC: Implement Release Automation Script in `tools/release.py`.
- EPIC: Professionalize Documentation (README overhaul and CONTRIBUTING.md).
- EPIC: Standardize Code Headers & PEP 8 Compliance across all Python files.
- EPIC: Repository Structural Reorganization into `src/`, `tests/`, `docs/`, `tools/`.

### Fixed
- Resolve `AttributeError` in `GnomeDriver` by adding screen resolution attributes.

### Improved
- Validate `HyprlandDriver` and add unit tests with mocks.
- Investigate absolute cursor position on GNOME and add research PoC script.
- Dynamic screen resolution detection on GNOME/Wayland via `gdbus` and `xrandr`.

## [2.2.0] - 2026-03-01
### Added
- **Hardware Access Automation**: Introduced `fix_linuxtask_perms.sh` to automate ACL and Udev configuration.
- **Pure Relative Movement Engine**: Implemented relative movement logic for GNOME Wayland users.
- **Ydotool Integration**: Optimized `ydotoold` daemon management for Arch/CachyOS.

### Fixed
- Resolved "drift" and "corner jump" bugs with strict coordinate clamping and delta-based tracking.

## [2.0.0] - 2026-02-22
### Added
- **🤖 Humanize Mode (Anti-Bot)**: Algorithm with ±2px jitter and 0-3% time delays to mimic human behavior.
- **Settings UI Overhaul**: Fixed "Black Screen" bug on Wayland/Hyprland and improved contrast.

### Improved
- **Stable Desktop Shortcut**: Consistently uses `input-mouse` icon.
- **Test Suite**: Added unit tests (`test_jitter.py`) for movement precision.
