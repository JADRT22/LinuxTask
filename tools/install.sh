#!/usr/bin/env bash
# Script de Instalação do LinuxTask
# Compatible with: apt (Debian/Ubuntu/Mint), pacman (Arch), dnf (Fedora)

set -euo pipefail

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$APP_DIR")"
USER_HOME=$(eval echo "~$USER")
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

echo "🚀 Iniciando instalação do LinuxTask..."

# 0. Install Python dependencies
echo "[INFO] Installing Python dependencies..."
if [ -f "$REPO_ROOT/requirements.txt" ]; then
    pip3 install --user -r "$REPO_ROOT/requirements.txt" 2>/dev/null || \
    python3 -m pip install --user -r "$REPO_ROOT/requirements.txt" 2>/dev/null || {
        echo "[WARN] pip install from requirements.txt failed. Trying individually..."
        pip3 install --user customtkinter evdev 2>/dev/null || \
        python3 -m pip install --user customtkinter evdev 2>/dev/null || {
            echo "[ERROR] Could not install Python dependencies."
            echo "        Please install manually: pip3 install customtkinter evdev"
        }
    }
else
    pip3 install --user customtkinter evdev 2>/dev/null || \
    python3 -m pip install --user customtkinter evdev 2>/dev/null || {
        echo "[ERROR] Could not install Python dependencies."
        echo "        Please install manually: pip3 install customtkinter evdev"
    }
fi

# Also ensure xdotool is available (needed for X11 desktops like Cinnamon)
if ! command -v xdotool >/dev/null 2>&1; then
    echo "[INFO] Installing xdotool..."
    install_package xdotool || echo "[WARN] Could not install xdotool. Install manually: sudo apt install xdotool"
fi

# 1. Ensure 'input' group exists
sudo groupadd -f input

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
Comment=Minimalist Macro Recorder (Cinnamon Edition)
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

# 6. Add user to input group
sudo gpasswd -a "$USER" input

# 6. Reload udev rules
sudo udevadm control --reload-rules && sudo udevadm trigger

# 7. Grant IMMEDIATE access (avoids logout/login on first run)
echo "[INFO] Granting immediate hardware access..."

# Ensure setfacl is available
if ! command -v setfacl >/dev/null 2>&1; then
    echo "[WARN] setfacl not found. Installing 'acl' package..."
    install_package acl || echo "[WARN] Could not install acl automatically."
fi

if command -v setfacl >/dev/null 2>&1; then
    sudo setfacl -m "u:$USER:rw" /dev/uinput
    for dev in /dev/input/event*; do
        [ -e "$dev" ] && sudo setfacl -m "u:$USER:rw" "$dev"
    done
fi

echo "✅ Instalação concluída!"
echo "Agora você pode pesquisar 'LinuxTask' no seu menu de aplicativos."
echo "Nota: Pode ser necessário fazer logout e login novamente para as permissões de grupo surtirem efeito."
