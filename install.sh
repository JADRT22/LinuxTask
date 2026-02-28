#!/bin/bash
# Script de Instalação do LinuxTask

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
USER_HOME=$(eval echo "~$USER")
DESKTOP_DIR="$USER_HOME/.local/share/applications"
UDEV_RULE_PATH="/etc/udev/rules.d/99-uinput.rules"

echo "🚀 Iniciando instalação do LinuxTask..."

# 1. Garante permissões de execução
chmod +x "$APP_DIR/run.sh"

# 2. Cria o arquivo .desktop
echo "Creating desktop entry..."
cat > "$DESKTOP_DIR/linuxtask.desktop" <<EOF
[Desktop Entry]
Name=LinuxTask
Comment=Macro Recorder Minimalista (Clone TinyTask)
Exec=$APP_DIR/run.sh
Icon=input-mouse
Terminal=false
Type=Application
Categories=Utility;Automation;
StartupNotify=true
Path=$APP_DIR
EOF

# 3. Configura Udev Rules para permissão permanente de uinput e input
# Isso evita ter que dar sudo chmod toda hora
echo "Configuring permanent permissions (requires sudo)..."
sudo cp "$APP_DIR/99-linuxtask.rules" "$UDEV_RULE_PATH"

# 4. Adiciona o usuário ao grupo input (se não estiver)
sudo gpasswd -a $USER input

# 5. Recarrega as regras do udev
sudo udevadm control --reload-rules && sudo udevadm trigger

echo "✅ Instalação concluída!"
echo "Agora você pode pesquisar 'LinuxTask' no seu menu de aplicativos."
echo "Nota: Pode ser necessário fazer logout e login novamente para as permissões de grupo surtirem efeito."
