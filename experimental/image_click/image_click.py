# -*- coding: utf-8 -*-
"""
LinuxTask (experimental) - image_click.py
Description: PoC de "achar imagem na tela e clicar nela" para Hyprland.
Author: Buffy (Codebuff) para JADRT22
License: MIT

Fluxo: grim captura a tela -> template matching NCC puro em numpy ->
HyprlandDriver.move_cursor() -> clique via uinput (evdev).

Não é referenciado por src/, tools/, CI ou AppImage (ver README do
diretório). Rodar direto na sessão Hyprland:

    python3 image_click.py --template botao.png           # achar + mover
    python3 image_click.py --template botao.png --click   # achar + clicar
    python3 image_click.py --template botao.png --selftest
"""

import argparse
import io
import logging
import os
import subprocess
import sys
import time

import numpy as np
from PIL import Image

# Permite rodar tanto como script solto quanto dentro do repositório
# (`python3 experimental/image_click/image_click.py`) reusando o driver real.
sys.path.insert(
    0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "src"))
)

logger = logging.getLogger("LinuxTask.experimental.image_click")


# --------------------------------------------------------------------------
# 1. Captura de tela (grim -> PNG em memória -> ndarray RGB)
# --------------------------------------------------------------------------

def grab_screen(**kwargs):
    """Captura a tela com `grim` e devolve um ndarray RGB (H, W, 3) uint8.

    Aceita os mesmos kwargs de grim (ex.: output="DP-1", scale=2). Levanta
    RuntimeError com a mensagem real do grim se a captura falhar.
    """
    # Destino "-" explícito: alguns builds do grim não escrevem no stdout
    # sem um argumento de saída (verificado no Arch). Opções antes do "-".
    cmd = ["grim"]
    for key, value in kwargs.items():
        cmd.append(f"--{key.replace('_', '-')}={value}")
    cmd.append("-")
    try:
        png = subprocess.run(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True
        ).stdout
    except FileNotFoundError:
        raise RuntimeError("grim não encontrado. Instale com: pacman -S grim")
    except subprocess.CalledProcessError as exc:
        raise RuntimeError(
            "grim falhou: %s" % exc.stderr.decode(errors="replace").strip()
        )
    return np.asarray(Image.open(io.BytesIO(png)).convert("RGB"))


# --------------------------------------------------------------------------
# 2. Template matching — NCC normalizado via FFT, puro numpy
# --------------------------------------------------------------------------

def _cross_correlate(image_f, template_f):
    """Correlação cruzada válida image×template via FFT (numpy.fft, sem scipy).

    Retorna array (h-th+1, w-tw+1) onde [iy, ix] é o somatório
    image[iy:iy+th, ix:ix+tw] * template — todas as janelas totalmente
    dentro da imagem. Equivale a sliding_window_view + dot, mas em
    O(N log N) e sem materializar as janelas (uma tela 4K com template
    pequeno estouraria memória do outro jeito).
    """
    h, w = image_f.shape
    th, tw = template_f.shape
    fh, fw = h - th + 1, w - tw + 1

    # FFT no tamanho da convolução linear completa (h+th-1, w+tw-1):
    # evita o wrap-around circular que contaminaria as janelas de borda.
    f_shape = (h + th - 1, w + tw - 1)
    f_image = np.fft.rfft2(image_f, s=f_shape)
    f_template = np.fft.rfft2(template_f[::-1, ::-1], s=f_shape)
    full = np.fft.irfft2(f_image * f_template, s=f_shape)

    # Deslocamento i da janela equivale a full[i + th - 1].
    return full[th - 1:th - 1 + fh, tw - 1:tw - 1 + fw]


