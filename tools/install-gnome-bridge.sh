#!/usr/bin/env bash
# LinuxTask - install-gnome-bridge.sh
# Description: installs the GNOME Shell cursor-bridge extension that gives
#              the GNOME Wayland driver real absolute cursor position and
#              absolute replay (seat.warp_pointer).
# Without it, the GNOME driver records/plays relative deltas and the
# cursor read falls back to xdotool/tkinter (stale over pure-Wayland apps).
# Author: JADRT22 (https://github.com/JADRT22)
# License: MIT
set -u

EXT_SRC="$(cd "$(dirname "$0")" && pwd)/../extensions/gnome-shell/linuxtask-cursorbridge@jadrt22"
EXT_ID="linuxtask-cursorbridge@jadrt22"
EXT_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/gnome-shell/extensions/$EXT_ID"

if [[ ! -d "$EXT_SRC" ]]; then
    echo "Cursor bridge extension not found at $EXT_SRC" >&2
    echo "Run from a checked-out LinuxTask repository." >&2
    exit 1
fi

if ! command -v gnome-shell >/dev/null 2>&1; then
    echo "gnome-shell not found — is this a GNOME session? Nothing to do." >&2
    exit 1
fi

echo "== Copying the extension =="
mkdir -p "$EXT_DIR"
cp -f "$EXT_SRC/extension.js" "$EXT_SRC/metadata.json" "$EXT_DIR/"
echo "Installed to: $EXT_DIR"

GNOME_VER="$(gnome-shell --version | grep -o '[0-9]*\.' | tr -d '.' | head -1)"
if [[ -n "$GNOME_VER" && "$GNOME_VER" -lt 45 ]]; then
    echo
    echo "WARNING: GNOME Shell $GNOME_VER detected. The extension uses"
    echo "ESM (GNOME 45+) syntax; on older shells it will not load."
fi

echo
if command -v gnome-extensions >/dev/null 2>&1; then
    echo "== Enabling the extension =="
    gnome-extensions enable "$EXT_ID" 2>/dev/null \
        || echo "(could not enable yet — enable it after the re-login below)"
else
    echo "== 'gnome-extensions' not found; enable it via Extensions app =="
fi

echo
echo "== IMPORTANT: one logout/login is needed the first time =="
echo "GNOME Shell picks up newly installed extension files only when the"
echo "shell restarts. Log out and back in (once — after that it stays"
echo "enabled and loads every session). Check with:"
echo
echo "  gdbus call --session --dest org.freedesktop.DBus \\"
echo "    --object-path /org/freedesktop/DBus \\"
echo "    --method org.freedesktop.DBus.NameHasOwner \\"
echo "    org.linuxtask.cursorbridge"
echo
echo "It must print '(true)'. Then LinuxTask's GNOME Wayland driver owns"
echo "real absolute positioning; without the bridge it keeps working in"
echo "relative-delta fallback mode."
