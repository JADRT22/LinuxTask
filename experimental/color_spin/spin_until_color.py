# -*- coding: utf-8 -*-
"""
LinuxTask (experimental) - spin_until_color.py
Description: Loop de clique até uma cor aparecer numa região da tela.
Author: Buffy (Codebuff) para JADRT22
License: MIT

Caso de uso: girar "clans" em jogos do Roblox — clica no botão de girar
repetidamente e PARA quando a cor rara do resultado aparece.

    # 1. capture o botão de girar e a região onde o resultado aparece:
    python3 ../image_click/grab_template.py botao_girar.png
    python3 grab_region.py regiao_resultado.png

    # 2. ache as coordenadas do botão e a cor alvo:
    python3 ../image_click/find.py --template botao_girar.png
    python3 pick_color.py regiao_resultado.png

    # 3. rode o loop:
    python3 spin_until_color.py \
        --button-x 1650 --button-y 606 \
        --region 1559,447 258x253 \
        --color 255,215,0 --tolerance 40 \
        --interval 1.2

Fluxo: clica no botão → espera → checa se a cor apareceu na região
→ se sim, para (e clica em 'ok' se configurado); se não, clica de novo.
"""

import argparse
import logging
import os
import sys
import time

import numpy as np

# Roda de qualquer CWD: resolve src/ (drivers), capture/vision (pasta
# experimental) e o PoC irmão image_click/ (UInputClicker) pelo local
# deste arquivo.
_HERE = os.path.abspath(os.path.dirname(__file__))
for p in (os.path.join(_HERE, "..", "..", "src"),
          os.path.join(_HERE, ".."),  # capture/vision (experimental/)
          os.path.join(_HERE, "..", "image_click")):
    p = os.path.abspath(p)
    if p not in sys.path:
        sys.path.insert(0, p)

logger = logging.getLogger("LinuxTask.experimental.spin")


def color_fraction(img, target_rgb, tolerance):
    """Fração de pixels da imagem dentro da tolerância do RGB alvo.

    Tolerância é a distância máxima por canal (métrica de Chebyshev) —
    intuitiva e fácil de ajustar: tolerance=40 pega qualquer cor
    "parecida".
    """
    target = np.array(target_rgb, dtype=np.int16)
    diff = np.abs(img.astype(np.int16) - target)
    mask = diff.max(axis=2) <= tolerance
    return float(mask.mean())


def wait_region_stable(backend, region, poll=0.15, diff=2.0, need=3,
                       max_wait=10.0):
    """Espera a ANIMAÇÃO da região acabar antes de checar a cor.

    Sem isso, roletas/gachas que "passam" por vários clans durante a
    animação geram falso-positivo: o clan raro aparece ~1s na tela mas
    não é o resultado. A solução é só checar a cor quando a imagem
    para de mudar.

    Compara capturas consecutivas da região; quando `need` comparações
    seguidas tiverem diferença média <= `diff` (0-255), considera
    estável. Retorna (estavel: bool, segundos_decorridos: float).
    """
    start = time.monotonic()
    deadline = start + max_wait
    prev = backend.capture_region(region).astype(np.int16)
    stable = 0
    while time.monotonic() < deadline:
        time.sleep(poll)
        cur = backend.capture_region(region).astype(np.int16)
        d = float(np.abs(cur - prev).mean())
        prev = cur
        if d <= diff:
            stable += 1
            if stable >= need:
                return True, time.monotonic() - start
        else:
            stable = 0
    return False, time.monotonic() - start


