# AppImage update notifier and downloader — design

Date: 2026-11-07 · Status: approved for implementation · Target: LinuxTask v3.6.0

## Purpose

A user running the AppImage has no way to learn that a newer release exists.
The `v3.5.2` bundle shipped without the KDE multi-monitor fix and stayed on
users' disks until they happened to revisit the release page; issue #7 is
exactly that story. This feature tells the user, inside the app, that a newer
release is published, and lets them download and install it without leaving
the app.

Scope is the AppImage only. A git checkout or a `tools/install.sh` install
gets nothing: no badge, no Settings section, no network call.

## What was verified before designing

These are measurements on the published `v3.5.3` artifact, not assumptions:

| Claim | Evidence |
|---|---|
| The runtime exports `APPIMAGE` as the absolute path of the running file | Captured from `/proc/<pid>/environ` of a real `LinuxTask-x86_64.AppImage play probe.json --dry-run` child: `APPIMAGE=/tmp/upd-probe/LinuxTask-x86_64.AppImage`, `APPDIR=/tmp/.mount_LinuxTCdJGib` |
| Replacing the file while it runs is safe | `os.replace` over a mounted AppImage succeeded; the mount kept serving `AppRun` byte-for-byte afterwards, and `/proc/<pid>/exe` read `…/LinuxTask-x86_64.AppImage (deleted)` — the runtime holds the old inode through 3 open descriptors |
| GitHub publishes a per-asset digest | `releases/latest` for `v3.5.3` returns `digest: sha256:70653098…fdf7`; the file downloaded from the public URL hashes to exactly that |
| The bundle's own interpreter reports the version | `linuxtask_main.APP_VERSION` → `3.5.3`, with `evdev`, `customtkinter`, `Xlib`, `cairo`, `gi`, `dbus` all importing |

The second row is the reason the install step can be a plain `os.replace`.
Writing into the running file in place would corrupt the live squashfs mount
and is explicitly not done.

## Constraints carried from the existing code

- **The window is a 400×44 topmost toolbar** (`src/main.py:146`), seven grid
  columns, no status bar, not resizable. A banner would change the geometry
  of the app's whole visual identity. The notice must fit in what is there.
- **Tk is never touched from a worker thread.** The rule is written at
  `src/main.py:178-181`; workers push a string token onto `_ui_queue` and
  store detail on a plain attribute, and `_poll_hotkeys` (UI thread, every
  50 ms) does the rest. `_driver_warn_fn` at `src/main.py:270` is the exact
  pattern to copy.
- **Config already exists**: `app_config` dict, XDG-aware
  `~/.config/linuxtask/config.json`, `_load_app_config`/`_save_app_config`
  (`src/main.py:413-441`). Update state goes there, not in a new file.
- **The app makes no network calls today.** `tools/run.sh` used to pip-install
  from the network on the launch path and that was removed as a security fix.
  This feature is the first egress, so it is disclosed, throttled, silent on
  failure, and switchable off.
- **Python floor is 3.10** and no new dependency may be added. `urllib`,
  `hashlib`, `json`, `os`, `dataclasses` are all stdlib. `packaging` happens to
  be present in the bundle as a transitive dep but is not declared, so it is
  not used.
- **Version comparison convention** is the numeric triple already used by
  `tools/release.py:58` (`list(map(int, v.split('.')))`). No prerelease
  suffixes exist in this project's tags.

## Behaviour agreed with the user

Automatic check on launch, at most once per 24 h, on a worker thread.
Any failure — offline, rate limit, HTTP error, malformed JSON, missing asset —
is silent: `logger.debug` and nothing on screen. The notice is never a dialog.
A `Check automatically` checkbox in Settings turns it off, and the README
documents that the app now contacts `api.github.com`.

## Architecture

Three approaches were considered:

1. **Pure `src/updater.py` + thin GUI wiring** (chosen). All logic is
   importable and testable without Tk, without a display and without network.
   `main.py` only starts a thread and reacts to queue tokens.
2. Methods on `LinuxTaskApp`. Rejected: `main.py` is already a 635-line class
   that tests must build via `__new__`; adding network and file-replacement
   logic there makes it untestable headlessly.
3. AppImageUpdate / zsync delta updates. Rejected: requires update metadata
   embedded at build time and an external binary. `python-appimage` does not
   emit that metadata, so this is a build-system project, not a feature.

### `src/updater.py`

No Tk, no threads, no config access. Every function is pure except the two
that do I/O, and both take their inputs as arguments.

