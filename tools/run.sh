#!/usr/bin/env bash
# Script de Execução e Autoconfiguração do LinuxTask

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
        zenity --info --title="Configuração do Sistema" \
            --text="O LinuxTask precisa de permissões de hardware.\n\nPor favor, insira sua senha para configurar o acesso imediato." \
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
if [ -d "$REPO_ROOT/venv" ]; then
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

# Quick pip dependency check — install if missing
$PYTHON_BIN -c "import customtkinter, evdev, Xlib" 2>/dev/null || {
    echo "[INFO] Installing missing Python dependencies..."
    if [ -d "$REPO_ROOT/venv" ]; then
        "$REPO_ROOT/venv/bin/pip" install customtkinter evdev python-xlib
    else
        pip3 install --user customtkinter evdev python-xlib 2>/dev/null || \
        python3 -m pip install --user customtkinter evdev python-xlib 2>/dev/null || {
            echo "[ERROR] Failed to install dependencies. Run: pip3 install customtkinter evdev python-xlib"
            exit 1
        }
    fi
}

# 4. Run the application
if [ -d "$REPO_ROOT/venv" ]; then
    source "$REPO_ROOT/venv/bin/activate"
    python src/main.py
else
    python3 src/main.py
fi
