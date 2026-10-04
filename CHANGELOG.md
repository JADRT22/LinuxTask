# Changelog

All notable changes to the LinuxTask project will be documented in this file.
The `[Unreleased]` section collects changes since the last release;
`tools/release.py` moves its body under the new version heading when a
release is cut and resets it to empty, so released notes never linger
as pending.

## [Unreleased]

### Changed
- README is now English-first: Portuguese survives only as a short footnote
  with a cross-link to the English guide.
- Demo is now an animated GIF showing keyboard-only record/replay on
  KDE Wayland instead of a static screenshot.
- Quickstart heading uses the plain style, matching the rest of the docs.
- Audit cleanup: the unfinished libei prototypes moved to `.quarantine/`
  (out of the AppImage payload), the AppImage font patch targets the actual
  toolbar font size, `requirements.txt` marks numpy/Pillow as add-on-only,
  and the global `*.json` ignore is narrowed so config files stay visible.

### Fixed
- Playback tallies per-event failures and reports a summary afterward, and a
  malformed event timestamp now fails that event only instead of aborting
  the whole macro.
- Hyprland `get_cursor_pos()` returns `None` on read failure instead of
  `(0, 0)`, so a transient `hyprctl` failure falls back to uinput instead of
  jumping the cursor to the corner.
- Audit bug fixes: the KDE portal driver uses the shared screen-size
  attributes, a missing `hyprctl` no longer escapes playback, X11/GNOME
  cursor reads return `None` on failure, Stop responds immediately via
  sliced waits, event dedupe uses bounded eviction, a missing `ydotool` is
  handled, shared recorder state is lock-guarded, portal and `xrandr`/`gdbus`
  calls time out, the release script avoids shell invocation, and macro
  save/load validates UTF-8 input.

## [v3.0.1] - 2026-10-01

### Added
- **Optional visual-trigger add-on** in `experimental/`: `image_click/` finds
  an image on screen and clicks it (grim capture with a pure-numpy NCC
  matcher) and `color_spin/` clicks in a loop until a target color appears,
  with a stability guard against animated false positives and a compact GUI
  with live log and start/stop buttons. Ships with an independent installer
  (`experimental/install.sh`) that only adds numpy/Pillow, grim/slurp and
  desktop shortcuts; the main install neither includes nor requires it.
  Backed by reusable `src/vision.py` (template matching, `color_fraction`)
  and `src/capture.py` (grim/slurp backend) helpers used only by the add-on.

### Changed
- **Compact toolbar**: window reduced from 420x50 to 400x44 with 32px buttons
  and tighter spacing (TinyTask-inspired density); all controls keep their
  places, with smaller Open/Save labels, the 0.5x-10x speed selector, the
  settings gear and hover tooltips intact.
- README rewritten for accuracy and professional tone, with a one-line
  quickstart; CONTRIBUTING rewritten in the same style.
- Release script inserts new entries below the hand-written `[Unreleased]`
  section instead of prepending above it.


## [v3.0.0] - 2026-09-15

### Added
- **KDE Wayland Support**: new driver using the Portal RemoteDesktop interface
  with dead-reckoning position tracking, re-synced once per playback.
- **Reproducible AppImage Build**: `tools/appimage/build.sh` stages and patches
  the source for python-build-standalone (ASCII toolbar labels for the bundled
  Tk).
- **Core Flow Test Suite**: new `tests/test_main_flow.py` with 38 headless
  unit tests for the heart of `main.py` (no display or hardware needed): event
  deduplication across devices, recording of keys/scroll/relative and absolute
  motion with `EV_SYN` flush, hotkey mapping and exclusion, humanize jitter
  bounds, playback dispatch with UInput fallback, speed scaling and stop
  interruption, macro validation and save/load roundtrip, and the thread-safe
  hotkey queue. Added to the CI workflow (`python-app.yml`).

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

## [v2.6.0] - 2026-04-07

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

## [v2.4.0] - 2026-03-01
### Added
- EPIC: Implement Release Automation Script in `tools/release.py`.
- EPIC: Professionalize Documentation (README overhaul and CONTRIBUTING.md).
- EPIC: Standardize Code Headers & PEP 8 Compliance across all Python files.
- EPIC: Repository Structural Reorganization into `src/`, `tests/`, `docs/`, `tools/`.

### Fixed
- Resolve `AttributeError` in `GnomeDriver` by adding screen resolution attributes.

### Changed
- Validate `HyprlandDriver` and add unit tests with mocks.
- Investigate absolute cursor position on GNOME and add research PoC script.
- Dynamic screen resolution detection on GNOME/Wayland via `gdbus` and `xrandr`.

## [v2.2.0] - 2026-03-01
### Added
- **Hardware Access Automation**: Introduced `fix_linuxtask_perms.sh` to automate ACL and Udev configuration.
- **Pure Relative Movement Engine**: Implemented relative movement logic for GNOME Wayland users.
- **Ydotool Integration**: Optimized `ydotoold` daemon management for Arch/CachyOS.

### Fixed
- Resolved "drift" and "corner jump" bugs with strict coordinate clamping and delta-based tracking.

## [v2.0.0] - 2026-02-22
### Added
- **Humanize Mode (Anti-Bot)**: Algorithm with ±2px jitter and 0-3% time delays to mimic human behavior.
- **Settings UI Overhaul**: Fixed "Black Screen" bug on Wayland/Hyprland and improved contrast.

### Changed
- **Stable Desktop Shortcut**: Consistently uses `input-mouse` icon.
- **Test Suite**: Added unit tests (`test_jitter.py`) for movement precision.

[Unreleased]: https://github.com/JADRT22/LinuxTask/compare/v3.0.1...HEAD
[v3.0.1]: https://github.com/JADRT22/LinuxTask/compare/v3.0.0...v3.0.1
[v3.0.0]: https://github.com/JADRT22/LinuxTask/compare/v2.6.0...v3.0.0
[v2.6.0]: https://github.com/JADRT22/LinuxTask/compare/v2.4.0...v2.6.0
[v2.4.0]: https://github.com/JADRT22/LinuxTask/compare/v2.2.0...v2.4.0
[v2.2.0]: https://github.com/JADRT22/LinuxTask/compare/v2.0.0...v2.2.0
[v2.0.0]: https://github.com/JADRT22/LinuxTask/releases/tag/v2.0.0
