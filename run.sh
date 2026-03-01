#!/bin/bash
# Script de Execução e Autoconfiguração do LinuxTask

# Resolve o diretório real do script (mesmo se for um symlink)
APP_DIR="$(cd "$(dirname "$(readlink -f "$0")")" && pwd)"
export APP_DIR
export YDOTOOL_SOCKET="/tmp/.ydotool_socket"
cd "$APP_DIR" || exit

# 1. Verificação de permissões (Hardware Access)
# Verifica se consegue ler os eventos e escrever no uinput
CAN_READ_EVENTS=$( [ -r /dev/input/event0 ] && echo "yes" || echo "no" )
CAN_WRITE_UINPUT=$( [ -w /dev/uinput ] && echo "yes" || echo "no" )

if [ "$CAN_READ_EVENTS" != "yes" ] || [ "$CAN_WRITE_UINPUT" != "yes" ]; then
    # Se o sistema tiver zenity, avisa graficamente
    if command -v zenity >/dev/null; then
        zenity --info --title="Configuração do Sistema" --text="O LinuxTask precisa de permissões de hardware.\n\nPor favor, insira sua senha para configurar o acesso imediato." --width=350
    fi
    
    # Executa o instalador via interface gráfica de privilégios (pkexec)
    # Usamos o caminho absoluto sem aspas internas para o pkexec
    pkexec "$APP_DIR/install.sh"
    
    # Aguarda um pouco para o sistema processar as novas regras
    sleep 1
fi

# 2. Execução normal do app
if [ -d "$APP_DIR/venv" ]; then
    source "$APP_DIR/venv/bin/activate"
    python main.py
else
    python3 main.py
fi
