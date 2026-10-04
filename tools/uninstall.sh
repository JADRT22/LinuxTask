#!/usr/bin/env bash
# LinuxTask uninstallation script — mirror of tools/install.sh
# Usage: ./tools/uninstall.sh [--yes] [--purge]

set -euo pipefail

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$APP_DIR")"
# Real (non-root) user, even when invoked via pkexec/sudo.
REAL_USER="${SUDO_USER:-}"
if [ -z "$REAL_USER" ] && [ -n "${PKEXEC_UID:-}" ]; then
    REAL_USER="$(id -nu "$PKEXEC_UID" 2>/dev/null || true)"
fi
REAL_USER="${REAL_USER:-${LOGNAME:-$USER}}"
[ -n "$REAL_USER" ] || { echo "[ERROR] Could not determine the real user." >&2; exit 1; }
USER_HOME=$(eval echo "~$REAL_USER")
DESKTOP_DIR="$USER_HOME/.local/share/applications"
DESKTOP_FILE="$DESKTOP_DIR/linuxtask.desktop"
UDEV_RULE_PATH="/etc/udev/rules.d/99-linuxtask.rules"
VENV_PIP="$REPO_ROOT/.venv/bin/pip"

ASSUME_YES=0
PURGE=0
for arg in "$@"; do
    case "$arg" in
        --yes|-y) ASSUME_YES=1 ;;
        --purge)  PURGE=1 ;;
        *)
            echo "[ERROR] Unknown option: $arg (supported: --yes, --purge)" >&2
            exit 1
            ;;
    esac
done

fail() {
    echo "[ERROR] $1" >&2
    echo "[ERROR] Uninstall FAILED." >&2
    exit 1
}

# Run a command as root. Returns the command's status (0 = ok), so an
# already-removed artifact stays a warning instead of a hard failure.
run_root() {
    if [ "$(id -u)" -eq 0 ]; then
        "$@"
    elif command -v sudo >/dev/null 2>&1; then
        sudo "$@"
    else
        echo "[ERROR] Root privileges are required and sudo was not found." >&2
        return 1
    fi
}

echo "Starting LinuxTask uninstallation..."

# 1. Remove the udev rule and reload (permanent part of the permissions fix).
if [ -e "$UDEV_RULE_PATH" ]; then
    echo "[INFO] Removing udev rule $UDEV_RULE_PATH..."
    run_root rm -f "$UDEV_RULE_PATH" \
        || fail "Could not remove $UDEV_RULE_PATH (root required). Re-run as: sudo ./tools/uninstall.sh"
    echo "[INFO] Reloading udev rules..."
    run_root udevadm control --reload-rules || fail "udev reload failed."
    run_root udevadm trigger || fail "udev trigger failed."
else
    echo "[WARN] udev rule $UDEV_RULE_PATH not found; skipping (already removed)."
fi

# 2. Remove the desktop entry.
if [ -e "$DESKTOP_FILE" ]; then
    echo "[INFO] Removing desktop entry $DESKTOP_FILE..."
    rm -f "$DESKTOP_FILE" 2>/dev/null || run_root rm -f "$DESKTOP_FILE" \
        || fail "Could not remove $DESKTOP_FILE."
    if command -v update-desktop-database >/dev/null 2>&1; then
        update-desktop-database "$DESKTOP_DIR" 2>/dev/null || true
    fi
else
    echo "[WARN] Desktop entry $DESKTOP_FILE not found; skipping (already removed)."
fi

# 3. Drop the user from the 'input' group (asks first; --yes skips).
if id -nG "$REAL_USER" 2>/dev/null | tr ' ' '\n' | grep -qx input; then
    REMOVE_GROUP="no"
    if [ "$ASSUME_YES" -eq 1 ]; then
        REMOVE_GROUP="yes"
    else
        printf "Remove %s from the 'input' group? [y/N] " "$REAL_USER"
        read -r ANSWER || ANSWER=""
        case "$ANSWER" in y|Y|yes|YES) REMOVE_GROUP="yes" ;; esac
    fi
    if [ "$REMOVE_GROUP" = "yes" ]; then
        run_root gpasswd -d "$REAL_USER" input \
            && echo "[INFO] Removed $REAL_USER from the 'input' group (log out and back in to apply)." \
            || echo "[WARN] Could not remove $REAL_USER from 'input'; run: sudo gpasswd -d $REAL_USER input"
    else
        echo "[INFO] Keeping $REAL_USER in the 'input' group."
    fi
