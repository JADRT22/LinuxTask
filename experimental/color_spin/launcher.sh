#!/usr/bin/env bash
# Launcher do assistente Color Spin — abre sem terminal (via .desktop).
# Resolve os caminhos a partir do próprio arquivo, funciona de qualquer CWD.
set -euo pipefail

HERE="$(cd "$(dirname "$(readlink -f "$0")")" && pwd)"
REPO_ROOT="$(dirname "$(dirname "$HERE")")"

PY="$REPO_ROOT/venv/bin/python3"
[ -x "$PY" ] || PY="python3"

exec "$PY" "$HERE/app.py" "$@"
