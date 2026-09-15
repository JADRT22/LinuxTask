# Changelog

All notable changes to the LinuxTask project will be documented in this file.
(Single canonical changelog: updated by hand and prepended automatically by
`tools/release.py`.)

## [2.6.1] - 2026-09-15

### Added
- **KDE Wayland Support**: new driver using the Portal RemoteDesktop interface
  with dead-reckoning position tracking, re-synced once per playback.
- **Reproducible AppImage Build**: `tools/appimage/build.sh` stages and patches
  the source for python-build-standalone (ASCII toolbar labels for the bundled
  Tk).

### Fixed
- **Missing Dependency Crashes**: `factory.py` now checks for `Xlib` (X11) and
  `dbus`/`gi` (KDE Wayland) **before** importing each driver and raises a clear
  `RuntimeError` with exact install instructions (apt/pacman/dnf) instead of a
  raw `ImportError`. `main.py` shows the message in a visible dialog rather
  than dying with a traceback.
- **KDE Wayland Uninstallable Out of the Box**: `tools/install.sh` now installs
  the distro D-Bus bindings (`python3-dbus`/`python3-gi`) the portal driver
  needs; `run.sh` warns with manual commands when they are absent.
- **X11 Fallback Missing python-xlib**: `install.sh` and `run.sh` pip fallbacks
  now include `python-xlib` (previously only `customtkinter evdev`), so the
  generic X11 driver no longer fails to import on manual installs.
- **Implicit State**: `_rel_dx`/`_rel_dy` are now initialized in the app
  constructor instead of being created lazily inside `toggle_record()`;
  evdev listener threads no longer depend on record having run first.
- **Hyprland 0.55+**: cursor moves use the new Lua dispatcher
  (`hl.dsp.cursor.move`) with fallback to the legacy `movecursor` form.
- **Release Script Version Regex**: `tools/release.py` now reads the
  `APP_VERSION` constant (the old pattern parsed a hardcoded version out of
  the window title and always failed) and mirrors the bump to
  `tools/appimage/pyproject.toml`.

### Security
- **Read-Only Input Devices**: udev rule for `event*` devices changed from
  `0660` to `0440` — recording only needs read access, and write access on
  real input devices is a full injection primitive for any process in the
  `input` group. `/dev/uinput` stays `0660` (replay requires it).
- **Matching ACLs**: `install.sh` and `fix_linuxtask_perms.sh` now grant
  `u:USER:r` (not `rw`) on `/dev/input/event*`, so the immediate ACL grant
  cannot reopen the write access the udev rule closes.
- **Experiment Quarantined**: the unfinished libei PoCs moved out of
  `src/drivers/` into `experimental/libei/` (with a README), and the compiled
  `ei_send` binary was removed — `build.sh` copies `src/drivers/` wholesale,
  so the AppImage no longer bundles stray artifacts.

### Changed
- **X11 Driver Rewrite**: `X11Driver` now uses `python-xlib` (XTest) instead of
  shelling out to `xdotool`.
- **Thread-Safe Hotkeys**: global hotkeys are dispatched to the UI thread via
  a queue; hover tooltips added for emoji-only toolbar buttons.
- **Monotonic Timing**: macro recording and playback schedules use
  `time.monotonic()` instead of `time.time()`, making event deltas immune to
  NTP/DST clock jumps. Saved `.json` macros stay compatible (they store
  deltas, not absolute timestamps).

## [2.6.0] - Cinnamon Edition - 2026-04-07

### Added
- **Full Cinnamon/X11 Support**: New driver using `xdotool` for absolute and relative movement on X11 desktops (Cinnamon, MATE, XFCE, etc.).
- **Mouse Scroll Recording**: Hardware-level capture of `REL_WHEEL` events and playback support for all drivers.
- **Improved Hotkey Configuration**: Added "Esc" to cancel hotkey remapping and instant UI feedback for new keys.
- **Gnome Driver Fallback**: Implemented mouse button handling via `ydotool` for better reliability when UInput is unavailable.
- **Enhanced Documentation**: Updated `README.md` with professional architecture diagrams, support matrix, and a high-quality demo screenshot.
- **Improved Installer**: refined `install.sh` to ensure the desktop shortcut is immediately visible and uses absolute paths.
- **CI Automation**: GitHub Actions workflows for automated testing and tagged GitHub Releases.

### Changed
- **UI Refresh**: Increased window width to `420px` to prevent text overlap and refactored internal component structure.
- **Cross-Distro Installation**: `install.sh` and `fix_linuxtask_perms.sh` now support `apt`, `pacman`, and `dnf` automatically.
- **Enhanced Core Precison**: Refactored relative movement accumulation logic to eliminate coordinate drift and stuttering during playback.
- **Cleanup**: Removed obsolete legacy "virtual coordinates" system in favor of native compositor drivers.

### Fixed
- **Double Movement Bug**: Corrected driver return values that were causing double-firing of events through UInput in Hyprland and GNOME.
- **Permission Management**: Improved detection of input devices and automated permission granting via `setfacl`.
- **Theme Consistency**: Fixed settings window hardcoded background color to respect user theme.
- **Release Script Regex**: support dynamic window titles when reading the version.

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