else
    echo "[WARN] $REAL_USER is not in the 'input' group; skipping (already removed)."
fi

# 4. pip packages: remove only what nothing else can depend on. Packages
# inside the project venv are private to this repo; anything installed
# elsewhere (distro/global) is shared, so it is only warned about unless
# --purge forces it.
echo "[INFO] Checking Python packages..."
PIP_PKGS=(customtkinter evdev python-xlib)
SAFE_PKGS=()
SHARED_PKGS=()
if [ -x "$VENV_PIP" ]; then
    for pkg in "${PIP_PKGS[@]}"; do
        LOC=$("$VENV_PIP" show "$pkg" 2>/dev/null | awk '/^Location:/{print $2}') || LOC=""
        [ -n "$LOC" ] || continue
        case "$LOC" in
            "$REPO_ROOT"/.venv/*) SAFE_PKGS+=("$pkg") ;;
            *)                    SHARED_PKGS+=("$pkg") ;;
        esac
    done
else
    echo "[WARN] No project venv pip at $VENV_PIP; only system packages can be checked."
    SHARED_PKGS=("${PIP_PKGS[@]}")
fi

if [ "${#SAFE_PKGS[@]}" -gt 0 ]; then
    echo "[INFO] Uninstalling project venv packages: ${SAFE_PKGS[*]}"
    "$VENV_PIP" uninstall -y "${SAFE_PKGS[@]}" \
        || echo "[WARN] Could not uninstall some venv packages; delete the venv instead: rm -rf '$REPO_ROOT/.venv'"
fi

if [ "${#SHARED_PKGS[@]}" -gt 0 ]; then
    if [ "$PURGE" -eq 1 ]; then
        echo "[WARN] --purge: force-uninstalling shared packages: ${SHARED_PKGS[*]}"
        if command -v pip3 >/dev/null 2>&1; then
            pip3 uninstall -y "${SHARED_PKGS[@]}" \
                || echo "[WARN] Some shared packages could not be removed (distro-managed?); use your package manager."
        else
            echo "[WARN] pip3 not found; remove them with your package manager."
        fi
    else
        echo "[WARN] Shared packages left installed: ${SHARED_PKGS[*]}"
        echo "[WARN] Other software may depend on them. Force removal with: ./tools/uninstall.sh --purge"
    fi
fi

# 5. Temporary ACLs on the input devices (best-effort: they vanish on reboot).
if command -v setfacl >/dev/null 2>&1; then
    echo "[INFO] Clearing temporary ACLs on input devices..."
    for dev in /dev/uinput /dev/input/event*; do
        [ -e "$dev" ] || continue
        run_root setfacl -x "u:$REAL_USER" "$dev" 2>/dev/null \
            || echo "[WARN] Could not clear ACL on $dev (root required; it disappears on reboot)."
    done
else
    echo "[WARN] setfacl not found; skipping ACL cleanup."
fi

echo "Uninstall complete!"
echo "[INFO] NOT removed on purpose:"
echo "[INFO]   - Project venv: $REPO_ROOT/.venv"
echo "[INFO]     delete it with: rm -rf '$REPO_ROOT/.venv'"
echo "[INFO]   - Distro packages the installer pulled in (xdotool, python3-dbus/python-dbus,"
echo "[INFO]     python3-gi/python-gobject, acl, Tk, evdev, python-xlib): remove with your"
echo "[INFO]     package manager, e.g.: sudo pacman -Rns xdotool"
echo "[INFO]   - Project files under $REPO_ROOT"
echo "[NOTE] ACLs on /dev/uinput and /dev/input/event* disappear on reboot;"
echo "[NOTE] removing the udev rule is what makes the permission change permanent."
