#!/bin/bash
# Root wrapper for LinuxTask uninstallation
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec "$SCRIPT_DIR/tools/uninstall.sh" "$@"
