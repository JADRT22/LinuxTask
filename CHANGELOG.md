# Changelog

All notable changes to the LinuxTask project will be documented in this file.
The `[Unreleased]` section collects changes since the last release;
`tools/release.py` moves its body under the new version heading when a
release is cut and resets it to empty, so released notes never linger
as pending. Releases v2.0.0 and v2.2.0 predate the project's git tags,
so their headings carry no compare links (v2.2.0 is also listed with the
same date as v2.4.0, and with no tag that date cannot be checked).

## [Unreleased]

### Added
- **Sway driver**: `src/drivers/sway.py` drives Sway (and swayfx) through the
  seat IPC — `cursor move` for relative motion, `cursor set` to warp absolute,
  `cursor press/release` for buttons (`button1`/`button2`/`button3`) and
  scroll via `button4`/`button5`. Detected first through `SWAYSOCK` and then
  `XDG_CURRENT_DESKTOP`, before the generic X11 fallback, so the warning
  from issue #4 no longer fires on Sway. Because the sway IPC has no way to
  read the cursor position back, the driver sets
  `supports_absolute_positioning = False` and records relative deltas like the
  GNOME driver; `cursor set` is still used at replay for `start_pos` and `pos`
  events. Resolution comes from `swaymsg -t get_outputs` (output `rect`, with
  `current_mode` as fallback). `tools/install.sh` checks for `swaymsg` on
  Sway and fails with install guidance instead of installing the compositor.
- **Sway driver verified against a live compositor**: the author ran sway 1.12
  headless on a private `SWAYSOCK` (leaving the desktop session untouched) and
  exercised `SwayDriver` end to end — seat resolved to `seat0`, resolution read
  as 1024×768 from `get_outputs`, `cursor move 10 -5`, `cursor set 100 200`,
  clamping to the last pixel, button press/release and `button4`/`button5`
  scroll all answered `success: true`. That run exposed two bugs the mocked
  tests could not: swaymsg answers commands with a JSON **array**
  (`[{"success": true}]`), not a bare object, and its `getopt` eats negative
  coordinates (`cursor move -30 40` arrives as `cursor move 40`). Both are
  fixed and covered by regression tests, and the README status table now lists
  Sway as author-tested instead of "implemented, not tested".

### Fixed
- **Sway seat IPC replies are parsed correctly**: `_seat_cmd` required a JSON
  object with `success`, but swaymsg answers commands with a list of result
  objects (`[{"success": true}]`), so every cursor move, button and scroll
  reported failure against a real sway while passing the mocked tests.
- **Sway negative coordinates survive swaymsg's getopt**: `cursor move -30 40`
  reached sway as `cursor move 40`. A `--` separator is inserted before a
  negative number, and stays off for `-t <type>` queries where the leading
  `-t` is the option itself.
- **Sway IPC commands are no longer passed as a single argv entry**: the
  command string was handed to `swaymsg` as one argument, so `-t get_seats`
  arrived as a literal message type and sway answered
  `Unknown message type  get_seats`. The command is now `shlex.split` into
  argv, which also fixes the seat and resolution detection that silently fell
  back to `seat0` and 1920×1080.
- **Driver-factory tests no longer break CI by importing every driver**: they
  patched `drivers.kde_wayland...`, which force-imports the module. That module
  needs `dbus-python` and `PyGObject` at import time and CI installs only
  `requirements.txt`, so the suite failed with
  `module 'drivers' has no attribute 'kde_wayland'`. Stub modules are injected
  into `sys.modules` instead, and no real driver module is imported.

### Documentation
- **README status table matches the capability matrix**: Hyprland and the X11
  desktops are marked as author-tested (record, replay and clicks), on par with
  the KDE Plasma Wayland column that was already listed as verified. Before
  this the table said only KDE was tested while the matrix below it claimed
  three columns were verified. GNOME Wayland stays marked as implemented but
  not tested by the author.
- **Sway column added** to the capability matrix, with a note explaining why
  absolute recording is impossible there (no cursor query in the sway IPC)
  and that macros still replay through the uinput fallback.

## [v3.1.2] - 2026-10-07

### Added
- **Installer confirms before sudo**: `tools/install.sh` asks for
  confirmation before escalating and accepts `--yes` to skip the prompt
  for unattended installs.

### Fixed
- **KDE Wayland buttons reach the portal as real mouse buttons**: clicks,
  right-clicks and middle-clicks are translated to the evdev codes the
  RemoteDesktop portal expects (272/273/274) instead of X11 button
  numbers 1/2/3, which portal versions ignored or misread.
