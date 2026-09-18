# -*- coding: utf-8 -*-
"""
LinuxTask (experimental) - find.py
Description: Teste isolado da busca de imagem — passo 2.
Author: Buffy (Codebuff) para JADRT22
License: MIT

Captura a tela com grim, procura o template e só REPORTA a coordenada.
Não move o cursor e não clica.

    python3 find.py --template botao.png
    python3 find.py --template botao.png --confidence 0.9 --timeout 5
"""

import argparse
import logging
import sys
import time

import numpy as np
from PIL import Image

logger = logging.getLogger("LinuxTask.experimental.find")


def main():
    p = argparse.ArgumentParser(
        description="Acha o template na tela e só reporta a coordenada "
                    "(não move, não clica)."
    )
    p.add_argument("--template", required=True,
                   help="PNG de referência (recorte da UI alvo)")
    p.add_argument("--confidence", type=float, default=0.80,
                   help="confiança NCC mínima, 0-1 (default 0.80)")
    p.add_argument("--output", default=None,
                   help="monitor específico p/ grim (ex.: DP-1)")
    p.add_argument("--scale", type=float, default=None,
                   help="fator de escala p/ grim em telas HiDPI")
    p.add_argument("--timeout", type=float, default=10.0,
                   help="segundos tentando até desistir (default 10)")
    p.add_argument("--poll", type=float, default=0.25,
                   help="intervalo entre capturas (default 0.25 s)")
    args = p.parse_args()

    from image_click import grab_screen, find_image

    try:
        template = np.asarray(Image.open(args.template).convert("RGB"))
    except FileNotFoundError:
        logger.error(
            "template '%s' não existe. Capture um recorte da tela com: "
            "python3 grab_template.py %s",
            args.template, args.template,
        )
        return 1
    capture_kwargs = {}
    if args.output:
        capture_kwargs["output"] = args.output
    if args.scale:
        capture_kwargs["scale"] = args.scale

    logger.info("procurando %s (confiança %.2f)...",
                args.template, args.confidence)
    deadline = time.monotonic() + args.timeout
    attempts = 0
    while True:
        attempts += 1
        screen = grab_screen(**capture_kwargs)
        try:
            x, y, score = find_image(screen, template, args.confidence)
        except LookupError:
            if time.monotonic() >= deadline:
                logger.error("não achei em %.1fs (%d tentativas).",
                             args.timeout, attempts)
                return 1
            time.sleep(args.poll)
            continue

        print()
        print(f"ACHOU: x={x} y={y} score={score:.3f}")
        return 0


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO, format="[%(levelname)s] %(name)s: %(message)s"
    )
    sys.exit(main())
