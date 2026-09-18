# -*- coding: utf-8 -*-
"""
LinuxTask (experimental) - grab_region.py
Description: Captura uma região da tela como referência visual.
Author: Buffy (Codebuff) para JADRT22
License: MIT

Mostra a região que você vai monitorar (a "área do resultado") — use junto
com pick_color.py para descobrir o RGB alvo dentro dela.

    python3 grab_region.py                    # salva em region.png
    python3 grab_region.py resultado.png
"""

import subprocess
import sys


def main():
    out = sys.argv[1] if len(sys.argv) > 1 else "region.png"
    try:
        geom = subprocess.check_output(["slurp"]).decode().strip()
    except subprocess.CalledProcessError:
        print("seleção cancelada (Esc). Nada salvo.")
        return 1
    except FileNotFoundError:
        print("slurp não encontrado. Instale com: pacman -S slurp")
        return 1

    subprocess.run(["grim", "-g", geom, out], check=True)
    print(f"região salva em {out} (geometria {geom})")
    print(f"agora ache a cor alvo com: python3 pick_color.py {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