- **A dead portal is reported instead of silently swallowing input**: when
  the portal session fails to start or a portal call fails, the driver
  raises a one-time warning in the UI (repeats stay in the log) and the
  event falls back to `uinput`, instead of dropping it with no signal.
- **KDE Wayland cursor position is read from the compositor, not from
  frozen `xdotool`**: `xdotool getmouselocation` only tracks the pointer
  over XWayland surfaces, so on a Wayland desktop it froze on one stale
  coordinate and every recorded macro carried the same position — replays
  then clicked wherever the pointer happened to be. The driver now reads
  the true position from KWin's scripting D-Bus API (`workspace.cursorPos`,
  the `kdotool` mechanism, ~7 ms per read), falls back to `xdotool` and
  then to the last known position, and warns once if KWin is unavailable
  so a stale-coordinate macro can never be recorded silently again.

## [v3.1.1] - 2026-10-04

### Changed
- **Vision/capture helpers moved out of `src/`**: `vision.py` and `capture.py`
  now live in `experimental/` with the add-ons that use them, keeping them out
  of the main package and the AppImage.
- **X11 driver verified**: record/replay tested by the author on a KDE Plasma
  X11 session; the README status table and capability matrix now mark the X11
  column as tested.
- **`evdev` pinned end to end**: `requirements.txt`, the AppImage `pyproject`
  and the `.venv` created by `install.sh` all run the pinned 2.0.0, so CI, the
  venv and the packaged app stop testing three different versions.

### Fixed
- **Coordinate suite cannot touch a live `ydotoold`**: the test mocks the
  daemon spawn *and* the socket cleanup, registers every patcher with
  `addCleanup`, and ships a regression test proving a stale socket file
  survives the suite (reviewer-reproduced before the fix).
- **AppImage guard is total**: `build.sh` selects an interpreter that actually
  has `appimage` (existing env, then system python) and, when none exists,
  fails with pip/uv guidance instead of `uv: command not found`.
- **Release script keeps the README in sync**: `update_source_version()` now
  rewrites the `This README describes vX.Y.Z` line (v3.1.0 shipped while the
  README still said 3.0.3).
- **`color_spin` sys.path inserts normalized**: one spelling, membership
  guard, same pattern as the test suite.

## [v3.1.0] - 2026-10-04

### Added
- **Uninstall script**: `tools/uninstall.sh` mirrors the installer (udev rule,
  desktop entry, optional `input` group removal, pip packages behind an explicit
  purge flag) with a root `./uninstall.sh` wrapper; the README keeps the manual
  procedure as a fallback.

### Changed
- **`main.py` split**: the 967-line `LinuxTaskApp` god object was reduced to
  UI and wiring (~507 lines); device capture, deduplication and timeline
  building moved to `src/recorder.py`, and replay, humanize jitter and macro
  validation to `src/playback.py`. No behavior change.
- **Wider CI**: the workflow now runs the X11, Hyprland and input-device
  suites alongside the core three — 6 suites, 68 tests, all headless-safe.

## [v3.0.3] - 2026-10-04

### Added
- **First-recording password warning**: the app now warns before the first
  recording that everything typed (including passwords) is captured, with
  a "Don't show again" opt-out persisted to `~/.config/linuxtask/config.json`;
  recording can be cancelled from the dialog, and stale hotkey actions are
  drained while it is open.

### Changed
- **English-first installer**: `tools/install.sh` and `tools/run.sh`
  messages standardized in English, and the README documents `tools/` as
  the canonical install path.
- **Honest status table**: the README lists KDE Plasma (Wayland) as tested
  by the author and Hyprland/GNOME/X11 as implemented but untested, with
  known limitations, manual uninstall steps, and an AI-assistance note.

### Fixed
- **Readable-only input devices on evdev 2.x**: device enumeration now
  calls `evdev.list_devices(writable=False)` (read-only access, matching
  the `0440` udev rule) with a no-arg fallback for evdev 1.x, instead of
  returning an empty list; an actionable warning dialog appears when no
  devices are accessible.
- **Arch-proof, PEP 668-safe installer**: `tools/install.sh` installs the
  distro evdev/xlib/Tk packages, creates a project `.venv`
  (`--system-site-packages`) so pip runs outside the externally-managed
  system Python (PEP 668, never `--break-system-packages`), fails fast with
  a logout notice, guards the real user under sudo, and smoke-tests the
  app; `tools/run.sh` prefers the venv.
- **Own virtual device excluded from listeners**: input listeners skip the
  app's `LinuxTask-Virtual` uinput device by name, stopping replay echo and
  hotkey re-triggering during playback.

