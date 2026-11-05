#!/usr/bin/env bash
# LinuxTask run and self-setup script

# Resolve the real directory of the script (even if symlinked)
APP_DIR="$(cd "$(dirname "$(readlink -f "$0")")" && pwd)"
REPO_ROOT="$(dirname "$APP_DIR")"
export APP_DIR
export REPO_ROOT
cd "$REPO_ROOT" || exit

# 1. Hardware permission check
# Check that we can read at least one input event device and write to uinput
CAN_READ_EVENTS="no"
for dev in /dev/input/event*; do
    if [ -r "$dev" ]; then
        CAN_READ_EVENTS="yes"
        break
    fi
done

CAN_WRITE_UINPUT="no"
[ -w /dev/uinput ] && CAN_WRITE_UINPUT="yes"

if [ "$CAN_READ_EVENTS" != "yes" ] || [ "$CAN_WRITE_UINPUT" != "yes" ]; then
    # Graphical notification if zenity is available
    if command -v zenity >/dev/null; then
        zenity --info --title="System Setup" \
            --text="LinuxTask needs hardware permissions.\n\nPlease enter your password to grant immediate access." \
            --width=350
    fi

    # Run installer via pkexec for privilege escalation
    pkexec "$APP_DIR/install.sh"

    # Wait for system to process new rules
    sleep 1
fi

# 2. Set YDOTOOL_SOCKET only if on Wayland with GNOME
SESSION_TYPE="${XDG_SESSION_TYPE:-}"
DESKTOP="${XDG_CURRENT_DESKTOP:-}"
if [ "$SESSION_TYPE" = "wayland" ] && echo "$DESKTOP" | grep -qi "gnome"; then
    export YDOTOOL_SOCKET="/run/user/$(id -u)/.ydotool_socket"
fi

PYTHON_BIN="python3"
if [ -x "$REPO_ROOT/.venv/bin/python" ]; then
    PYTHON_BIN="$REPO_ROOT/.venv/bin/python"
elif [ -d "$REPO_ROOT/venv" ]; then
    PYTHON_BIN="$REPO_ROOT/venv/bin/python3"
fi

# KDE Wayland: warn about distro-only Python D-Bus bindings.
# dbus-python/PyGObject are NOT pip-installable (need C headers) and are
# provided by install.sh via the package manager.
if [ "$SESSION_TYPE" = "wayland" ] && echo "$DESKTOP" | grep -qi "kde"; then
    if ! "$PYTHON_BIN" -c "import dbus, gi" 2>/dev/null; then
        echo "[WARN] KDE Wayland needs python3-dbus and python3-gi (distro packages)."
        echo "       Run ./tools/install.sh to install them, or manually:"
        echo "         apt install python3-dbus python3-gi"
        echo "         pacman -S python-dbus python-gobject"
        echo "         dnf install python3-dbus python3-gobject"
    fi
fi

# 3. Dependency check — this script never installs anything.
# An auto `pip install` here would fetch and execute code from the network
# every time the menu entry is clicked, bypass the requirements.txt pins
# that ./tools/install.sh installs into .venv, and trip PEP 668 on any
# current distro anyway. Deciding what gets installed is the setup
# script's job, so this only reports and points at it.
if ! $PYTHON_BIN -c "import customtkinter, evdev, Xlib" 2>/dev/null; then
    echo "[ERROR] LinuxTask's Python dependencies are missing for $PYTHON_BIN." >&2
    echo "        Run ./tools/install.sh once — it creates .venv with the" >&2
    echo "        pinned requirements.txt and sets up permissions." >&2
    if command -v zenity >/dev/null; then
        zenity --error --title="LinuxTask setup needed" \
            --text="LinuxTask cannot start: its Python dependencies are missing.\n\nRun ./tools/install.sh once, then start LinuxTask again." \
            --width=380 2>/dev/null
    fi
    exit 1
fi

# 4. Run the application (.desktop entry calls this script, so the
# menu shortcut follows the same interpreter choice). Arguments are
# forwarded: `./tools/run.sh play macro.json` uses the headless CLI.
exec "$PYTHON_BIN" src/main.py "$@"
