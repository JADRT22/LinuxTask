#!/usr/bin/env bash
# LinuxTask installation script
# Compatible with: apt (Debian/Ubuntu/Mint), pacman (Arch), dnf (Fedora)

set -euo pipefail

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$APP_DIR")"
# Real (non-root) user, even when invoked via pkexec/sudo from run.sh.
REAL_USER="${SUDO_USER:-}"
if [ -z "$REAL_USER" ] && [ -n "${PKEXEC_UID:-}" ]; then
    REAL_USER="$(id -nu "$PKEXEC_UID" 2>/dev/null || true)"
fi
REAL_USER="${REAL_USER:-${LOGNAME:-$USER}}"
[ -n "$REAL_USER" ] || { echo "[ERROR] Could not determine the real user." >&2; exit 1; }
USER_HOME=$(eval echo "~$REAL_USER")

fail() {
    echo "[ERROR] $1" >&2
    echo "[ERROR] Installation FAILED." >&2
    exit 1
}

# Run a command as the real (non-root) user, so files like .venv are
# never created root-owned when this script runs via sudo/pkexec.
as_user() {
    if [ "$(id -u)" -eq 0 ] && [ "$REAL_USER" != "root" ]; then
        sudo -u "$REAL_USER" "$@"
    else
        "$@"
    fi
}
DESKTOP_DIR="$USER_HOME/.local/share/applications"
UDEV_RULE_PATH="/etc/udev/rules.d/99-linuxtask.rules"

# --- Helper functions ---
detect_pkg_manager() {
    if command -v apt >/dev/null 2>&1; then
        echo "apt"
    elif command -v pacman >/dev/null 2>&1; then
        echo "pacman"
    elif command -v dnf >/dev/null 2>&1; then
        echo "dnf"
    else
        echo "unknown"
    fi
}

install_package() {
    local pkg="$1"
    local mgr
    mgr=$(detect_pkg_manager)

    case "$mgr" in
        apt)    sudo apt install -y "$pkg" ;;
        pacman) sudo pacman -S --noconfirm "$pkg" ;;
        dnf)    sudo dnf install -y "$pkg" ;;
        *)
            echo "[ERROR] Unknown package manager. Please install '$pkg' manually."
            return 1
            ;;
    esac
}

# dbus-python + PyGObject cannot be built from PyPI without system headers,
# so they MUST come from the distro. Only needed for KDE Wayland.
install_dbus_python_deps() {
    local mgr
    mgr=$(detect_pkg_manager)
    echo "[INFO] Installing system Python D-Bus bindings (needed on KDE Wayland)..."
    case "$mgr" in
        apt)    install_package python3-dbus && install_package python3-gi ;;
        pacman) install_package python-dbus && install_package python-gobject ;;
        dnf)    install_package python3-dbus && install_package python3-gobject ;;
        *)
            echo "[WARN] Unknown package manager: install python3-dbus and"
            echo "       python3-gi (or equivalent) manually if you use KDE Wayland."
            return 1
            ;;
    esac
}

echo "Starting LinuxTask installation..."

# 0. Install Python dependencies (fail-fast: no silent fallbacks).
# evdev + python-xlib come from the distro; customtkinter is NOT packaged
# on Arch/CachyOS and distro Pythons here are externally managed (PEP 668
# blocks `pip install --user`), so it goes into a project venv that still
# sees distro packages (dbus, gi, evdev) via --system-site-packages.
# Never --break-system-packages.
echo "[INFO] Installing system packages (evdev, python-xlib, Tk)..."
SYS_MGR=$(detect_pkg_manager)
case "$SYS_MGR" in
    apt)    install_package python3-evdev && install_package python3-xlib && install_package python3-tk ;;
    pacman) install_package python-evdev && install_package python-xlib && install_package tk ;;
    dnf)    install_package python3-evdev && install_package python3-xlib && install_package python3-tkinter ;;
    *)      fail "Unknown package manager. Install manually: evdev, python-xlib, Tk, xdotool." ;;
esac || fail "Could not install system Python packages."

if [ ! -x "$REPO_ROOT/.venv/bin/python" ]; then
    echo "[INFO] Creating project venv (.venv)..."
    as_user python3 -m venv --system-site-packages "$REPO_ROOT/.venv" \
        || fail "Could not create .venv (missing python3-venv / python-virtualenv?)."
    if [ "$(id -u)" -eq 0 ]; then
        chown -R "$REAL_USER" "$REPO_ROOT/.venv" || fail "Could not fix .venv ownership."
    fi
fi
as_user "$REPO_ROOT/.venv/bin/pip" install customtkinter \
    || fail "Could not install customtkinter into .venv."