## [v3.0.2] - 2026-10-04

### Changed
- **English-first README**: Portuguese survives only as a short footnote
  with a cross-link to the English guide.
- **Animated demo GIF**: shows keyboard-only record/replay on KDE Wayland
  instead of a static screenshot.
- **Quickstart heading style**: uses the plain style, matching the rest of
  the docs.
- **Prototypes quarantined**: the unfinished libei prototypes moved to
  `.quarantine/`, out of the AppImage payload.
- **Font patch retargeted**: the AppImage font patch targets the actual
  toolbar font size instead of a stale pattern that never matched.
- **Add-on-only dependencies**: `requirements.txt` marks numpy/Pillow as
  add-on-only rather than app dependencies.
- **Narrowed JSON ignore**: the global `*.json` ignore is narrowed so
  config files stay visible.
- **House-style rewrite**: changelog rewritten in one house style (plain
  Keep a Changelog, no emoji) from v3.0.1 down to v2.0.0.
- **Compare-link footer**: compare-link footer added, and dead links to
  the untagged v2.0.0/v2.2.0 removed.
- **Unreleased draining**: the release script now drains `[Unreleased]`
  into the new version heading and resets it, instead of leaving released
  notes on top as still pending.
- **Version-based base tag**: the script selects the base tag by version
  rather than commit distance, and keeps the footer links current.
- **Faithful dry run**: `--dry-run` previews the entry that will actually
  be published instead of a generated draft.

### Fixed
- **Per-event failure tally**: playback counts per-event failures and
  reports a summary afterward, so a replay with skipped events is visible.
- **Isolated bad timestamps**: a malformed event timestamp now fails that
  event only instead of aborting the whole macro.
- **Hyprland read fallback**: `get_cursor_pos()` returns `None` on read
  failure instead of `(0, 0)`, so a transient `hyprctl` failure falls back
  to uinput instead of jumping the cursor to the corner.
- **Shared portal screen size**: the KDE portal driver uses the shared
  screen-size attributes instead of private copies stuck at zero.
- **Missing hyprctl contained**: a missing `hyprctl` no longer escapes
  playback mid-macro via an unhandled `FileNotFoundError`.
- **No corner jump on failure**: X11/GNOME cursor reads return `None` on
  failure instead of `(0, 0)`, so a failed read aborts the move rather
  than jumping to the corner.
- **Immediate Stop response**: playback sleeps in slices that check the
  stop flag, so Stop responds immediately instead of after the full gap.
- **Bounded event dedupe**: event dedupe evicts partially through a deque
  instead of clearing wholesale, closing the double-fire window in long
  sessions.
- **Missing ydotool handled**: the GNOME driver returns early when the
  `ydotool` path is missing instead of raising `TypeError`.
- **Lock-guarded recorder state**: shared recorder state is now guarded
  by a lock across device threads and record/playback.
- **Backend call timeouts**: the automated portal steps time out after 15s
  instead of freezing the UI at startup (the `Start` call that waits for the
  user to approve the dialog keeps its 120s), and `xrandr`/`gdbus` calls pass
  a timeout like the other backends.
- **No shell invocation**: the release script passes an argument list
  with `shell=False`, closing tag-based shell injection.
- **Validated macro I/O**: macro save/load uses UTF-8 encoding and
  validates its input.

## [v3.0.1] - 2026-10-01

### Added
- **Image-click add-on**: `experimental/image_click/` finds an image on
  screen and clicks it, using grim capture with a pure-numpy NCC matcher.
- **Color-spin add-on**: `experimental/color_spin/` clicks in a loop until
  a target color appears, with a stability guard against animated false
  positives and a compact GUI with live log and start/stop buttons.
- **Independent add-on installer**: `experimental/install.sh` adds only
  numpy/Pillow, grim/slurp and desktop shortcuts; `--remove` cleans them
  up, and the main install neither includes nor requires the add-on.
- **Vision and capture helpers**: reusable `src/vision.py` (template
  matching, `color_fraction`) and `src/capture.py` (grim/slurp backend)
  used only by the add-on, so the app itself gains no new dependency.
- **Add-on tests**: `tests/test_experimental_addons.py` covers the add-on
  headless with fake backends; run manually, not in CI.

### Changed
- **Compact toolbar**: window reduced from 420x50 to 400x44 with 32px buttons
  and tighter spacing (TinyTask-inspired density); all controls keep their
  places, with smaller Open/Save labels, the 0.5x-10x speed selector, the
  settings gear and hover tooltips intact.
