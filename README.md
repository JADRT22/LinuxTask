# LinuxTask

**A minimalist macro recorder for Linux with hardware-level input capture.**

[![Release](https://img.shields.io/github/v/release/JADRT22/LinuxTask?style=flat-square)](https://github.com/JADRT22/LinuxTask/releases)
[![CI](https://img.shields.io/github/actions/workflow/status/JADRT22/LinuxTask/python-app.yml?style=flat-square&label=tests)](https://github.com/JADRT22/LinuxTask/actions/workflows/python-app.yml)
[![License](https://img.shields.io/github/license/JADRT22/LinuxTask?style=flat-square)](LICENSE)
[![Stars](https://img.shields.io/github/stars/JADRT22/LinuxTask?style=flat-square)](https://github.com/JADRT22/LinuxTask/stargazers)

LinuxTask records and replays keyboard and mouse actions on X11 and Wayland.
Recording reads events directly from the kernel via `evdev`, so nothing is
lost even when the desktop is under load. Replay uses a virtual `uinput`
device or the native APIs of your compositor, which sidesteps the input
injection restrictions that Wayland compositors impose on traditional X11
automation tools.

![LinuxTask demo](assets/demo.png)

## Features

- **Cross-desktop drivers** — native backends for X11 (Cinnamon, MATE, XFCE…),
  GNOME Wayland, Hyprland and KDE Wayland, auto-detected at startup.
- **Hardware-precision capture** — raw `evdev` event reading with
  deduplication across multiple input devices and `time.monotonic()`-based
  scheduling, immune to NTP and DST clock jumps.
- **Full mouse support** — absolute and relative movement, button clicks and
  scroll wheel, with automatic fallback to the virtual `uinput` device when a
  compositor cannot handle an action.
- **Humanize mode** — optional ±2 px positional jitter and 0–3 % timing
  variance so replays do not look machine-perfect.
- **Playback control** — 0.5×–10× speed, loop mode, stop-at-any-time.
- **Portable macros** — a single JSON file holding the event timeline and the
  starting cursor position.
- **Global hotkeys** — record and play from any window (F8/F9 by default,
  fully remappable).
- **Compact UI** — a 400×44 px toolbar built with CustomTkinter that stays out
  of the way.

## Supported environments

| | X11 desktops | GNOME Wayland | Hyprland | KDE Wayland |
|---|---|---|---|---|
| **Driver** | `python-xlib` (XTest) | `ydotool` | `hyprctl` | XDG Portal (RemoteDesktop) |
| Mouse click | ✅ | ✅ | ✅ (uinput) | ✅ |
| Absolute move | ✅ | ❌ (emulated by deltas) | ✅ | ✅ (dead-reckoned, re-synced per playback) |
| Relative move | ✅ | ✅ | ✅ | ✅ |
| Scroll | ✅ | ✅ | ✅ (uinput) | ✅ |
| Keyboard | ✅ (uinput) | ✅ (uinput) | ✅ (uinput) | ✅ |

The driver is selected automatically from `XDG_CURRENT_DESKTOP`,
`XDG_SESSION_TYPE` and `HYPRLAND_INSTANCE_SIGNATURE`; unsupported desktops
with a running X server fall back to the X11 driver.

## How it works

```mermaid
graph TD
    UI[CustomTkinter UI] -->|commands| Factory[Driver Factory]
    Factory -->|auto-detect| X11[X11Driver · XTest]
    Factory -->|auto-detect| Gnome[GnomeDriver · ydotool]
    Factory -->|auto-detect| Hypr[HyprlandDriver · hyprctl]
    Factory -->|auto-detect| Kde[KdeWaylandDriver · Portal]

    Listener[evdev Listener threads] -->|raw events + dedupe| Queue[Event Timeline]
    Queue -->|replay| UInput[Virtual uinput Device]
    Queue -->|replay| Driver[Compositor Driver]
```

- **Recording**: one listener thread per input device pushes keyboard, mouse
  and scroll events into a timeline. Motion is flushed on `EV_SYN` report
  boundaries — absolute coordinates when the driver supports them, relative
  deltas otherwise.
- **Playback**: the timeline is replayed at the chosen speed through the
  compositor driver first and the virtual `uinput` device as fallback, with
  optional humanize jitter applied per movement.
- **Hotkeys**: global F8/F9 presses are detected by the same evdev listeners
  and dispatched to the UI thread through a queue, keeping tkinter calls on
  the main thread.

## Getting started

### Requirements

- Python ≥ 3.10 with Tk
- `evdev`, `customtkinter`, `python-xlib` (installed by the setup script)
- **GNOME Wayland only**: a running `ydotoold` daemon
- **KDE Wayland only**: `python3-dbus` and `python3-gi` from your distro
  repositories (they cannot be built from PyPI without C headers)
- Membership in the `input` group and access to `/dev/uinput`
  (the installer configures both)

### Install

```bash
git clone https://github.com/JADRT22/LinuxTask.git
cd LinuxTask
./tools/install.sh
```

The installer works with `apt`, `pacman` and `dnf`, installs the Python
dependencies, writes the `udev` rules, grants immediate ACL access (no
logout needed in most cases) and creates a desktop entry.

### Run

```bash
./tools/run.sh
```

Or look for **LinuxTask** in your application menu.

## Usage

| Control | Action |
|---|---|
| `●` / `■` | Start / stop recording (default hotkey **F8**) |
| `▶` / `■` | Play / stop playback (default hotkey **F9**) |
| `↻` | Toggle loop playback |
| Speed menu | Playback speed from 0.5× to 10× |
| `⚙` | Settings: remap hotkeys (press `Esc` to cancel), enable Humanize |
| Open / Save | Load / store macros as JSON files |

Hotkeys work globally: press F8 or F9 in any application. Recorded macros
store the event timeline plus the starting cursor position, and playback
returns the cursor there first so repeats are deterministic.

## Security model

Input capture only needs to *read* devices; it never writes to them. The
bundled `udev` rules therefore grant:

- `/dev/input/event*` — **read-only** (`0440` + matching read-only ACL):
  enough for recording, while withholding the full injection primitive that
  write access on real keyboards would give any process in the `input` group.
- `/dev/uinput` — read/write (`0660`): replay creates a *virtual* device, so
  injected events go through the kernel's sanctioned input path or through
  compositor APIs, never into your physical devices.

## Development

### Tests

```bash
# Hardware- and display-independent suites (the ones CI runs):
python -m unittest tests.test_main_flow tests.test_jitter tests.test_coordinate_precision
```

The core flow suite exercises recording, playback dispatch, macro validation
and persistence headlessly by instantiating the app without a display.
`tests/test_x11_driver.py` and `tests/test_hyprland_driver.py` additionally
mock or exercise drivers individually.

### Release process

```bash
python3 tools/release.py --bump minor [--dry-run]
git push origin main --tags
```

The script bumps `APP_VERSION` (mirrored to the AppImage project), prepends a
changelog entry below the hand-written `[Unreleased]` section, commits and
tags. Pushing a `v*` tag triggers the GitHub Actions workflow that publishes
the release with the changelog entry as notes.

### AppImage

```bash
tools/appimage/build.sh
```

Builds a reproducible AppImage on top of python-build-standalone.

## Troubleshooting

| Symptom | Fix |
|---|---|
| `Permission denied` on start | Re-run `./tools/install.sh` to refresh `udev` rules and group membership |
| Cursor does not move | Check the driver's external dependency: `ydotool` daemon running (GNOME Wayland), `hyprctl` in `PATH` (Hyprland), portal permission granted (KDE Wayland) |
| Hotkeys do not fire | Verify the `input` group: `groups $USER` — re-login after being added |
| Missing dependency dialog | Follow the printed instructions (`python-xlib` via pip; `python3-dbus`/`python3-gi` via your package manager) |

## Contributing

See [CONTRIBUTING.md](docs/CONTRIBUTING.md). Bug reports and driver fixes for
other compositors are especially welcome — each driver is a single file under
`src/drivers/` behind a small abstract interface.

## License

MIT — see [LICENSE](LICENSE).