def main():
    p = argparse.ArgumentParser(
        description="Clica num botão em loop até uma cor aparecer."
    )
    p.add_argument("--button-x", type=int, required=True,
                   help="X do centro do botão de girar")
    p.add_argument("--button-y", type=int, required=True,
                   help="Y do centro do botão de girar")
    p.add_argument("--region", required=True, nargs=2,
                   metavar=("POS", "SIZE"),
                   help="região do resultado: 'x,y' 'WxH' (ex.: 1559,447 258x253)")
    p.add_argument("--color", required=True,
                   help="RGB alvo: '255,215,0'")
    p.add_argument("--tolerance", type=int, default=40,
                   help="tolerância por canal RGB (default 40)")
    p.add_argument("--threshold", type=float, default=0.02,
                   help="fração mínima de pixels da cor pra contar como "
                        "achado (default 0.02 = 2%% da região)")
    p.add_argument("--interval", type=float, default=1.5,
                   help="segundos entre cliques (default 1.5)")
    p.add_argument("--max-spins", type=int, default=100,
                   help="limite de giros por segurança (default 100)")
    p.add_argument("--settle", type=float, default=0.3,
                   help="espera inicial após o clique antes de começar a "
                        "detectar estabilização (default 0.3s)")
    p.add_argument("--poll", type=float, default=0.1,
                   help="intervalo entre capturas na detecção de "
                        "estabilização (default 0.1s)")
    p.add_argument("--stable-diff", type=float, default=2.5,
                   help="diferença média máxima (0-255) entre capturas "
                        "pra considerar parado (default 2.5; efeitos de "
                        "brilho podem pedir um valor maior)")
    p.add_argument("--stable-need", type=int, default=15,
                   help="quantas comparações seguidas paradas são "
                        "necessárias (default 15 = ~1.5s congelada — "
                        "desacelerada da roleta não passa por parada)")
    p.add_argument("--stable-max", type=float, default=20.0,
                   help="tempo máximo esperando a roleta parar "
                        "(default 20s)")
    p.add_argument("--confirm-times", type=int, default=2,
                   help="quantas vezes a cor precisa ser re-confirmada "
                        "após a detecção (default 2; mata falso-positivo "
                        "de clan que passa na roleta)")
    p.add_argument("--confirm-gap", type=float, default=1.0,
                   help="segundos entre a detecção e cada re-confirmação "
                        "(default 1.0s)")
    args = p.parse_args()

    import capture as cap
    from image_click import UInputClicker
    from drivers.hyprland import HyprlandDriver

    # Parse da região "x,y" "WxH"
    try:
        pos_s, size_s = args.region
        x_s, _, y_s = pos_s.partition(",")
        w_s, _, h_s = size_s.lower().partition("x")
        region = (int(x_s), int(y_s), int(w_s), int(h_s))
    except ValueError:
        logger.error("região inválida: %r (use: 'x,y' 'WxH')", args.region)
        return 1

    try:
        target = tuple(int(c) for c in args.color.split(","))
        assert len(target) == 3 and all(0 <= c <= 255 for c in target)
    except (ValueError, AssertionError):
        logger.error("cor inválida: %r (use: '255,215,0')", args.color)
        return 1

    backend = cap.GrimCapture()
    clicker = UInputClicker()
    driver = HyprlandDriver()
    rx, ry, rw, rh = region

    logger.info(
        "girando: clique em (%d,%d) a cada %.1fs; paro quando a cor "
        "RGB%s (tol %d) ocupar >= %.1f%% de %dx%d em (%d,%d). Máx: %d giros.",
        args.button_x, args.button_y, args.interval, target,
        args.tolerance, args.threshold * 100, rw, rh, rx, ry,
        args.max_spins,
    )

    for spin in range(1, args.max_spins + 1):
        # 1. Clica no botão de girar
        driver.move_cursor(args.button_x, args.button_y)
        time.sleep(0.05)
        clicker.click()
        logger.info("giro %d/%d: cliquei.", spin, args.max_spins)

        # 2. Espera a roleta PARAR (a animação passa por vários clans;
        #    checar durante a animação gera falso-positivo).
        if args.settle > 0:
            time.sleep(args.settle)  # ignora o início da animação
        stable, waited = wait_region_stable(
            backend, region,
            poll=args.poll, diff=args.stable_diff,
            need=args.stable_need, max_wait=args.stable_max,
        )
        if not stable:
            logger.warning(
                "giro %d: região não estabilizou em %.1fs; checando mesmo "
                "assim.", spin, waited,
            )
        else:
            logger.info("giro %d: roleta parou em %.1fs.", spin, waited)

        # 3. Agora sim: checa a cor no resultado final
        try:
            crop = backend.capture_region(region)
        except cap.CaptureError as exc:
            logger.error("captura falhou: %s", exc)
            return 1

        frac = color_fraction(crop, target, args.tolerance)
        logger.info("  cor alvo ocupa %.2f%% da região", frac * 100)

        if frac >= args.threshold:
            # Confirmação dupla: clan que só PASSOU na roleta some em
            # ~1s; o resultado real fica parado na tela. Só paro se a
            # cor continuar lá em todas as re-checagens.
            confirmed = True
            for k in range(1, args.confirm_times):
                time.sleep(args.confirm_gap)
                crop2 = backend.capture_region(region)
                frac2 = color_fraction(crop2, target, args.tolerance)
                logger.info("  confirmação %d/%d: %.2f%%", k,
                            args.confirm_times - 1, frac2 * 100)
                if frac2 < args.threshold:
                    confirmed = False
                    break
            if confirmed:
                logger.info(
                    "★ COR ACHADA E CONFIRMADA no giro %d! "
                    "(%.2f%%) Parando.",
                    spin, frac * 100,
                )
                return 0
            logger.info(
                "giro %d: falso-positivo (a cor sumiu — era a roleta "
                "passando). Continuando.", spin,
            )

        time.sleep(max(0.0, args.interval))

    logger.warning("atingiu o limite de %d giros sem a cor aparecer.",
                   args.max_spins)
    return 2


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO, format="[%(levelname)s] %(name)s: %(message)s"
    )
    sys.exit(main())