- **README and CONTRIBUTING rewrite**: both files rewritten for accuracy
  and professional tone, with a one-line quickstart in the README.
- **Release script placement**: new entries are inserted below the
  hand-written `[Unreleased]` section instead of prepended above it (the
  behavior at the time; the script now drains `[Unreleased]` under the new
  heading).

## [v3.0.0] - 2026-09-15

### Added
- **KDE Wayland support**: new driver using the Portal RemoteDesktop interface
  with dead-reckoning position tracking, re-synced once per playback.
- **Reproducible AppImage build**: `tools/appimage/build.sh` stages and
  patches the source for python-build-standalone (ASCII toolbar labels for
  the bundled Tk).
- **Core flow test suite**: new `tests/test_main_flow.py` with 38 headless
  unit tests for the heart of `main.py` (no display or hardware needed): event
  deduplication across devices, recording of keys/scroll/relative and absolute
  motion with `EV_SYN` flush, hotkey mapping and exclusion, humanize jitter
  bounds, playback dispatch with UInput fallback, speed scaling and stop
  interruption, macro validation and save/load roundtrip, and the thread-safe
  hotkey queue. Added to the CI workflow (`python-app.yml`).

### Changed
- **X11 driver rewrite**: `X11Driver` now uses `python-xlib` (XTest)
  instead of shelling out to `xdotool`.
- **Thread-safe hotkeys**: global hotkeys are dispatched to the UI thread via
  a queue; hover tooltips added for emoji-only toolbar buttons.
- **Monotonic timing**: macro recording and playback schedules use
  `time.monotonic()` instead of `time.time()`, making event deltas immune to
  NTP/DST clock jumps. Saved `.json` macros stay compatible (they store
  deltas, not absolute timestamps).

### Fixed
- **Missing dependency crashes**: `factory.py` now checks for `Xlib` (X11)
  and `dbus`/`gi` (KDE Wayland) **before** importing each driver and raises
  a clear `RuntimeError` with exact install instructions (apt/pacman/dnf)
  instead of a raw `ImportError`. `main.py` shows the message in a visible
  dialog rather than dying with a traceback.
- **KDE Wayland uninstallable out of the box**: `tools/install.sh` now
  installs the distro D-Bus bindings (`python3-dbus`/`python3-gi`) the
  portal driver needs; `run.sh` warns with manual commands when they are
  absent.
- **X11 fallback missing python-xlib**: `install.sh` and `run.sh` pip
  fallbacks now include `python-xlib` (previously only
  `customtkinter evdev`), so the generic X11 driver no longer fails to
  import on manual installs.
- **Implicit state**: `_rel_dx`/`_rel_dy` are now initialized in the app
  constructor instead of being created lazily inside `toggle_record()`;
  evdev listener threads no longer depend on record having run first.
- **Hyprland 0.55+**: cursor moves use the new Lua dispatcher
  (`hl.dsp.cursor.move`) with fallback to the legacy `movecursor` form.
- **Release script version regex**: `tools/release.py` now reads the
  `APP_VERSION` constant (the old pattern parsed a hardcoded version out of
  the window title and always failed) and mirrors the bump to
  `tools/appimage/pyproject.toml`.

### Security
- **Read-only input devices**: udev rule for `event*` devices changed from
  `0660` to `0440` — recording only needs read access, and write access on
  real input devices is a full injection primitive for any process in the
  `input` group. `/dev/uinput` stays `0660` (replay requires it).
- **Matching ACLs**: `install.sh` and `fix_linuxtask_perms.sh` now grant
  `u:USER:r` (not `rw`) on `/dev/input/event*`, so the immediate ACL grant
  cannot reopen the write access the udev rule closes.
- **Experiment quarantined**: the unfinished libei PoCs moved out of
  `src/drivers/` into `experimental/libei/` (with a README), and the compiled
  `ei_send` binary was removed — `build.sh` copies `src/drivers/` wholesale,
  so the AppImage no longer bundles stray artifacts.

## [v2.6.0] - 2026-04-07

### Added
- **Full Cinnamon/X11 support**: new driver using `xdotool` for absolute
  and relative movement on X11 desktops (Cinnamon, MATE, XFCE, and
  others).
- **Mouse scroll recording**: hardware-level capture of `REL_WHEEL` events
  with playback support across all drivers.
- **Improved hotkey configuration**: pressing Esc cancels hotkey
  remapping, and the UI confirms newly assigned keys immediately.
- **GNOME driver fallback**: mouse button handling via `ydotool` for
  better reliability when UInput is unavailable.
