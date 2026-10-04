# -*- coding: utf-8 -*-
"""
LinuxTask (experimental) - assistente.py
Description: Assistente guiado: clique por imagem + parar por cor.
Author: Buffy (Codebuff) para JADRT22
License: MIT

UM comando que te guia do zero até o loop girando:

    python3 assistente.py

Ele pergunta (com seleção visual na tela, nada de coordenadas):
  1. Onde é o BOTÃO de girar?     -> arraste um quadradinho nele
  2. Onde aparece o RESULTADO?    -> arraste na área da roleta/resultado
  3. Qual é a COR rara?           -> clique na cor em QUALQUER lugar da
     tela (ex.: na tabela de clans do jogo), com zoom pra acertar o pixel
E faz uma checagem de sanidade: se a cor já estiver visível na área do
resultado ANTES de girar, avisa (você provavelmente marcou a tabela em
vez da área do resultado) e deixa remarcar.

A configuração fica salva em spin_config.json — nas próximas vezes ele
pergunta se quer reaproveitar (só Enter pra começar direto).
"""

import json
import logging
import os
import subprocess
import sys
import time

_HERE = os.path.abspath(os.path.dirname(__file__))
for p in (os.path.join(_HERE, "..", "..", "src"),
          os.path.join(_HERE, ".."),  # capture/vision (experimental/)
          os.path.join(_HERE, "..", "image_click")):
    p = os.path.abspath(p)
    if p not in sys.path:
        sys.path.insert(0, p)

import numpy as np  # noqa: E402
from PIL import Image, ImageTk  # noqa: E402
import tkinter as tk  # noqa: E402

import capture as cap  # noqa: E402
from drivers.hyprland import HyprlandDriver  # noqa: E402
from image_click import UInputClicker  # noqa: E402
from spin_until_color import (  # noqa: E402
    color_fraction, wait_region_stable,
)

logger = logging.getLogger("LinuxTask.experimental.assistente")

CONFIG_PATH = os.path.join(_HERE, "spin_config.json")
LOG_PATH = os.path.join(_HERE, "spin_log.txt")

# Com terminal: comportamento interativo de sempre. Sem terminal
# (duplo clique no launcher): pula as perguntas de stdin, confirma via
# zenity quando disponível e registra o loop em spin_log.txt.
_TTY = sys.stdin.isatty() and sys.stdout.isatty()


def _log(msg):
    """Print no terminal, ou append no log quando lançado pelo desktop."""
    if _TTY:
        print(msg, flush=True)
    else:
        with open(LOG_PATH, "a") as f:
            f.write(time.strftime("[%H:%M:%S] ") + msg + "\n")


def _notify(title, body):
    """Notificação de desktop; cai para o log se não houver notify-send."""
    try:
        subprocess.run(["notify-send", title, body], timeout=5,
                       check=False)
    except (FileNotFoundError, subprocess.SubprocessError):
        _log(f"{title}: {body}")

# Comportamento do loop: sempre sobrescrito a cada execução (não é parte
# da configuração do usuário — botão/região/cor é que ficam salvos).
# Assim, ajustes de estabilização valem mesmo com config antiga no disco.
_BEHAVIOR_DEFAULTS = {
    "tolerance": 40,
    "threshold": 0.02,
    "interval": 1.5,
    "settle": 0.3,
    "poll": 0.1,          # leituras a cada 0.1s na detecção de parada
    "stable_diff": 2.5,   # diferença média máxima pra considerar parado
    "stable_need": 15,    # 15 leituras paradas = ~1.5s congelada
    "stable_max": 20.0,   # espera até 20s a roleta parar
    "confirm_times": 2,   # re-confirma a cor depois de detectar
    "confirm_gap": 1.0,   # 1s entre detecção e cada re-confirmação
    "max_spins": 100,
}


# --------------------------------------------------------------------------
# Passos guiados (cada um devolve o dado que precisa ser salvo)
# --------------------------------------------------------------------------

def _slurp_region(prompt):
    """Seleção visual de região via slurp; mostra o prompt no terminal."""
    print(f"\n→ {prompt}")
    print("  (arraste um quadradinho na tela; Esc cancela e refaz)")
    try:
        geom = subprocess.check_output(["slurp"]).decode().strip()
    except subprocess.CalledProcessError:
        return None  # Esc: o chamador decide repetir
    pos, _, size = geom.partition(" ")
    x_s, _, y_s = pos.partition(",")
    w_s, _, h_s = size.lower().partition("x")
    return (int(x_s), int(y_s), int(w_s), int(h_s))


