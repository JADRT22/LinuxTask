# -*- coding: utf-8 -*-
"""
LinuxTask (experimental) - click_test.py
Description: Teste isolado do clique via uinput — passo 1.
Author: Buffy (Codebuff) para JADRT22
License: MIT

Cria o dispositivo virtual uinput e injeta cliques. Não captura tela,
não move o cursor — testa SOMENTE a injeção de botão.

    python3 click_test.py --count 3           # 3 cliques onde o cursor está
    python3 click_test.py --count 3 --dry-run # só mostra o que faria
    python3 click_test.py --delay 0.5         # intervalo entre cliques
"""

import argparse
import logging
import sys
import time

logger = logging.getLogger("LinuxTask.experimental.click_test")


def main():
    p = argparse.ArgumentParser(
        description="Testa SOMENTE o clique via uinput (sem mover o cursor)."
    )
    p.add_argument("--count", type=int, default=1,
                   help="quantos cliques (default 1)")
    p.add_argument("--delay", type=float, default=0.3,
                   help="segundos entre cliques (default 0.3)")
    p.add_argument("--button", default="left",
                   choices=["left", "right", "middle"],
                   help="qual botão (default left)")
    p.add_argument("--dry-run", action="store_true",
                   help="não injeta nada; só valida o dispositivo")
    args = p.parse_args()

    from image_click import UInputClicker
    from evdev import ecodes as e

    buttons = {"left": e.BTN_LEFT, "right": e.BTN_RIGHT,
               "middle": e.BTN_MIDDLE}
    btn = buttons[args.button]

    logger.info("criando dispositivo uinput...")
    clicker = UInputClicker()
    logger.info("dispositivo criado OK.")

    if args.dry_run:
        logger.info("--dry-run: nenhuma injeção feita. Dispositivo OK.")
        clicker.close()
        return 0

    if args.count == 1:
        logger.info("1 clique do botão %s vai acontecer AGORA "
                    "(onde o cursor estiver).", args.button)
    else:
        logger.info("%d cliques do botão %s, a cada %.1fs, começando em 2s...",
                    args.count, args.button, args.delay)
        time.sleep(2)

    for i in range(args.count):
        clicker.click(btn)
        logger.info("clique %d/%d injetado.", i + 1, args.count)
        if i + 1 < args.count:
            time.sleep(args.delay)

    clicker.close()
    logger.info("pronto. O aplicativo sob o cursor recebeu os cliques?")
    return 0


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO, format="[%(levelname)s] %(name)s: %(message)s"
    )
    sys.exit(main())
