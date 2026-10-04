# -*- coding: utf-8 -*-
"""
LinuxTask (experimental) - app.py
Description: GUI do Color Spin — layout compacto estilo LinuxTask com
             "terminal" embutido mostrando o log do loop ao vivo.
Author: Buffy (Codebuff) para JADRT22
License: MIT

Alternativa gráfica ao assistente.py (mesma config spin_config.json):

    python3 app.py        # ou pelo atalho do desktop

  ┌───────────────────────────────────────┐
  │ [Selecionar alvo] [● GIRAR] [■ PARAR] │
  │ ■ RGB(52,54,189) · região 154x60      │
  │ ┌───────────────────────────────────┐ │
  │ │ [giro 3/100] cliquei...           │ │
  │ │            roleta parou (2.1s)    │ │
  │ │            cor rara: 0.4%         │ │
  │ └───────────────────────────────────┘ │
  │ parado                                │
  └───────────────────────────────────────┘
"""

import json
import logging
import os
import queue
import subprocess
import sys
import threading
import time

_HERE = os.path.abspath(os.path.dirname(__file__))
sys.path.insert(0, os.path.join(_HERE, "..", "..", "src"))
sys.path.insert(0, os.path.join(_HERE, ".."))  # capture/vision (mesma pasta)
sys.path.insert(0, os.path.join(_HERE, "..", "image_click"))

import customtkinter as ctk  # noqa: E402
import numpy as np  # noqa: E402
from PIL import Image as PILImage, ImageTk  # noqa: E402
import tkinter as tk  # noqa: E402

import capture as cap  # noqa: E402
from drivers.hyprland import HyprlandDriver  # noqa: E402
from image_click import UInputClicker  # noqa: E402
from spin_until_color import (  # noqa: E402
    color_fraction, wait_region_stable,
)

logger = logging.getLogger("LinuxTask.experimental.app")

CONFIG_PATH = os.path.join(_HERE, "spin_config.json")

_BEHAVIOR = {
    "tolerance": 40, "threshold": 0.02, "interval": 1.5, "settle": 0.3,
    "poll": 0.1, "stable_diff": 2.5, "stable_need": 15,
    "stable_max": 20.0, "confirm_times": 2, "confirm_gap": 1.0,
    "max_spins": 100,
}


class ColorSpinApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Color Spin")
        self.geometry("440x330")
        self.attributes("-topmost", True)
        self.resizable(False, False)
        ctk.set_appearance_mode("dark")

        self.config_data = self._load_config()
        self.stop_event = threading.Event()
        self.loop_thread = None
        self.ui_queue = queue.Queue()
        self.backend = None

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)

        # --- Linha 1: botões (mesmo estilo do LinuxTask) ---
        row = ctk.CTkFrame(self, fg_color="transparent")
        row.grid(row=0, column=0, padx=6, pady=6, sticky="ew")
        for i in range(3):
            row.grid_columnconfigure(i, weight=1)
        self.btn_select = ctk.CTkButton(
            row, text="Selecionar alvo", height=32,
            fg_color="#333333", hover_color="#444444",
            command=self.select_target)
        self.btn_select.grid(row=0, column=0, padx=2, sticky="ew")
        self.btn_toggle = ctk.CTkButton(
            row, text="● GIRAR", height=32,
            fg_color="#d32f2f", hover_color="#b71c1c",
            command=self.toggle_loop)
        self.btn_toggle.grid(row=0, column=1, padx=2, sticky="ew")
        self.btn_stop = ctk.CTkButton(
            row, text="■ PARAR", height=32,
            fg_color="#333333", hover_color="#444444",
            command=self.stop_loop, state="disabled")
        self.btn_stop.grid(row=0, column=2, padx=2, sticky="ew")

        # --- Linha 2: resumo da config ---
        self.lbl_config = ctk.CTkLabel(
            self, anchor="w", justify="left", font=("Arial", 11))
        self.lbl_config.grid(row=1, column=0, padx=10, sticky="ew")
        self._refresh_config_label()

        # --- Linha 3: "terminal" embutido ---
        self.logbox = ctk.CTkTextbox(self, font=("Monospace", 11),
                                     activate_scrollbars=True)
        self.logbox.grid(row=2, column=0, padx=6, pady=6, sticky="nsew")
        self._log("Color Spin pronto. 'Selecionar alvo' marca botão, "
                  "área e cor; 'GIRAR' começa o loop.")

        # --- Linha 4: status ---
        self.lbl_status = ctk.CTkLabel(self, anchor="w", text="parado")
        self.lbl_status.grid(row=3, column=0, padx=10, pady=(0, 6),
                             sticky="ew")

        self.after(100, self._poll)

    # ------------------------------------------------------------------
    # utilidades de UI
    # ------------------------------------------------------------------

    def _log(self, msg):
        self.ui_queue.put(("log", msg))

    def _set_status(self, msg):
        self.ui_queue.put(("status", msg))

    def _poll(self):
        try:
            while True:
                kind, msg = self.ui_queue.get_nowait()
                if kind == "log":
                    self.logbox.configure(state="normal")
                    self.logbox.insert("end", msg + "\n")
                    self.logbox.see("end")
                    self.logbox.configure(state="disabled")
                elif kind == "status":
                    self.lbl_status.configure(text=msg)
                elif callable(msg):
                    msg()
        except queue.Empty:
            pass
        self.after(100, self._poll)

    def _load_config(self):
        if os.path.exists(CONFIG_PATH):
            with open(CONFIG_PATH) as f:
                cfg = json.load(f)
            cfg.update(_BEHAVIOR)
            return cfg
        return None

    def _save_config(self):
        with open(CONFIG_PATH, "w") as f:
            json.dump(self.config_data, f, indent=2)

    def _refresh_config_label(self):
        c = self.config_data
        if not c:
            self.lbl_config.configure(
                text="Nenhum alvo configurado.\n"
                     "Clique em 'Selecionar alvo' para começar.")
            return
        r, g, b = c["color"]
        rx, ry, rw, rh = c["region"]
        self.lbl_config.configure(text=(
            f"Alvo: RGB({r},{g},{b}) · região ({rx},{ry}) {rw}x{rh} · "
            f"até {c['max_spins']} giros"))

    # ------------------------------------------------------------------
    # seleção do alvo (worker thread; janelas Tk só na UI thread)
    # ------------------------------------------------------------------

    def select_target(self):
        self.btn_select.configure(state="disabled")
        self._set_status("selecionando...")

        def _flow():
            try:
                if self.backend is None:
                    self.backend = cap.GrimCapture()

                self._log("[1/3] Marque o BOTÃO de girar (arraste).")
                btn_region = self.backend.select_region()
                if btn_region is None:
                    self._log("cancelado.")
                    return
                bx = btn_region[0] + btn_region[2] // 2
                by = btn_region[1] + btn_region[3] // 2

                self._log("[2/3] Marque a ÁREA DO RESULTADO "
                          "(não a tabela de clans!).")
                region = self.backend.select_region()
                if region is None:
                    self._log("cancelado.")
                    return

                self._log("[3/3] Escolha a cor rara na tela "
                          "(2 cliques, com zoom).")
                screen = self.backend.capture()
                img = PILImage.fromarray(screen).convert("RGB")
                result, done = {}, threading.Event()
                self.ui_queue.put((
                    "ui", lambda: self._color_picker_ui(img, result, done)))
                done.wait()
                color = result.get("rgb")
                if not color:
                    self._log("cancelado.")
                    return

                crop = self.backend.crop(
                    self.backend.capture(), region)
                frac = color_fraction(crop, color, 40)
                if frac >= 0.02:
                    self._log(f"AVISO: a cor já ocupa {frac*100:.1f}% da "
                              "área — você marcou a tabela em vez do "
                              "resultado?")

                self.config_data = {
                    "button_pos": [bx, by],
                    "region": [int(v) for v in region],
                    "color": list(color),
                }
                self.config_data.update(_BEHAVIOR)
                self._save_config()
                self.ui_queue.put(("ui", self._refresh_config_label))
                self._log(f"Alvo salvo: RGB{color} em "
                          f"({region[0]},{region[1]}) {region[2]}x{region[3]}.")
            except Exception as exc:
                self._log(f"ERRO na seleção: {exc}")
                logger.exception("seleção falhou")
            finally:
                self.ui_queue.put(("ui", lambda: self.btn_select.configure(
                    state="normal")))
                self._set_status("parado")

        threading.Thread(target=_flow, daemon=True).start()

    def _color_picker_ui(self, img, result, done):
        """Picker 2 cliques — UI thread (Toplevel da própria app)."""
        arr = np.asarray(img)
        win = tk.Toplevel(self)
        win.title("1º clique: perto da cor · 2º clique: pixel exato")
        win.attributes("-topmost", True)
        scale = min(1.0, 900 / img.width)
        small = img.resize((int(img.width * scale),
                            int(img.height * scale)), PILImage.LANCZOS)
        state = {"photo": ImageTk.PhotoImage(small)}
        canvas = tk.Canvas(win, width=small.width, height=small.height)
        canvas.pack()
        canvas.create_image(0, 0, image=state["photo"], anchor="nw")

        def finish(rgb):
            result["rgb"] = rgb
            done.set()
            try:
                win.destroy()
            except Exception:
                pass

        def on_click1(event):
            ox, oy = int(event.x / scale), int(event.y / scale)
            zoom, half = 8, 30
            y0, y1 = max(0, oy - half), min(arr.shape[0], oy + half + 1)
            x0, x1 = max(0, ox - half), min(arr.shape[1], ox + half + 1)
            crop = img.crop((x0, y0, x1, y1)).resize(
                ((x1 - x0) * zoom, (y1 - y0) * zoom), PILImage.NEAREST)
            state["photo"] = ImageTk.PhotoImage(crop)
            canvas.delete("all")
            canvas.configure(width=crop.width, height=crop.height)
            canvas.create_image(0, 0, image=state["photo"], anchor="nw")

            def on_click2(ev2):
                px, py = x0 + ev2.x // zoom, y0 + ev2.y // zoom
                patch = arr[max(0, py - 1):py + 2, max(0, px - 1):px + 2]
                finish(tuple(int(round(c)) for c in
                             patch.reshape(-1, 3).mean(axis=0)))

            canvas.unbind("<Button-1>")
            canvas.bind("<Button-1>", on_click2)

        canvas.bind("<Button-1>", on_click1)
        win.protocol("WM_DELETE_WINDOW", lambda: finish(None))
        win.bind("<Destroy>", lambda _e: done.set())

    # ------------------------------------------------------------------
    # loop de giro
    # ------------------------------------------------------------------

    def toggle_loop(self):
        if self.loop_thread and self.loop_thread.is_alive():
            return
        if not self.config_data:
            self._log("Configure o alvo primeiro ('Selecionar alvo').")
            return
        self.stop_event.clear()
        self.btn_toggle.configure(text="● GIRANDO", fg_color="#f57c00")
        self.btn_stop.configure(state="normal")
        self.loop_thread = threading.Thread(
            target=self._loop, daemon=True)
        self.loop_thread.start()

    def stop_loop(self):
        self.stop_event.set()
        self._log("parando após este giro...")

    def _loop(self):
        cfg = self.config_data
        backend = self.backend or cap.GrimCapture()
        driver = HyprlandDriver()
        clicker = UInputClicker()
        bx, by = cfg["button_pos"]
        region = tuple(cfg["region"])
        target = tuple(cfg["color"])
        tol, thr = cfg["tolerance"], cfg["threshold"]

        self._log(">>> GIRANDO! <<<")
        try:
            for spin in range(1, cfg["max_spins"] + 1):
                if self.stop_event.is_set():
                    self._log("parado por você.")
                    return
                driver.move_cursor(bx, by)
                time.sleep(0.05)
                clicker.click()
                self._log(f"[giro {spin}/{cfg['max_spins']}] cliquei...")

                time.sleep(cfg["settle"])
                stable, waited = wait_region_stable(
                    backend, region, poll=cfg["poll"],
                    diff=cfg["stable_diff"], need=cfg["stable_need"],
                    max_wait=cfg["stable_max"])
                self._log(f"           roleta "
                          f"{'parou' if stable else 'NÃO parou'} "
                          f"({waited:.1f}s)")

                crop = backend.capture_region(region)
                frac = color_fraction(crop, target, tol)
                self._log(f"           cor rara: {frac*100:.1f}% "
                          f"(paro em >= {thr*100:.1f}%)")

                if frac >= thr:
                    confirmed = True
                    for k in range(1, cfg["confirm_times"]):
                        time.sleep(cfg["confirm_gap"])
                        crop2 = backend.capture_region(region)
                        frac2 = color_fraction(crop2, target, tol)
                        self._log(f"           confirmando {k}: "
                                  f"{frac2*100:.1f}%")
                        if frac2 < thr:
                            confirmed = False
                            break
                    if confirmed:
                        msg = (f"★ GANHOU no giro {spin}! "
                               f"({frac*100:.1f}%)")
                        self._log(msg)
                        try:
                            subprocess.run(
                                ["notify-send", "Color Spin — GANHOU!",
                                 msg], timeout=5, check=False)
                        except Exception:
                            pass
                        return
                    self._log("           falso-positivo (era a roleta "
                              "passando). continuando...")
                time.sleep(cfg["interval"])
            self._log(f"Acabou: {cfg['max_spins']} giros sem a cor.")
        except Exception as exc:
            self._log(f"ERRO no loop: {exc}")
            logger.exception("loop falhou")
        finally:
            self.ui_queue.put(("ui", lambda: (
                self.btn_toggle.configure(text="● GIRAR",
                                          fg_color="#d32f2f"),
                self.btn_stop.configure(state="disabled"),
                self.lbl_status.configure(text="parado"))))


def main():
    app = ColorSpinApp()
    app.mainloop()


if __name__ == "__main__":
    main()