def _ask_region(prompt):
    """Pede a região até sair uma válida (Esc repete a pergunta)."""
    while True:
        region = _slurp_region(prompt)
        if region and region[2] > 2 and region[3] > 2:
            return region
        print("  região muito pequena ou cancelada — tenta de novo.")


def _pick_color_fullscreen(backend):
    """PASSO 3: escolhe a cor em QUALQUER lugar da tela.

    O clan raro normalmente ainda NÃO está na área do resultado (você
    nunca ganhou ele) — a única referência da cor costuma ser a TABELA
    de clans do jogo. Por isso a escolha é na tela inteira, em dois
    cliques: 1º na área aproximada, 2º no pixel exato (zoom 8x).
    Retorna (r, g, b) ou None se cancelado.
    """
    screen = backend.capture()
    img = Image.fromarray(screen).convert("RGB")
    arr = np.asarray(img)
    result = {}

    # --- Janela 1: tela inteira escalada ---
    scale = min(1.0, 900 / img.width)
    small = img.resize(
        (int(img.width * scale), int(img.height * scale)), Image.LANCZOS
    )
    root = tk.Tk()
    root.title("1/2 — clique PERTO da cor do clan (na tabela do jogo)")
    tk.Label(root, text="1º clique: aproximo o zoom. Depois você "
                        "escolhe o pixel exato.").pack()
    tk_img = ImageTk.PhotoImage(small)
    canvas = tk.Canvas(root, width=small.width, height=small.height)
    canvas.pack()
    canvas.create_image(0, 0, image=tk_img, anchor="nw")

    def on_click1(event):
        result["approx"] = (int(event.x / scale), int(event.y / scale))
        root.destroy()

    canvas.bind("<Button-1>", on_click1)
    root.mainloop()
    if "approx" not in result:
        return None
    ox, oy = result["approx"]

    # --- Janela 2: zoom 8x em volta do ponto ---
    zoom, half = 8, 30
    y0, y1 = max(0, oy - half), min(arr.shape[0], oy + half + 1)
    x0, x1 = max(0, ox - half), min(arr.shape[1], ox + half + 1)
    crop = img.crop((x0, y0, x1, y1)).resize(
        ((x1 - x0) * zoom, (y1 - y0) * zoom), Image.NEAREST
    )
    root = tk.Tk()
    root.title("2/2 — clique NO PIXEL exato da cor")
    tk.Label(root, text=f"zoom 8x de ({ox},{oy}) — clique no meio da "
                        "cor do clan").pack()
    tk_img2 = ImageTk.PhotoImage(crop)
    canvas = tk.Canvas(root, width=crop.width, height=crop.height)
    canvas.pack()
    canvas.create_image(0, 0, image=tk_img2, anchor="nw")

    def on_click2(event):
        px = x0 + event.x // zoom
        py = y0 + event.y // zoom
        # Média 3x3 pra não pegar ruído de 1 pixel
        patch = arr[max(0, py - 1):py + 2, max(0, px - 1):px + 2]
        result["rgb"] = tuple(
            int(round(c)) for c in patch.reshape(-1, 3).mean(axis=0)
        )
        root.destroy()

    canvas.bind("<Button-1>", on_click2)
    root.mainloop()
    return result.get("rgb")


