#!/usr/bin/env bash

# fix_linuxtask_perms.sh
# Script to fix permissions for LinuxTask macro recorder.
# Compatible with: apt (Debian/Ubuntu/Mint), pacman (Arch), dnf (Fedora)
# Grants read/write access to /dev/input/event* and /dev/uinput for the current user.

set -euo pipefail

# Colors for output
GREEN='\033[0;32m'
RED='\033[0;31m'
NC='\033[0m' # No Color

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
            echo -e "${RED}Unknown package manager. Please install '$pkg' manually.${NC}"
            return 1
            ;;
    esac
}

echo -e "${GREEN}Starting LinuxTask permission fix...${NC}"

# 1. Check for setfacl (acl package)
if ! command -v setfacl &> /dev/null; then
    echo -e "${RED}setfacl not found. Attempting to install 'acl' package...${NC}"
    install_package acl || { echo -e "${RED}Failed to install 'acl' package. Please install it manually.${NC}"; exit 1; }
fi

# 2. Ensure the 'input' group exists
echo -e "${GREEN}Ensuring 'input' group exists...${NC}"
sudo groupadd -f input

# 3. Add current user to the 'input' group
echo -e "${GREEN}Adding user $USER to 'input' group...${NC}"
sudo gpasswd -a "$USER" input

# 4. Install udev rules
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RULES_FILE="$SCRIPT_DIR/99-linuxtask.rules"
TARGET_DIR="/etc/udev/rules.d/"

if [ -f "$RULES_FILE" ]; then
    echo -e "${GREEN}Installing udev rules to $TARGET_DIR...${NC}"
    sudo cp "$RULES_FILE" "$TARGET_DIR"
else
    echo -e "${RED}Error: $RULES_FILE not found in $SCRIPT_DIR.${NC}"
    exit 1
fi

# 5. Reload and trigger udev rules
echo -e "${GREEN}Reloading and triggering udev rules...${NC}"
sudo udevadm control --reload-rules
sudo udevadm trigger

# 6. Grant immediate read/write access via ACL
echo -e "${GREEN}Granting immediate read/write access via ACL to $USER...${NC}"

# For /dev/uinput
if [ -e /dev/uinput ]; then
    sudo setfacl -m "u:$USER:rw" /dev/uinput
    echo -e "${GREEN}ACL applied to /dev/uinput${NC}"
else
    echo -e "${RED}Warning: /dev/uinput not found.${NC}"
fi

# For all /dev/input/event* devices
if ls /dev/input/event* >/dev/null 2>&1; then
    for dev in /dev/input/event*; do
        [ -e "$dev" ] && sudo setfacl -m "u:$USER:rw" "$dev"
    done
    echo -e "${GREEN}ACL applied to /dev/input/event* devices${NC}"
else
    echo -e "${RED}Warning: No /dev/input/event* devices found.${NC}"
fi

echo -e "${GREEN}Permission fix completed successfully!${NC}"
echo -e "Note: You may need to restart LinuxTask for changes to take effect."
echo -e "While ACLs provide immediate access, the group change will fully apply after your next login."
