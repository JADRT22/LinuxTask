#!/usr/bin/env bash
# Para o assistente Color Spin imediatamente (uso pelo atalho do desktop).
# O padrão não casa com este próprio script, então é seguro.
pkill -f "color_spin/assistente.py" 2>/dev/null
sleep 0.3
if pgrep -f "color_spin/assistente.py" >/dev/null 2>&1; then
    pkill -9 -f "color_spin/assistente.py" 2>/dev/null
fi
# Notificação de confirmação (silenciosa se notify-send não existir)
notify-send "Color Spin" "Loop interrompido." 2>/dev/null || true