def _confirm(config):
    """Mostra o resumo e pede Enter pra começar."""
    bx, by = config["button_pos"]
    rx, ry, rw, rh = config["region"]
    r, g, b = config["color"]
    summary = [
        "CONFIGURAÇÃO:",
        f"  Botão de girar:  ({bx}, {by})",
        f"  Área resultado:  ({rx}, {ry}) {rw}x{rh}",
        f"  Cor rara:        RGB {r},{g},{b}  (tol {config['tolerance']})",
        f"  Parar quando a cor ocupar >= {config['threshold']*100:.1f}% da área",
        f"  Espera a roleta PARAR (~1.5s congelada, até "
        f"{config.get('stable_max', 20.0):.0f}s por giro)",
        f"  Confirma a cor {config.get('confirm_times', 2)}x antes de "
        "parar (mata falso-positivo da roleta)",
        f"  Pausa entre giros: {config['interval']}s | máx {config['max_spins']} giros",
    ]
    print("\n" + "=" * 60)
    print("\n".join(summary))
    print("=" * 60)
    if _TTY:
        input("Enter pra COMEÇAR a girar (Ctrl+C a qualquer momento "
              "pra parar)...")
    else:
        # Lançado pelo desktop: pede confirmação gráfica; sem zenity,
        # começa direto após 3s.
        try:
            r = subprocess.run(
                ["zenity", "--question",
                 "--title=Color Spin",
                 "--text=Começar a girar agora?\n\n" +
                 "\n".join(s.strip() for s in summary[1:5])],
                timeout=60, check=False)
            if r.returncode != 0:
                print("Cancelado pelo usuário.")
                sys.exit(0)
        except (FileNotFoundError, subprocess.SubprocessError):
            time.sleep(3)


def _run_loop(config):
    """O loop de giro em si (mesma lógica do spin_until_color)."""
    backend = cap.GrimCapture()
    driver = HyprlandDriver()
    clicker = UInputClicker()
    bx, by = config["button_pos"]
    region = tuple(config["region"])
    target = tuple(config["color"])
    tol = config["tolerance"]
    thr = config["threshold"]
    interval = config["interval"]
    settle = config.get("settle", 0.3)
    poll = config.get("poll", 0.1)
    stable_diff = config.get("stable_diff", 2.5)
    stable_need = config.get("stable_need", 15)
    stable_max = config.get("stable_max", 20.0)
    confirm_times = config.get("confirm_times", 2)
    confirm_gap = config.get("confirm_gap", 1.0)
    max_spins = config["max_spins"]

    _log(">>> GIRANDO! (Ctrl+C no terminal pra parar)")
    try:
        for spin in range(1, max_spins + 1):
            driver.move_cursor(bx, by)
            time.sleep(0.05)
            clicker.click()
            _log(f"[giro {spin}/{max_spins}] cliquei...")

            # Espera a ROLETA PARAR: a animação passa por vários clans
            # e checar durante ela daria falso-positivo (clan raro que
            # só passou). Só checo a cor com a imagem estável.
            if settle > 0:
                time.sleep(settle)
            stable, waited = wait_region_stable(
                backend, region, poll=poll, diff=stable_diff,
                need=stable_need, max_wait=stable_max,
            )
            status = "roleta parou" if stable else "não parou a tempo"
            _log(f"           {status} ({waited:.1f}s)")

            crop = backend.capture_region(region)
            frac = color_fraction(crop, target, tol)
            _log(f"           cor rara: {frac*100:.1f}% da área "
                 f"(paro em >= {thr*100:.1f}%)")

            if frac >= thr:
                # Confirmação dupla: o clan raro que só PASSOU na roleta
                # continua girando (some da região); o resultado real
                # fica parado. Exijo a cor em TODAS as re-checagens.
                confirmed = True
                for k in range(1, confirm_times):
                    time.sleep(confirm_gap)
                    crop2 = backend.capture_region(region)
                    frac2 = color_fraction(crop2, target, tol)
                    print(f"           confirmando {k}/{confirm_times-1}: "
                          f"{frac2*100:.1f}%", flush=True)
                    if frac2 < thr:
                        confirmed = False
                        break
                if confirmed:
                    _log(f"\n★ GANHOU no giro {spin}! Cor rara "
                         f"confirmada ({frac*100:.1f}%). Parando.")
                    if not _TTY:
                        _notify("Color Spin — GANHOU!",
                                f"Cor rara confirmada no giro {spin} "
                                f"({frac*100:.1f}%).")
                    return 0
                _log("           falso-positivo: a cor sumiu (era a "
                     "roleta passando). Continuando...")
            time.sleep(interval)
        _log(f"\nAcabou: {max_spins} giros e a cor não apareceu.")
        if not _TTY:
            _notify("Color Spin — fim", f"{max_spins} giros sem a cor.")
        return 2
    except KeyboardInterrupt:
        _log("\nParado por você (Ctrl+C).")
        return 130


# --------------------------------------------------------------------------