- **Enhanced documentation**: `README.md` rewritten with architecture
  diagrams, a support matrix, and an updated demo screenshot.
- **Improved installer**: `install.sh` refined so the desktop shortcut
  appears immediately and uses absolute paths.
- **CI automation**: GitHub Actions workflows added for automated testing
  and tagged GitHub Releases.

### Changed
- **UI refresh**: window width increased to `420px` to prevent text
  overlap, with the internal component structure refactored.
- **Cross-distro installation**: `install.sh` and
  `fix_linuxtask_perms.sh` detect and support `apt`, `pacman`, and `dnf`
  automatically.
- **Enhanced core precision**: relative movement accumulation logic
  refactored to eliminate coordinate drift and stuttering during
  playback.
- **Legacy cleanup**: the obsolete virtual-coordinates system removed in
  favor of the native compositor drivers.

### Fixed
- **Double-movement bug**: driver return values corrected so events no
  longer fire twice through UInput on Hyprland and GNOME.
- **Permission management**: input-device detection improved and
  permission grants automated via `setfacl`.
- **Theme consistency**: settings window background fixed to respect the
  user theme instead of a hardcoded color.
- **Release script regex**: version lookup supports dynamic window titles
  instead of matching only a hardcoded title.

## [v2.4.0] - 2026-03-01

### Added
- **Release automation script**: `tools/release.py` added to cut releases
  from conventional commits and update the changelog.
- **Professionalized documentation**: README overhauled and
  `CONTRIBUTING.md` added, giving new contributors a single entry point.
- **Standardized code headers**: license headers and PEP 8 compliance
  applied across all Python files for consistent tooling output.
- **Structural reorganization**: repository laid out into `src/`,
  `tests/`, `docs/`, and `tools/` so code, tests, docs, and helpers live
  apart.

### Changed
- **Hyprland driver validation**: driver covered with mocked unit tests,
  locking its behavior against regressions.
- **GNOME cursor research**: absolute cursor position on GNOME
  investigated with a PoC script kept as research, not shipped as a
  feature.
- **Dynamic screen resolution**: GNOME/Wayland resolution detected at
  runtime via `gdbus` and `xrandr` instead of assuming a fixed size.

### Fixed
- **GNOME driver crash**: missing screen-resolution attributes added to
  `GnomeDriver`, resolving the `AttributeError` on startup.

## v2.2.0 - 2026-03-01

### Added
- **Hardware access automation**: `fix_linuxtask_perms.sh` added to
  configure ACL and udev rules without manual steps.
- **Pure relative-movement engine**: relative movement logic implemented
  for GNOME Wayland users without absolute cursor reads.
- **Ydotool integration**: `ydotoold` daemon management optimized for
  Arch/CachyOS.

### Fixed
- **Delta-based tracking**: cursor movement now uses delta-based tracking
  so it no longer drifts.
- **Strict coordinate clamping**: coordinates are strictly clamped so the
  cursor no longer snaps to the corner.

## v2.0.0 - 2026-02-22

### Added
- **Humanize mode**: playback adds ±2px jitter and 0-3% timing delays so
  macros mimic human input more closely.
- **Settings black-screen fix**: the "black screen" bug on Wayland/Hyprland
  is fixed.
- **Better settings-window contrast**: contrast improved across the
  settings window.

### Changed
- **Stable desktop shortcut**: shortcut icon pinned to `input-mouse` for
  a consistent launcher appearance.
- **Movement-precision tests**: `test_jitter.py` added to cover movement
  precision with unit tests.

[Unreleased]: https://github.com/JADRT22/LinuxTask/compare/v3.1.2...HEAD
[v3.1.2]: https://github.com/JADRT22/LinuxTask/compare/v3.1.1...v3.1.2
[v3.1.1]: https://github.com/JADRT22/LinuxTask/compare/v3.1.0...v3.1.1
[v3.1.0]: https://github.com/JADRT22/LinuxTask/compare/v3.0.3...v3.1.0
[v3.0.3]: https://github.com/JADRT22/LinuxTask/compare/v3.0.2...v3.0.3
[v3.0.2]: https://github.com/JADRT22/LinuxTask/compare/v3.0.1...v3.0.2
[v3.0.1]: https://github.com/JADRT22/LinuxTask/compare/v3.0.0...v3.0.1
[v3.0.0]: https://github.com/JADRT22/LinuxTask/compare/v2.6.0...v3.0.0
[v2.6.0]: https://github.com/JADRT22/LinuxTask/compare/v2.4.0...v2.6.0
[v2.4.0]: https://github.com/JADRT22/LinuxTask/releases/tag/v2.4.0
