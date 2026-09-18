#!/usr/bin/env bash
# Instalador dos EXPERIMENTOS visuais (image_click + color_spin).
#
# Totalmente independente do LinuxTask: não modifica src/ principal,
# requisitos.txt, udev rules, grupos nem nada da instalação do app.
# Quem instalar só o LinuxTask (tools/install.sh) NÃO recebe nada disto.
#
# O que faz (apenas o que os scripts precisam):
#   1. Dependências Python extras (numpy, Pillow) no venv do projeto
#      ou no usuário — o app em si NÃO usa estas dependências.
#   2. grim + slurp (Hyprland/wlroots), via pacman/dnf/apt.
#   3. Wrapper + .desktop para o assistente Color Spin no menu/desktop.
#
# Uso:  ./experimental/install.sh        (a partir da raiz do repo)
#       bash experimental/install.sh --remove   (desinstala os atalhos)

set -euo pipefail

HERE="$(cd "$(dirname "$(readlink -f "$0")")" && pwd)"
REPO_ROOT="$(dirname "$HERE")"
TEMPLATE="$HERE/color_spin/color-spin.desktop.template"
TEMPLATE_STOP="$HERE/color_spin/color-spin-stop.desktop.template"
STOP_SH="$HERE/color_spin/stop.sh"
LOCAL_APPS="${XDG_DATA_HOME:-$HOME/.local/share}/applications"

REAL_USER="${SUDO_USER:-${LOGNAME:-$USER}}"

# --- 0. Desinstalação ----------------------------------------------------
if [ "${1:-}" = "--remove" ]; then
    rm -f "$LOCAL_APPS/color-spin.desktop" "$LOCAL_APPS/color-spin-stop.desktop"
    DESKTOP_DIR="$(xdg-user-dir DESKTOP 2>/dev/null || true)"
    if [ -n "$DESKTOP_DIR" ]; then
        rm -f "$DESKTOP_DIR/color-spin.desktop" \
              "$DESKTOP_DIR/color-spin-stop.desktop"
    fi
    update-desktop-database "$LOCAL_APPS" 2>/dev/null || true
    echo "✅ Atalhos do Color Spin removidos (scripts e configs mantidos)."
    exit 0
fi

echo "🧪 Instalador dos experimentos visuais (image_click + color_spin)"
echo "   Repo: $REPO_ROOT"
echo "   (independente do LinuxTask — nada do app é modificado)"
echo

# --- 1. Dependências Python (numpy + Pillow) ------------------------------
PY="$REPO_ROOT/venv/bin/python3"
if [ -x "$PY" ]; then
    echo "[1/3] Instalando numpy + Pillow no venv do projeto..."
    "$REPO_ROOT/venv/bin/pip" install --quiet numpy Pillow || {
        echo "[WARN] pip do venv falhou; tentando --user..."
        python3 -m pip install --user --quiet numpy Pillow || \
            echo "[ERRO] Instale manualmente: pip3 install --user numpy Pillow"
    }
else
    echo "[1/3] Sem venv; instalando numpy + Pillow com --user..."
    python3 -m pip install --user --quiet numpy Pillow || \
        echo "[ERRO] Instale manualmente: pip3 install --user numpy Pillow"
fi

# --- 2. grim + slurp (Hyprland/wlroots) ------------------------------------
if ! command -v grim >/dev/null 2>&1 || ! command -v slurp >/dev/null 2>&1; then
    echo "[2/3] Instalando grim + slurp..."
    if command -v pacman >/dev/null 2>&1; then
        sudo pacman -S --noconfirm --needed grim slurp
    elif command -v dnf >/dev/null 2>&1; then
        sudo dnf install -y grim slurp
    elif command -v apt >/dev/null 2>&1; then
        sudo apt install -y grim slurp
    else
        echo "[WARN] Gerenciador de pacotes não identificado."
        echo "       Instale manualmente: grim e slurp"
    fi
else
    echo "[2/3] grim + slurp já presentes. ✔"
fi

# --- 3. Atalho do assistente (menu + desktop) ------------------------------
echo "[3/3] Criando atalho do assistente Color Spin..."
# Preenche o template com os caminhos deste usuário (o .desktop do repo
# não pode ter caminho fixo — cada instalação fica em um lugar).
DESKTOP_FILE="$LOCAL_APPS/color-spin.desktop"
mkdir -p "$LOCAL_APPS"
sed -e "s|@LAUNCHER@|$HERE/color_spin/launcher.sh|g" \
    -e "s|@ICON@|$REPO_ROOT/assets/icon.png|g" \
    -e "s|@CWD@|$HERE/color_spin|g" \
    "$TEMPLATE" > "$DESKTOP_FILE"
chmod +x "$STOP_SH"
DESKTOP_FILE_STOP="$LOCAL_APPS/color-spin-stop.desktop"
sed -e "s|@STOP@|$STOP_SH|g" \
    -e "s|@ICON@|$REPO_ROOT/assets/icon.png|g" \
    -e "s|@CWD@|$HERE/color_spin|g" \
    "$TEMPLATE_STOP" > "$DESKTOP_FILE_STOP"
DESKTOP_DIR="$(xdg-user-dir DESKTOP 2>/dev/null || true)"
if [ -n "$DESKTOP_DIR" ]; then
    cp "$DESKTOP_FILE" "$DESKTOP_DIR/"
    cp "$DESKTOP_FILE_STOP" "$DESKTOP_DIR/"
    chmod +x "$DESKTOP_DIR/color-spin.desktop" \
              "$DESKTOP_DIR/color-spin-stop.desktop"
    gio set "$DESKTOP_DIR/color-spin.desktop" metadata::trusted true \
        2>/dev/null || true
    gio set "$DESKTOP_DIR/color-spin-stop.desktop" metadata::trusted true \
        2>/dev/null || true
fi
chmod +x "$HERE/color_spin/launcher.sh"
update-desktop-database "$LOCAL_APPS" 2>/dev/null || true

echo
echo "✅ Experimentos instalados. Nota: estes scripts leem /dev/input e"
echo "   capturam a tela — no Hyprland basta estar no grupo 'input'"
echo "   (a instalação do LinuxTask já configura isso; se nunca rodou"
echo "   ./tools/install.sh, faça antes e relogue)."
echo
echo "   Uso:"
echo "     - Duplo clique em 'Color Spin (auto-girar)' no desktop/menu"
echo "     - Parar o loop: atalho 'Color Spin (parar)' (ou: pkill -f assistente.py)"
echo "     - Ou no terminal: python3 $HERE/color_spin/assistente.py"
echo
echo "   Remover os atalhos: bash $0 --remove"
