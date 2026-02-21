#!/bin/bash
# Script para rodar o LinuxTask
# Ativa o ambiente virtual e executa o programa
export APP_DIR="$HOME/Projetos/LinuxTask"
cd "$APP_DIR" || exit
source venv/bin/activate
python main.py
