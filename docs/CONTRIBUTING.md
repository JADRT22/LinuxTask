# Contributing to LinuxTask

**How to report bugs, add drivers, and send pull requests.**

Thanks for helping with LinuxTask. This guide covers the workflow we use
to keep `main` stable across X11, GNOME Wayland, Hyprland and KDE Wayland.
If you are new here, start with the [README](../README.md) for features,
the [support matrix](../README.md#status), and the
[security model](../README.md#security-model).

## Ways to contribute

| Area | Examples | Where |
|---|---|---|
| Bug reports | Missing dependency dialog, cursor does not move, hotkeys do not fire | GitHub Issues |
| Driver fixes | New compositor support, coordinate drift, scroll fallback | `src/drivers/` |
| Core | Recording, playback dispatch, timing, persistence | `src/main.py` |
| Tests | Headless flow, jitter bounds, coordinate precision | `tests/` |
| Docs / tooling | README, troubleshooting, `install.sh`, AppImage | `docs/`, `tools/` |

Bug reports and driver fixes for other compositors are especially welcome —
each driver is a single file under `src/drivers/` behind a small abstract
interface.

Security reports take a different route: use the private disclosure
channel in [SECURITY.md](../SECURITY.md) rather than an issue, so a fix
can land before the problem is public.

## Getting started

### Requirements

- Python ≥ 3.10 with Tk
- `evdev`, `customtkinter`, `python-xlib` (installed by the setup script)
- **GNOME Wayland only**: a running `ydotoold` daemon
- **KDE Wayland only**: `python3-dbus` and `python3-gi` from your distro
  repositories (they cannot be built from PyPI without C headers)
- **Sway only**: `swaymsg` in `PATH` (ships with `sway`/`swayfx`)
- Membership in the `input` group and access to `/dev/uinput`
  (the installer configures both)

### Setup

```bash
git clone https://github.com/JADRT22/LinuxTask.git
cd LinuxTask
./tools/install.sh
```

The installer works with `apt`, `pacman` and `dnf`, installs the Python
dependencies, writes the `udev` rules, grants immediate ACL access and
creates a desktop entry. See [README](../README.md#getting-started) for
run instructions and troubleshooting.

Use a Python virtual environment for development; never commit `.venv/`,
`__pycache__/` or local macro JSON files.

## Repository organization

| Path | Contents |
|---|---|
| `src/main.py` | UI, recording timeline, playback dispatch, hotkeys |
| `src/drivers/` | One file per compositor behind `DesktopManager` + `factory.py` auto-detect |
| `tests/` | Headless suites run by CI, plus per-driver tests |
| `tools/` | `install.sh`, `run.sh`, `release.py`, AppImage build |
| `docs/` | Contributing guide and supplemental docs |
| `assets/` | Demo image and app icons |

## How to contribute

### Branching

```bash
git checkout -b feat/kde-scroll-fix
git checkout -b fix/wayland-detect
```

- Branch from `main` with a descriptive name: `feat/...`, `fix/...`,
  `docs/...`, `chore/...`.
- Keep one logical change per branch. Separate refactors from fixes.

### Commits

```bash
feat: add absolute move to KDE portal driver
fix: fall back to uinput when hyprctl move fails
```

- Follow Conventional Commits: `feat:`, `fix:`, `docs:`, `test:`, `chore:`.
- Write in imperative present tense, scope to what changed and why.
- The release script reads `APP_VERSION` and the changelog, so do not
  bump versions manually in feature branches.

### Pull requests

- Describe what changed, on which desktop/session it was tested
  (`XDG_CURRENT_DESKTOP`, `XDG_SESSION_TYPE`), and any limitations.
- Link related issues (`Fixes #12`).
- Ensure CI passes before requesting review.
- For new drivers, include the
  [support-matrix](../README.md#status) row that applies: click,
  absolute move, relative move, scroll, keyboard.

Checklist before opening:

- Tests pass locally (see below)
- `ShellCheck` passes for changed shell scripts
- Docs updated if behavior, requirements or troubleshooting changed
- No secrets, local paths or personal macro files included

## Coding standards

- **Python** — PEP 8, type hints where practical, descriptive docstrings
  on public functions and classes. Prefer `time.monotonic()` for timing,
  never wall-clock for scheduling.
- **Drivers** — all compositor drivers must inherit from `DesktopManager`
  and go through `factory.py` detection (`XDG_CURRENT_DESKTOP`,
  `XDG_SESSION_TYPE`, `HYPRLAND_INSTANCE_SIGNATURE`). Unknown Wayland
  sessions must warn explicitly, never silently use the wrong driver.
- **Shell** — `#!/usr/bin/env bash` with `set -euo pipefail`,
  compatible with `ShellCheck`, works on `apt`, `pacman` and `dnf`
  paths when touching the installer.
- **Naming** — clear and descriptive (`event_handler`, not `ev_h`).
- **Headers** — every new source file must include license, author
  and a brief description.

## Tests

```bash
# Everything, headless — the CI command:
.venv/bin/python -m pytest tests -q --timeout=120

# Same suites, stdlib runner (no pytest needed):
.venv/bin/python -m unittest discover -s tests -t .

# Lint (rules and their documented exemptions live in pyproject.toml):
.venv/bin/python -m ruff check .
```

Run from the repo root. `pip install -r requirements-dev.txt` gets you
pytest, pytest-cov, pytest-timeout and ruff; `tools/install.sh` already
created the `.venv` these commands use, and each suite prepends `src/`
to `sys.path` internally (alternatively, run with `PYTHONPATH=src`).

Collection is directory-based, so a new file under `tests/` reaches CI
without editing a workflow. What to know before writing one:

- The core flow suite exercises recording, playback dispatch, macro
  validation and persistence headlessly by instantiating the app without
  a display or a mainloop.
- Per-driver suites fake the IPC (subprocess output, D-Bus replies) —
  never a live session, so the suite runs on a headless runner.
- `tests/test_kde_wayland.py` and `tests/test_experimental_addons.py`
  skip themselves when the distro bindings (`python-dbus`, `python-gi`,
  numpy, Pillow) are missing. The `distro-bindings` CI job installs them
  and runs the whole suite, so they do execute somewhere; a skip on your
  machine normally just means a package is missing.
- `.quarantine/tests/test_evdev_access.py` is a manual hardware check and
  is not collected.
- Packaging and installation have their own guards —
  `test_appimage_smoke_coverage.py`, `test_appimage_ui_patch.py`,
  `test_python_lock.py`, `test_setup_scripts.py` — because an AppImage or
  installer breakage is otherwise invisible until a build or a user fails.
- Add or update tests with behavior changes. A bug fix without a
  regression test will be asked to include one.

## Issue policy

- Search existing issues before opening a new one.
- Include: distro + version, desktop + session type
  (`echo $XDG_CURRENT_DESKTOP $XDG_SESSION_TYPE`),
  Python version, install method, logs and steps to reproduce.
  For UI font issues, also include `fc-list | grep -i emoji`.
- Issues without reporter feedback for 30 days may be closed as stale.
  Reopen with the requested info and we will take another look.

## Security

Input capture reads from `/dev/input/event*` (read-only `0440`) and
replay writes only to a virtual `/dev/uinput` device or compositor APIs.
Never open pull requests that:

- grant write access to physical input devices,
- bypass the `udev` least-privilege rules,
- log or exfiltrate keystrokes outside the local macro file.

See [Security model](../README.md#security-model). Report suspected
vulnerabilities privately via GitHub Security Advisories instead of
public issues.

## License

MIT — see [LICENSE](../LICENSE). By contributing you agree your changes
are distributed under the same license.

## Code of Conduct

Be professional and respectful. Focus on technical merit, reproducible
results and clear architecture. Harassment, spam or low-effort AI bulk
contributions will be closed.