def main():
    logging.basicConfig(
        level=logging.WARNING, format="[%(levelname)s] %(name)s: %(message)s"
    )
    backend = cap.GrimCapture()

    print("=" * 60)
    print(" ASSISTENTE: girar até a cor rara aparecer")
    print("=" * 60)

    config = None
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH) as f:
            config = json.load(f)
        if _TTY:
            ans = input("\nAchei a configuração da última vez. "
                        "Reaproveitar? [S/n]: ").strip().lower()
            if ans in ("n", "nao", "não"):
                config = None
        else:
            _log("Config da última vez encontrada — reaproveitando "
                 "(rode num terminal para refazer a seleção).")

    if config is None:
        config = {}

        # 1. Botão de girar
        while True:
            btn_region = _ask_region(
                "PASSO 1/3 — Onde é o BOTÃO de girar?")
            screen = backend.capture()
            x, y, w, h = btn_region
            template = screen[y:y + h, x:x + w]
            if template.size == 0:
                print("  região vazia — tenta de novo.")
                continue
            break
        config["button_pos"] = [x + w // 2, y + h // 2]

        # 2. Área do resultado (NÃO a tabela de clans!)
        config["region"] = list(_ask_region(
            "PASSO 2/3 — Onde o RESULTADO aparece? "
            "(a área da ROLETA que muda — NÃO a tabela de clans do lado)"))

        # 3. Cor rara — escolhida na TELA INTEIRA (a cor normalmente só
        #    existe na tabela do jogo, você ainda não tem o clan).
        while True:
            picked = _pick_color_fullscreen(backend)
            if picked:
                config["color"] = list(picked)
                break
            print("  sem cor escolhida — tenta de novo (clique na janela).")
        print(f"  cor escolhida: RGB {','.join(map(str, config['color']))}")

        # (parâmetros de comportamento entram via _BEHAVIOR_DEFAULTS abaixo)

        with open(CONFIG_PATH, "w") as f:
            json.dump(config, f, indent=2)
        print(f"\n(configuração salva em {os.path.basename(CONFIG_PATH)} "
              "— na próxima vez é só Enter)")

    # Sempre aplica os parâmetros de comportamento atuais (a config
    # salva só carrega as seleções: botão, região, cor).
    config.update(_BEHAVIOR_DEFAULTS)

    # Válvula de escape: editando spin_config.json à mão, um bloco
    # "overrides" vence os defaults (ex. roleta de 30s):
    #   "overrides": {"stable_max": 30.0, "tolerance": 60}
    for key, value in config.pop("overrides", {}).items():
        config[key] = value

    # SANIDADE: a cor rara NÃO pode já estar visível na área do
    # resultado antes do primeiro giro. Se estiver, você marcou a
    # tabela (que nunca sai da tela) em vez da área do resultado — e
    # o loop detectaria "ganho" no primeiro giro, sempre.
    while True:
        crop = backend.capture_region(tuple(config["region"]))
        frac = color_fraction(crop, tuple(config["color"]),
                              config["tolerance"])
        if frac < config["threshold"]:
            break
        print(f"\n!! PROBLEMA: a cor escolhida JÁ está visível na área "
              f"monitorada ({frac*100:.1f}% >= "
              f"{config['threshold']*100:.0f}%).")
        print("   Você provavelmente marcou a TABELA de clans em vez da "
              "área onde o RESULTADO aparece — a tabela nunca sai da "
              "tela, então detectaria ganho no primeiro giro sempre.")
        if not _TTY:
            _log("!! SANIDADE: cor já visível na área monitorada — "
                 "provavelmente a tabela foi marcada. Rodar num terminal "
                 "para remarcar.")
            break
        ans = input("   Remarcar a área do resultado? [S/n]: ").strip().lower()
        if ans in ("n", "nao", "não"):
            print("   (seguindo com a configuração atual — seu risco)")
            break
        config["region"] = list(_ask_region(
            "PASSO 2 (de novo) — Onde o RESULTADO aparece? "
            "(a área da ROLETA que muda — NÃO a tabela)"))
        # Persiste a correção (senão da próxima volta a região errada)
        with open(CONFIG_PATH, "w") as f:
            json.dump(config, f, indent=2)

    _confirm(config)
    try:
        return _run_loop(config)
    finally:
        if not _TTY:
            try:
                os.remove(LOG_PATH)
            except OSError:
                pass


if __name__ == "__main__":
    sys.exit(main())
