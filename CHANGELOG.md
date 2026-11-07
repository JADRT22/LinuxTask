# Changelog

All notable changes to the LinuxTask project will be documented in this file.
The `[Unreleased]` section collects changes since the last release;
`tools/release.py` moves its body under the new version heading when a
release is cut and resets it to empty, so released notes never linger
as pending. Releases v2.0.0 and v2.2.0 predate the project's git tags,
so their headings carry no compare links (v2.2.0 is also listed with the
same date as v2.4.0, and with no tag that date cannot be checked).

## [Unreleased]

## [v3.5.3] - 2026-11-07

### Fixed
- **`linuxtask --version` no longer opens a window.** `main()` only handed
  off to the headless CLI when the first argument was `play`, `-h` or
  `--help`, so an unknown flag — or a subcommand typed wrong, `paly
  macro.json` — fell through to the GUI branch and launched the app.
  Anything on the command line now goes to the CLI and argparse answers
  with exit 2 and a usage line; a bare `linuxtask` still starts the GUI.
  Neither launcher passes arguments (`Exec=AppRun` in the AppImage desktop
  entry, `Exec="$ABS_RUN_PATH"` from the installer), so nothing that used
  to work changes.
- **KDE Wayland reads the Plasma 6.8 layout again (issue #7).** That
  `kscreen-doctor --json` puts each output's size on the output itself,
  next to `currentModeId` and `modes`, and marks the primary with
  `priority: 1` instead of a `primary` flag. The reader only looked inside
  `mode`/`currentMode`, so it dropped every output, detection fell through
  to the `kscreen-doctor -o` listing, and the clamp box became the first
  panel kscreen prints -- on the reporter's desk the 1600x1200 secondary,
  listed ahead of his 2560x1440 primary. Making the main monitor primary
  in kscreen could not help: the listing order does not follow priority.
  The size is now read from the output when no mode object is present, and
  `priority: 1` counts as primary. On his own JSON that gives
  `Resolution (kscreen-json): 2560x1440, layout 4160x1440+0+0`, the same
  4160x1440 kscreen declares as `screen.currentSize`.

### Documentation
- **The README points at the download, and counts four CI jobs.** Nothing
  in it told a reader that `LinuxTask-x86_64.AppImage` is on the release
  page -- the one thing v3.5.0 and v3.5.1 were missing -- and the tests
  section still said "three jobs" after the `appimage` job was added to
  close that class of failure.

## [v3.5.2] - 2026-11-06

This is the release that has the download. `v3.5.0` and `v3.5.1` were both
published with an empty asset list: the AppImage built here and then failed
on GitHub's machine - once at v3.5.0, once at v3.5.1, once more on a push -
over five separate causes: the path the workflow attached from, `meson` and
`patchelf` missing from the build environment's `PATH`, a wheel built at the
wrong version, `girepository-2.0` shipped under a different package name
than the apt list used, and the two below. Nothing in the recorder changed
since v3.5.1.

Why a clean machine notices things this one does not: `build/appimage/wheels`
still holds the output of an older bootstrap, and the build skips the step
that already has an artifact. Deleting that directory is what the runner does
by definition, so from now on CI does it on every push (below).

### Fixed
- **The AppImage is attached to this release**, built by CI from a clean
  checkout: `LinuxTask-x86_64.AppImage`.
- **PyGObject now finds pycairo's C headers from this build, not from the
  host.** PyGObject's build looks `cairo` up by importing it with the
  interpreter it is compiling for; the loop that source-builds pycairo never
  installed it into its own scratch environment, so on a runner the import
  failed, the pkg-config fallback found nothing either, and cc stopped at
  `fatal error: py3cairo.h`. Arch hosts hide that: their `python-cairo`
  answers the fallback with headers of a pycairo that is not the one that
  ships in the bundle. Each built wheel now goes back into the build
  environment, and PyGObject is not attempted unless `import cairo` answers.
- **The build names every host dependency its own sdists ask for.** The
  preflight went from three hand-picked `pkg-config` names to the full
  `dependency()` list of the pinned pycairo, dbus-python and PyGObject,
  versions included (`girepository-2.0 >= 2.80`, `libffi >= 3.0`,
  `cairo-gobject`...), and the Ubuntu packages that provide them live in one
  script that both workflows call instead of a list copy per workflow. A
  missing or too-old module now costs one `pkg-config` call and prints
  `PyGObject -> girepository-2.0 (not installed)`; before, it surfaced
  seconds or minutes later inside a meson stack trace that named a
  subprocess instead of the package to install.
- **The AppImage build is a CI job, not a tag-time surprise.** `Python CI`
  gained an `appimage` job that installs the dependencies, runs the whole
  documented build - including the smoke guard that imports every driver
  with the bundled interpreter - and checks the artifact exists. It found
  the pycairo defect on its first run, 39 seconds into a push, with nothing
  published.

## [v3.5.1] - 2026-11-05

A patch for the download itself. `v3.5.0` produced an AppImage that ran here
and failed on GitHub's clean runner, so that release went out without the
artifact - which is the one thing most readers of the release page came to
get. Nothing about the recorder changed.

The build script had been leaning on state a developer machine has and a
runner does not: build tools already on `PATH`, and a local wheel cache that
was hiding three separate packaging faults behind one green "build ok". Each
is fixed at its own level, and each has a guard test that fails against the
pre-fix script.

### Fixed
- **The AppImage builds on a clean checkout.** `meson`, `meson-python`,
  `ninja`, `patchelf`, `setuptools` and `wheel` are now installed inside the
  bundled build environment and that environment's `bin` is put on `PATH`
  before wheels are compiled, so the build no longer stops at
  `meson executable "meson" not found` or at `FileNotFoundError: 'patchelf'`
  in the RPATH step.
- **The wheels that ship are the wheels that are pinned.** The build asked
  pip for a bare package name and got whatever was newest (`dbus-python`
  1.5.1 while the project pins 1.5.0); it now derives the version from the
  pinned filename it is about to produce.
- **A wheel with no compiled extension is an error, not an artifact.** The
  probe that rejects a platform-tagged wheel containing only Python files ran
  before the check that the pinned wheel exists at all, so a version mismatch
  reported "contains no compiled extension" out of a `FileNotFoundError`. The
  existence check now comes first and the failure names the exact file to
  delete and rebuild.

## [v3.5.0] - 2026-11-05

The point of this release is playing a macro back across more than one
monitor: a recording made on a second screen no longer folds onto the first
one (#6, #7). The second visible change is that `v3.5.0` is the first release
that carries an AppImage - the build existed and worked, but nothing published
it, so the download the README pointed at was never there. Everything else is
what those two changes exposed: the installer stopped running `pip install` on
launch, the Wayland IPC paths started checking who answers, and CI now runs
the suite on every Python the project promises rather than on the one that
happened to be configured.

### Fixed
- **Multi-monitor playback (#6, #7).** The clamp box is the union of every
  enabled output rather than the geometry of the single output the driver
  happened to read, so coordinates on a second screen - or one placed left of
  or above the origin - are legal space and not an edge. Hyprland enumerates
  `hyprctl monitors -j`, Sway `swaymsg -t get_outputs`, KDE takes the union
  from `kscreen-doctor --json` with the text listing and `xrandr` as
  fallbacks (that pattern now accepts a negative offset, which the old
  `+`-only regex silently dropped for every monitor above the primary), and
  X11's root window already spans every CRTC. A detection that finds nothing
  falls back to 1920x1080 instead of a 0x0 box that pins the whole timeline
  to one pixel in silence.
- **A compositor refusal is honoured again.** `move_cursor`/`move_relative`
  return a bool across all five drivers, so playback's `uinput` warp fallback
  is reachable when the driver says no - and it warps the clamped coordinates
  rather than the raw event.
- **"Humanize" does what the label claimed.** Point jitter, delta jitter (up
  to 2 px per axis) and inter-event timing variance (0-3 % on top of the speed
  factor) are three primitives now; the old helper jittered nothing and only
  ever saw the delta path.
- **Settings stop going intermittent on long replays.** Speed and humanize
  are read through plain attributes that the Tk variables mirror, because
  reading a Tkinter variable from the replay thread is not safe.
- **The first events of a recording are no longer dropped:** `toggle_record`
  arms the capture thread last, since `device_loop` starts as soon as the flag
  is true.
- **A missing compositor dependency raises a dialog instead of killing the
  window** (`python3-dbus` absent on KDE Wayland, an unsupported desktop), and
  the title bar derives the desktop name from the driver in use.
- **`tools/run.sh` never installs packages at launch.** It checks the three
  imports it needs, names the script that fixes them and exits; the automatic
  `pip install --user` it replaced could half-populate a user site, fail on a
  managed environment, or reach the network on every start.
- **`tools/install.sh` stopped expanding a username through `eval`** in favour
  of a `getent passwd` lookup retried by uid, with an undeterminable home as a
  hard error; on GNOME Wayland it now installs `ydotool` and verifies both the
  client and `ydotoold`, because absolute warps need the daemon.
- **Python 3.10 installs again.** evdev 2.0 declares `Requires-Python >=3.11`
  while the pin carried no marker, so pip could not resolve it there - which
  made `tools/install.sh` fail on Ubuntu 22.04 and Debian 11 and advertised a
  support floor that was a claim rather than a fact. The pin is split by
  interpreter now (2.0.0 on >=3.11, 1.9.3 on 3.10), and CI exercises both -
  the 1.x branch is also what the distro `python3-evdev` packages ship.
- **The AppImage bundles a working evdev.** pip's global wheel cache is keyed
  by name and ABI, not by whether the C extensions actually compiled, so a
  stale cache entry from an earlier failed build shipped a wheel whose
  `import evdev` died on the user's machine. evdev is now source-built against
  the bundled interpreter's ABI with `--no-cache-dir`, and every wheel is
  checked for a `.so` before the build continues.

### Security
- **The Wayland IPC paths verify who answers.** On a shared session bus any
  process could reply to the KWin scripting probe or emit a portal `Response`
  signal, and the GNOME Shell bridge accepted warp requests from anyone. KDE
  now trusts only replies from the cached unique names of `org.kde.KWin` and
  `org.freedesktop.portal.Desktop`, tags every read with its own nonce so a
  reply cannot be replayed from an earlier one, and uses a random request
  handle instead of a time-derived one. The GJS extension refuses an
  invocation whose uid is not the uid it runs as, and the Python side confirms
  the bridge's owner through `GetConnectionUnixUser` before believing a
  coordinate. The rule throughout: fail-open only for the first call, while no
  name is known yet; fail-closed on a mismatch.
- **`SECURITY.md` replaced a template with this app's actual threat model** -
  what is in scope (command injection through `hyprctl`/`swaymsg`/`xdotool`/
  `ydotool`/`gdbus`/`kscreen-doctor`/`xrandr`, the D-Bus and portal trust
  decisions, the GNOME bridge), what is not, and that disclosures go to the
  private advisory form rather than an issue.

### Changed
- **The release carries the AppImage.** `release.yml` gained a job that
  installs the build dependencies, runs `tools/appimage/build.sh`, refuses an
  empty artifact and attaches the result to the release the previous job
  created. The build publishes it at the documented
  `build/appimage/dist/LinuxTask-x86_64.AppImage`, which is the path the
  workflow attaches and was not the path the builder produced.
- **The bundled interpreter is pinned and verified.**
  `tools/appimage/python-build-standalone.lock` records the release tag, the
  Python version, the URL and the sha256; `build.sh` refuses an incomplete
  pin or a URL that disagrees with its own tag, re-downloads a cached tarball
  whose digest stopped matching, and publishes the cache only after
  `sha256sum --check`. `update_python_lock.py` re-pins from the release API.
  The ASCII toolbar rewrite moved out of a heredoc into `patch_ui.py`,
  asserted against the real `src/main.py`.
- **CI is three jobs instead of one hand-listed script**: a matrix over
  3.10/3.11/3.12/3.13/3.14 running pytest with coverage and then
  `unittest discover` (README documents it as the no-pytest path), a
  `distro-bindings` job on ubuntu-24.04 where the KDE driver's suite actually
  runs, and a ruff lint job. The suites that need a distro-only binding skip
  instead of erroring when it is absent, and the runners got the packages a
  distribution CPython does not build in (`python3-tk`, `python3-pil.imagetk`).
- **Tooling at the repository root**: `pyproject.toml` with the pins, the
  Python floor and the lint/test configuration, `requirements-dev.txt`,
  `tests/__init__.py` doing the `sys.path` insert once instead of ten test
  files repeating it, and Dependabot for pip and Actions.
- **Documentation:** the README's multi-monitor section describes the layout
  box the drivers now read and names the
  `<driver> resolution: WxH, layout WxH+X+Y` start-up line as the thing to
  paste into a report; the troubleshooting table gained the wrong-monitor row;
  the development section describes what actually runs, and
  `docs/CONTRIBUTING.md` points at `SECURITY.md`.
- **Test suite: 175 tests at v3.4.1, 294 here**, passing on every interpreter
  CI covers, with the cross-driver contract suite pinning the bool return, the
  layout union and the log shape.

## [v3.4.1] - 2026-10-24

### Changed
- **Adwaita-flavored visual polish (chrome only)**: the dark UI now uses an
  explicit neutral palette - `#303030` window background, `#3a3a3a` button
  fill - with a discreet 1px outline on every toolbar button, lighter hover
  overlays on the neutral buttons and the flat settings gear, and the speed
  drop-down restyled from the CustomTkinter blue theme to flat gray (its
  height now matches the 32px button rhythm). Fonts are unified on DejaVu
  Sans (speed menu, settings window, first-recording dialog, tooltip), and
  "Open"/"Save" got wider buttons so their labels sit inside the new outline.
  Recording, playback, hotkeys and every driver keep their exact behavior
  and state colors (red/green/blue/orange); the toolbar is still the same
  400x44 window with the same controls, no new options or dependencies.

## [v3.4.0] - 2026-10-24

### Added
- **GNOME Wayland absolute mode** via a GNOME Shell cursor-bridge
  extension (`extensions/gnome-shell/linuxtask-cursorbridge@jadrt22`):
  `global.get_pointer()` for the real pointer position and
  `seat.warp_pointer()` for true absolute replay — the same pattern the
  KDE driver uses with KWin scripting, and the same one Keymasq/PaperWM
  use. Install with `tools/install-gnome-bridge.sh` (one logout/login on
  first install); `tools/uninstall.sh` removes it. The GNOME driver
  prefers the bridge for `get_cursor_pos()`, `move_cursor()` and exact
  `GetScreenSize()` resolution, degrades to the legacy relative-delta +
  xdotool/tkinter fallback when it is absent or dead (same escalate/skip
  rule as the KWin probe), and `python-dbus` stays optional for GNOME —
  calls go in-process when it is importable, short-lived `gdbus`
  subprocesses otherwise. New headless suite `tests/test_gnome_driver.py`
  joins CI.
- The one-time "Driver warning" dialog now shows the driver's own
  message (`warn_fn` no longer discards it) instead of the
  KDE-portal-specific hard-coded text, so the GNOME delta-fallback and
  bridge-degrade warnings are described correctly.

## [v3.3.0] - 2026-10-16

### Added
- **Headless `play` CLI** (issue #5): scripts can now replay a saved macro
  without the GUI - `linuxtask play macro.json [--speed N] [--loop]
  [--humanize] [--start-pos X,Y]`, also reachable as
  `./tools/run.sh play ...` and
  `python src/cli.py play ...`. `src/cli.py` reuses
  `Playback.playback_thread` verbatim, supplying the window-owned
  attributes (speed/humanize variables, loop flag, UI queue) as plain
  stand-ins, so the replay path is the same code the toolbar runs. The
  macro file is validated with the same `_validate_event` as
  `open_file`, and the compositor driver plus the uinput device are only
  opened after it validates, so a bad path can never pop a portal dialog.
  The README documents the macro JSON format, so a script can generate a
  macro instead of recording one in the GUI first.
  Exit codes: `2` invalid macro, `1` unsupported desktop, `130` on Ctrl+C.
  `main.py` routes `play`/`-h`/`--help` to the CLI and everything else to
  the GUI; the AppImage ships the module and its smoke guard imports it.

### Known issues
- **`src/cli.py` exited with SIGSEGV once in a 42-run batch** (exit code
  `-11` instead of `0`). Not reproduced in 30 later runs under
  `-X faulthandler`, which produced no traceback, so whether the crash is
  during replay or at teardown is unknown.

## [v3.2.1] - 2026-10-10

### Fixed
- **KDE Wayland absolute moves landed at the wrong coordinates**: a live
  cursor read never fed the driver's dead-reckoning origin. `_cur` starts
  at `(0, 0)` and was only ever updated by `sync_for_playback` or
  `move_relative`, so `move_cursor` computed every delta from the corner
  of the screen — asking for `(400, 300)` moved the pointer by
  `(+400, +300)` from wherever it happened to be instead of to that
  coordinate. `get_cursor_pos` now writes the position it reads into
  `_cur`, for the KWin source and for the xdotool fallback alike, so a
  single read before an absolute move is enough to anchor it. Relative
  moves, scroll and buttons were unaffected. Verified live against the
  running portal: 4/4 warps exact within 3 px, with and without a prior
  `sync_for_playback`.
- **Absolute moves no longer vanish when a driver refuses them**: a `pos`
  event called `move_cursor` and, on `False`, only queued the one-shot
  driver warning — the cursor went nowhere and the macro replayed as
  nothing. Every other event type (`rel`, `scroll`, `key`) already fell
  back to the virtual `uinput` device; the absolute path was the only
  one without a fallback. The refused move now decomposes into a delta
  from the driver's last known position and is written as `EV_REL`, which
  the kernel accepts regardless of driver state. The same fallback covers
  the start-position warp at the top of each playback pass, where a dead
  driver used to leave the pointer wherever the previous pass ended and
  loop repeats drifted.
- **The first absolute move of a session now lands on target**: nothing
  read the cursor position before the first `move_cursor`, so the
  dead-reckoning origin was still cold `(0, 0)` and the pointer ended up
  at `(real + target)`. This broke both halves of the app — recording
  (the first click of a macro) and replay (the first `pos` event) — and
  survived the fix above, because that one only anchors the origin once a
  read has already happened. `move_cursor` now anchors a cold origin with
  one live read before computing its delta, so a driver that never went
  through `sync_for_playback` still lands correctly.
- **A failed cursor read no longer freezes the tracked origin**: the lazy
  anchor marked the position initialised before it knew the read had
  succeeded, so a single unreadable position (no KWin scripting, no
  xdotool, no XWayland) left the origin stuck at `(0, 0)` for the rest of
  the driver's life. The flag is now set only on a successful read, and
  the next absolute move tries to anchor again instead of dead-reckoning
  from the screen corner forever.

## [v3.2.0] - 2026-10-10

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
- **The AppImage smoke guard imports every driver**: it listed the split
  modules, the D-Bus stack and the UI stack, but no driver module — the Sway
  driver could have shipped (and did ship) with a broken import. The guard now
  imports `drivers.sway`, `x11`, `gnome`, `hyprland` and `kde_wayland` plus
  `Xlib` with the bundled interpreter, and
  `tests/test_appimage_smoke_coverage.py` reads the guard out of `build.sh`
  and fails when a module under `src/drivers/` is missing from it, so the gap
  cannot reopen. Verified by a full AppImage rebuild with the guard expanded.

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

[Unreleased]: https://github.com/JADRT22/LinuxTask/compare/v3.5.3...HEAD
[v3.5.3]: https://github.com/JADRT22/LinuxTask/compare/v3.5.2...v3.5.3
[v3.5.2]: https://github.com/JADRT22/LinuxTask/compare/v3.5.1...v3.5.2
[v3.5.1]: https://github.com/JADRT22/LinuxTask/compare/v3.5.0...v3.5.1
[v3.5.0]: https://github.com/JADRT22/LinuxTask/compare/v3.4.1...v3.5.0
[v3.4.1]: https://github.com/JADRT22/LinuxTask/compare/v3.4.0...v3.4.1
[v3.4.0]: https://github.com/JADRT22/LinuxTask/compare/v3.3.0...v3.4.0
[v3.3.0]: https://github.com/JADRT22/LinuxTask/compare/v3.2.1...v3.3.0
[v3.2.1]: https://github.com/JADRT22/LinuxTask/compare/v3.2.0...v3.2.1
[v3.2.0]: https://github.com/JADRT22/LinuxTask/compare/v3.1.2...v3.2.0
[v3.1.2]: https://github.com/JADRT22/LinuxTask/compare/v3.1.1...v3.1.2
[v3.1.1]: https://github.com/JADRT22/LinuxTask/compare/v3.1.0...v3.1.1
[v3.1.0]: https://github.com/JADRT22/LinuxTask/compare/v3.0.3...v3.1.0
[v3.0.3]: https://github.com/JADRT22/LinuxTask/compare/v3.0.2...v3.0.3
[v3.0.2]: https://github.com/JADRT22/LinuxTask/compare/v3.0.1...v3.0.2
[v3.0.1]: https://github.com/JADRT22/LinuxTask/compare/v3.0.0...v3.0.1
[v3.0.0]: https://github.com/JADRT22/LinuxTask/compare/v2.6.0...v3.0.0
[v2.6.0]: https://github.com/JADRT22/LinuxTask/compare/v2.4.0...v2.6.0
[v2.4.0]: https://github.com/JADRT22/LinuxTask/releases/tag/v2.4.0
