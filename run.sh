#!/bin/bash
# Script de Execução e Autoconfiguração do LinuxTask

export APP_DIR="/home/fernando/projetos git/LinuxTask"
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
    pkexec "/home/fernando/projetos git/LinuxTask/install.sh"
    
    # Aguarda um pouco para o sistema processar as novas regras
    sleep 1
fi

# 2. Execução normal do app
source venv/bin/activate
python main.py