# 0.1 Distro-provided D-Bus bindings for the KDE Wayland driver.
# Best-effort: not fatal on non-KDE desktops.
install_dbus_python_deps || true

# Also ensure xdotool is available (needed for X11 desktops like Cinnamon)
if ! command -v xdotool >/dev/null 2>&1; then
    echo "[INFO] Installing xdotool..."
    install_package xdotool || fail "Could not install xdotool."
fi

# 1. Ensure 'input' group exists
sudo groupadd -f input || fail "Could not create the 'input' group."

# 1b. Add the real user to the 'input' group. A fresh member MUST log
# out and back in (tracked in NEEDS_LOGOUT), even if the ACLs below
# already grant immediate access.
NEEDS_LOGOUT="no"
if id -nG "$REAL_USER" 2>/dev/null | tr ' ' '\n' | grep -qx input; then
    echo "[INFO] User $REAL_USER is already in the 'input' group."
else
    sudo gpasswd -a "$REAL_USER" input || fail "Could not add $REAL_USER to the 'input' group."
    NEEDS_LOGOUT="yes"
fi

# 1. Ensure execute permissions
chmod +x "$APP_DIR/run.sh"

# 2. Create .desktop directory if needed
mkdir -p "$DESKTOP_DIR"

# 3. Create .desktop entry
echo "[INFO] Creating desktop entry..."
ABS_ICON_PATH=$(realpath "$REPO_ROOT/assets/icon.png")
ABS_RUN_PATH=$(realpath "$APP_DIR/run.sh")

cat > "$DESKTOP_DIR/linuxtask.desktop" <<EOF
[Desktop Entry]
Name=LinuxTask
Comment=Minimalist Macro Recorder for Linux
Exec=$ABS_RUN_PATH
Icon=$ABS_ICON_PATH
Terminal=false
Type=Application
Categories=Utility;Automation;
StartupNotify=true
Path=$REPO_ROOT
EOF

# 4. Finalize shortcut
chmod +x "$DESKTOP_DIR/linuxtask.desktop"
if command -v update-desktop-database >/dev/null 2>&1; then
    update-desktop-database "$DESKTOP_DIR"
fi

# 5. Configure Udev Rules for permanent uinput and input permissions
echo "[INFO] Configuring permanent permissions (requires sudo)..."
sudo cp "$APP_DIR/99-linuxtask.rules" "$UDEV_RULE_PATH"

# 7. Reload udev rules. These MUST really apply: a silent failure here
# means recording captures zero events with no error message.
sudo udevadm control --reload-rules || fail "udev reload failed."
sudo udevadm trigger || fail "udev trigger failed (device rules not applied)."

# 7. Grant IMMEDIATE access (avoids logout/login on first run)
echo "[INFO] Granting immediate hardware access..."

# Ensure setfacl is available
if ! command -v setfacl >/dev/null 2>&1; then
    echo "[WARN] setfacl not found. Installing 'acl' package..."
    install_package acl || fail "Could not install 'acl' (needed for immediate access)."
fi

if command -v setfacl >/dev/null 2>&1; then
    # uinput needs write (virtual device for replay); event* devices are
    # read-only (recording only) to avoid granting input injection rights.
    sudo setfacl -m "u:$REAL_USER:rw" /dev/uinput || fail "Could not grant uinput access."
    for dev in /dev/input/event*; do
        [ -e "$dev" ] || continue
        sudo setfacl -m "u:$REAL_USER:r" "$dev" || fail "Could not grant read access on $dev."
    done
fi

# 8. Post-install smoke test, checked AS the real user (not root:
# root can read everything, which would hide permission problems).
echo "[INFO] Running post-install checks..."
"$REPO_ROOT/.venv/bin/python" -c "import evdev, customtkinter" 2>/dev/null \
    || fail "Python check failed: evdev/customtkinter not importable from .venv."
READABLE="no"
for dev in /dev/input/event*; do
    if sudo -u "$REAL_USER" test -r "$dev" 2>/dev/null; then
        READABLE="yes"
        break
    fi
done
if [ "$READABLE" != "yes" ]; then
    fail "No readable /dev/input/event* for $REAL_USER. Log out and back in, then re-run ./tools/install.sh."
fi
if [ "$NEEDS_LOGOUT" = "yes" ]; then
    echo "[NOTE] $REAL_USER was just added to the 'input' group."
    echo "[NOTE] ACLs already grant immediate access, but group-based access"
    echo "[NOTE] needs one logout/login. If hotkeys fail, log out and back in."
fi

echo "Installation complete!"
echo "You can now find 'LinuxTask' in your application menu."
echo "Note: You may need to log out and back in for group permissions to take effect."