```
RELEASE_API = "https://api.github.com/repos/JADRT22/LinuxTask/releases/latest"
ASSET_NAME  = "LinuxTask-x86_64.AppImage"
CHECK_INTERVAL_SECONDS = 24 * 3600
HTTP_TIMEOUT = 10

class UpdateError(Exception): ...

@dataclass(frozen=True)
class UpdateInfo:
    version: str          # "3.5.4", no leading v
    asset_url: str        # https only
    asset_size: int
    sha256: str           # 64 lowercase hex, from the API digest
    html_url: str         # the release page, for the manual fallback
```

- `version_tuple(text) -> tuple[int, ...] | None` — strip a leading `v`,
  split on `.`, every part must be all digits, otherwise `None`.
- `is_newer(remote, local) -> bool` — `False` if either side fails to parse.
  Garbage never produces a nag.
- `parse_release(payload) -> UpdateInfo | None` — requires a dict, a string
  `tag_name`, and an asset named `ASSET_NAME` whose `browser_download_url`
  starts with `https://`, whose `size` is a positive int, and whose `digest`
  is `sha256:<64 lowercase hex>`. Any one of those missing or malformed
  yields `None` for the whole release (see "Fail closed" below).
- `fetch_latest(timeout=HTTP_TIMEOUT) -> UpdateInfo | None` — one GET with
  `User-Agent: LinuxTask/<APP_VERSION> (+https://github.com/JADRT22/LinuxTask)`
  and `Accept: application/vnd.github+json`. Catches `OSError`, `ValueError`
  and `http.client.HTTPException`, logs at debug, returns `None`. No
  exception escapes this function. No token, no auth, no redirect to a
  non-https URL.
- `appimage_path() -> str | None` — `os.environ["APPIMAGE"]`, accepted only
  if it is an absolute path to an existing regular file. Anything else →
  `None`, which disables the whole feature.
- `download(info, target_path, progress=None) -> None` — streams the asset to
  `target_path + ".part"` **in the same directory**, hashing as it goes.
  Verifies sha256 and size, `os.chmod(part, 0o755)`, then `os.replace(part,
  target_path)`. On any failure the `.part` is removed and `UpdateError` is
  raised; the target is never opened for writing. `progress(done, total)` is
  called from the caller's thread with a monotonically increasing `done`.

**Fail closed on a missing digest.** If the API does not supply a usable
`sha256`, `parse_release` returns `None` and no install is offered. GitHub
provides the field today (verified above); if that ever changes the feature
degrades to "no update known" rather than installing unverified bytes. The
manual path — the release page link — stays available.

### Trust model

HTTPS to `api.github.com` and to the asset URL, plus the sha256 that GitHub
publishes for the asset. There is no signature and no pinned key: a
compromised GitHub release would be trusted. That is the same trust boundary
as `curl … | chmod +x` from the README, and it is stated plainly in
`SECURITY.md` rather than implied to be stronger than it is. The digest
protects against a truncated or corrupted transfer, not against a malicious
release.

### GUI wiring in `src/main.py`

Startup, via `self.after(200, self._start_update_check)`:

1. `updater.appimage_path()` is `None` → return, nothing else happens.
2. `app_config.get("update_check_enabled") is False` → return.
3. `time.time() - app_config.get("update_last_check", 0) < CHECK_INTERVAL_SECONDS`
   → return.
4. Otherwise start a daemon thread running `_update_check_worker`.

`_update_check_worker` calls `fetch_latest()`, stores the result on the plain
attribute `self._update_info`, and puts `"update_checked"`. It does not write
config and does not touch a widget.

`_poll_hotkeys` gains four tokens, all handled on the UI thread:

| Token | Plain attribute read | UI effect |
|---|---|---|
| `update_checked` | `_update_info` | Persist `update_last_check`. If newer than `APP_VERSION`, set `_update_available`, recolour `btn_settings` to `#1976d2` (the blue already used for loop-enabled) and set its tooltip to `Update available: vX.Y.Z` |
| `update_progress` | `_update_progress = (done, total)` | Set the Settings progress bar |
| `update_installed` | `_update_info` | Label: `Restart LinuxTask to use vX.Y.Z`. Disable the download button |
| `update_failed` | `_update_error` | Label shows the message; re-enable the button |

Detail rides on plain attributes rather than tuple queue items, so the
existing string dispatch in `_poll_hotkeys` is not restructured. This is the
same shape as `manager.driver_warning_detail`.