def find_image(screen, template, min_confidence=0.80):
    """Acha `template` (H×W×3 uint8) dentro de `screen` (H×W×3 uint8).

    Retorna (cx, cy, score): centro do melhor match em coordenadas de tela
    (int) e a confiança NCC média por canal (float, -1..1). Levanta
    LookupError se o melhor score ficar abaixo de `min_confidence`.

    Pipeline por canal: média zero no template -> correlação via FFT ->
    normalização pela variância local de cada janela (imagens integrais) ->
    média dos canais. Janelas de variância ~0 (área plana) recebem -1.
    """
    screen = np.asarray(screen, dtype=np.uint8)
    template = np.asarray(template, dtype=np.uint8)
    if screen.ndim == 2:
        screen = screen[:, :, None]
    if template.ndim == 2:
        template = template[:, :, None]
    if screen.shape[2] != template.shape[2]:
        raise ValueError("canais diferentes entre tela e template")
    if screen.shape[2] not in (1, 3, 4):
        raise ValueError("esperava imagem 1/3/4 canais")

    channels = 3 if screen.shape[2] >= 3 else 1
    screen = screen[:, :, :channels].astype(np.float64)
    template = template[:, :, :channels].astype(np.float64)

    sh, sw = screen.shape[:2]
    th, tw = template.shape[:2]
    if th > sh or tw > sw:
        raise ValueError(f"template {tw}x{th} maior que a tela {sw}x{sh}")

    fh, fw = sh - th + 1, sw - tw + 1
    n = th * tw
    score_sum = np.zeros((fh, fw))
    used_channels = 0

    for c in range(channels):
        s = screen[:, :, c]
        t = template[:, :, c]

        t_zero = t - t.mean()
        t_norm = np.sqrt((t_zero ** 2).sum())
        if t_norm == 0:
            continue  # canal monocromático no template: sem informação
        t_zero /= t_norm

        corr = _cross_correlate(s, t_zero)

        # Média e variância locais de cada janela via imagens integrais:
        # win[i, j] = ii[i+th, j+tw] - ii[i, j+tw] - ii[i+th, j] + ii[i, j]
        ii = np.zeros((sh + 1, sw + 1))
        ii[1:, 1:] = s.cumsum(0).cumsum(1)
        win_sum = ii[th:, tw:] - ii[:-th, tw:] \
            - ii[th:, :-tw] + ii[:-th, :-tw]

        ii2 = np.zeros((sh + 1, sw + 1))
        ii2[1:, 1:] = (s * s).cumsum(0).cumsum(1)
        win_sqsum = ii2[th:, tw:] - ii2[:-th, tw:] \
            - ii2[th:, :-tw] + ii2[:-th, :-tw]

        # t_zero tem soma zero => numerador do NCC é a própria corr.
        var = win_sqsum - win_sum ** 2 / n
        np.maximum(var, 0.0, out=var)  # ruído de ponto flutuante
        denom = np.sqrt(var)

        ncc = np.full((fh, fw), -1.0)
        valid = denom > 1e-9
        ncc[valid] = corr[valid] / denom[valid]
        score_sum += np.clip(ncc, -1.0, 1.0)
        used_channels += 1

    if used_channels == 0:
        raise ValueError("template sem nenhum canal com variância")

    scores = score_sum / used_channels
    iy, ix = np.unravel_index(np.argmax(scores), scores.shape)
    score = float(scores[iy, ix])
    if score < min_confidence:
        raise LookupError(
            f"melhor match score={score:.3f} < confiança {min_confidence}"
        )
    return int(ix + tw // 2), int(iy + th // 2), score


# --------------------------------------------------------------------------
# 3. Clique — uinput (evdev), mesmo caminho do fallback do main.py
# --------------------------------------------------------------------------

class UInputClicker:
    """Cria um dispositivo virtual uinput e clica com ele."""

    def __init__(self):
        import evdev
        from evdev import ecodes as e
        self._e = e
        keys = [e.BTN_LEFT, e.BTN_RIGHT, e.BTN_MIDDLE] + list(range(1, 512))
        self.dev = evdev.UInput(
            {e.EV_KEY: keys, e.EV_REL: [e.REL_X, e.REL_Y, e.REL_WHEEL]},
            name="LinuxTask-Experimental-Click",
            vendor=0x1234, product=0x5679,
        )

    def click(self, button=None):
        """Pressiona e solta um botão (default: esquerdo)."""
        e = self._e
        btn = e.BTN_LEFT if button is None else button
        self.dev.write(e.EV_KEY, btn, 1)
        self.dev.syn()
        time.sleep(0.02)
        self.dev.write(e.EV_KEY, btn, 0)
        self.dev.syn()

    def close(self):
        self.dev.close()


# --------------------------------------------------------------------------

def main():
    p = argparse.ArgumentParser(
        description="Achar uma imagem na tela (Hyprland/grim) e clicar nela."
    )
    p.add_argument("--template", default=None,
                   help="PNG de referência (recorte da UI alvo); "
                        "obrigatório exceto com --selftest")
    p.add_argument("--click", action="store_true",
                   help="clica no centro do match (default: só move o cursor)")
    p.add_argument("--confidence", type=float, default=0.80,
                   help="confiança NCC mínima, 0-1 (default 0.80)")
    p.add_argument("--output", default=None,
                   help="monitor específico p/ grim (ex.: DP-1); default: todos")
    p.add_argument("--scale", type=float, default=None,
                   help="fator de escala p/ grim em telas HiDPI (ex.: 2)")
    p.add_argument("--template-scale", type=float, default=1.0,
                   help="escala do template se capturado em DPI diferente "
                        "(ex.: template 1x numa sessão 2x -> 2.0)")
    p.add_argument("--timeout", type=float, default=10.0,
                   help="segundos de espera até a imagem aparecer (default 10)")
    p.add_argument("--poll", type=float, default=0.25,
                   help="intervalo entre capturas (default 0.25 s)")
    p.add_argument("--selftest", action="store_true",
                   help="teste headless do matcher (sem display, sem grim)")
    args = p.parse_args()

    if args.selftest:
        _selftest()
        return 0
    template = None
    if args.template:
        try:
            template = np.asarray(Image.open(args.template).convert("RGB"))
        except FileNotFoundError:
            logger.error(
                "template '%s' não existe. Capture um recorte da tela "
                "com: python3 grab_template.py %s",
                args.template, args.template,
            )
            return 1
    if template is None:
        p.error("--template é obrigatório (exceto com --selftest)")

    # Driver real do projeto para mover o cursor (herda clamp + dispatch
    # novo/legado do Hyprland 0.55+).
    from drivers.hyprland import HyprlandDriver

    driver = HyprlandDriver()
    clicker = UInputClicker() if args.click else None

    if args.template_scale != 1.0:
        s = args.template_scale
        tpl_img = Image.fromarray(template)
        template = np.asarray(
            tpl_img.resize(
                (max(1, int(tpl_img.width * s)), max(1, int(tpl_img.height * s))),
                Image.LANCZOS,
            )
        )

    deadline = time.monotonic() + args.timeout
    capture_kwargs = {}
    if args.output:
        capture_kwargs["output"] = args.output
    if args.scale:
        capture_kwargs["scale"] = args.scale

    while True:
        screen = grab_screen(**capture_kwargs)
        try:
            x, y, score = find_image(screen, template, args.confidence)
        except LookupError:
            if time.monotonic() >= deadline:
                logger.error(
                    "imagem não encontrada em %.1fs (confiança %.2f)",
                    args.timeout, args.confidence,
                )
                return 1
            time.sleep(args.poll)
            continue

        logger.info("achou em (%d, %d), score=%.3f", x, y, score)
        driver.move_cursor(x, y)
        logger.info("cursor movido para (%d, %d)", x, y)
        if clicker is not None:
            time.sleep(0.05)
            clicker.click()
            logger.info("clique injetado em (%d, %d)", x, y)
        return 0


def _selftest():
    """Valida o matcher headless (sem display): gera uma 'tela' sintética,
    planta um template e verifica coordenada, score e rejeição."""
    rng = np.random.default_rng(42)

    # Tela sintética 800x600 com textura aleatória (regiões planas gerariam
    # matches ambíguos e NCC indefinido).
    screen = rng.integers(0, 256, size=(600, 800, 3), dtype=np.uint8)

    # Caso positivo: recorte real da tela com ruído leve (score < 1.0).
    tpl_x, tpl_y, tpl_w, tpl_h = 300, 200, 60, 40
    template = screen[tpl_y:tpl_y + tpl_h, tpl_x:tpl_x + tpl_w].copy()
    template = template.astype(np.int16) + rng.integers(-8, 9, template.shape)
    template = np.clip(template, 0, 255).astype(np.uint8)

    x, y, score = find_image(screen, template, min_confidence=0.7)
    cx, cy = tpl_x + tpl_w // 2, tpl_y + tpl_h // 2
    assert (x, y) == (cx, cy), f"posição errada: ({x}, {y}) != ({cx}, {cy})"
    assert score > 0.9, f"score baixo: {score}"
    print(f"[selftest] OK: match em ({x}, {y}), score={score:.3f}")

    # Caso negativo: template aleatório que não existe na tela.
    nonsense = rng.integers(0, 256, size=(40, 60, 3), dtype=np.uint8)
    try:
        find_image(screen, nonsense, min_confidence=0.7)
    except LookupError:
        print("[selftest] OK: template inexistente rejeitado (LookupError)")
    else:
        raise AssertionError("template inexistente não foi rejeitado")


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO, format="[%(levelname)s] %(name)s: %(message)s"
    )
    sys.exit(main())
