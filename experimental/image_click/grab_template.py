# -*- coding: utf-8 -*-
"""
LinuxTask (experimental) - grab_template.py
Description: Captura um recorte da tela como template (passo 0).
Author: Buffy (Codebuff) para JADRT22
License: MIT

Abre uma seleção de região com o mouse (slurp) e salva o recorte como
PNG, pronto para usar com find.py e image_click.py.

    python3 grab_template.py                 # salva em template.png
    python3 grab_template.py botao.png       # escolhe o nome
"""

import subprocess
import sys


def main():
    out = sys.argv[1] if len(sys.argv) > 1 else "template.png"

    try:
        # slurp imprime a geometria no formato que o grim espera:
        # "x,y WxH" (ex.: "100,200 120x40"). Esc cancela (exit != 0).
        geom = subprocess.check_output(["slurp"]).decode().strip()
    except subprocess.CalledProcessError:
        print("seleção cancelada (Esc). Nada salvo.")
        return 1
    except FileNotFoundError:
        print("slurp não encontrado. Instale com: pacman -S slurp")
        return 1

    try:
        subprocess.run(["grim", "-g", geom, out], check=True)
    except FileNotFoundError:
        print("grim não encontrado. Instale com: pacman -S grim")
        return 1

    print(f"template salvo em {out} (região {geom})")
    print(f"agora teste com: python3 find.py --template {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