The Settings window (`open_settings`, `src/main.py:356`) grows from 300×250
to 300×400 and gains an **Updates** section: current version, a status label,
`Check now`, `Download and install`, a progress bar, and the
`Check automatically` checkbox. `Check now` bypasses the 24 h throttle and
reports failure in the status label — a manual action deserves an answer,
unlike the silent automatic path.

Before downloading, `os.access(os.path.dirname(target), os.W_OK)` is checked.
If the directory is not writable the button reads `Save to…` and uses
`filedialog.asksaveasfilename`; `download` then writes to that chosen path
instead, verified the same way. The running AppImage is left alone — the user
gets a new file and a label naming where it is.

**One operation at a time.** `_update_check_running` guards the check so a
`Check now` click during an in-flight automatic check is a no-op rather than a
second thread. The download button is disabled from the moment it is clicked
until `update_installed` or `update_failed` arrives, so two downloads cannot
overlap. Both flags are written and read on the UI thread only.

**No auto-relaunch and no self-exec.** After a successful replace the app
keeps running on the old inode and asks the user to restart. Killing the
session mid-macro is worse than one click.

### Config keys

Added to the existing `config.json`, no new file:

- `update_check_enabled` — bool, absent means `True`.
- `update_last_check` — float epoch seconds, written only on the UI thread.

No "skip this version" key: the badge is non-intrusive enough that a skip
mechanism is not needed.

## Error handling

| Condition | Automatic path | Manual path |
|---|---|---|
| Not an AppImage | Feature absent entirely | Feature absent entirely |
| Offline, DNS failure, timeout | `logger.debug`, no UI change | Status label: could not reach GitHub |
| HTTP 403 rate limit / 404 / 5xx | `logger.debug`, no UI change | Status label names the failure |
| Malformed JSON, missing asset, no digest | `logger.debug`, no UI change | Status label: no usable release |
| Remote version ≤ local | Nothing | Status label: already up to date |
| sha256 or size mismatch | n/a (download is manual) | `UpdateError`, `.part` removed, target untouched, label shows it |
| Target directory not writable | n/a | Button becomes `Save to…`, no replace |
| Disk full mid-download | n/a | `UpdateError`, `.part` removed |

## Testing

`tests/test_updater.py`, no display, no network, no hardware:

- `version_tuple` / `is_newer`: triples, leading `v`, equal, older, newer,
  and malformed (`""`, `"v3.x"`, `None`) → `False`.
- `parse_release`: a fixture captured from the live `v3.5.3` API response;
  missing asset → `None`; non-https URL → `None`; absent or malformed digest
  → `None`; correct digest and size parsed.
- `fetch_latest`: `urlopen` patched to return `BytesIO`; assert the request
  URL, `User-Agent` and `Accept`. `HTTPError`, `URLError`, bad JSON and a
  non-dict payload each → `None` with no exception escaping.
- `download`: real temp directory and real bytes, `urlopen` patched to stream
  chunks. Matching digest → target replaced, mode `0755`, no `.part` left.
  **Mismatching digest → `UpdateError`, target byte-identical and mtime
  unchanged, no `.part` left.** Size mismatch → same. Progress callback
  receives increasing counts ending at the total.
- `appimage_path`: unset, relative, nonexistent, and a real file, via
  `patch.dict(os.environ)`.

GUI tests follow the existing `__new__` pattern in `tests/test_main_flow.py`:

- `_poll_hotkeys` with `update_checked` recolours `btn_settings` only when the
  stored version is newer.
- `_start_update_check` returns without starting a thread when not an
  AppImage, when disabled, when inside the 24 h window, and when
  `_update_check_running` is already set.
- The worker touches no Tk: the test replaces the widget methods with ones
  that raise, runs the worker, and asserts only the plain attribute and the
  queue token changed.

Every test patches `urlopen`; the suite must not gain a real network call.
The existing CI matrix (3.10–3.14 plus the distro-bindings job) runs these
without a new job.

## Documentation

- README: an **Updates** section stating what is contacted
  (`api.github.com`, once per 24 h), that no account or personal data is
  sent, how to turn it off, and that only the AppImage has the feature.
- SECURITY.md: the trust model above, including that a compromised release
  would be trusted and the digest is an integrity check, not a signature.
- CHANGELOG `[Unreleased]`: the feature in user terms.

## Out of scope

Delta updates; non-AppImage installs; automatic relaunch; a "skip this
version" control; prerelease channels; signature verification with a pinned
key; any change to the AppImage build.