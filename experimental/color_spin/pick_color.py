# -*- coding: utf-8 -*-
"""
LinuxTask (experimental) - pick_color.py
Description: Descobre o RGB alvo clicando num pixel de um PNG.
Author: Buffy (Codebuff) para JADRT22
License: MIT

Abre a imagem capturada por grab_region.py; você clica no pixel cuja cor
quer monitorar (ex.: o centro da cor rara do resultado) e o script imprime
o RGB médio de uma área 5x5 ao redor — robusto a ruído de 1 pixel.

    python3 pick_color.py resultado.png
"""

import sys

import numpy as np
from PIL import Image, ImageTk
import tkinter as tk


def main():
    if len(sys.argv) < 2:
        print("uso: python3 pick_color.py <imagem.png>")
        return 1
    path = sys.argv[1]

    img = Image.open(path).convert("RGB")
    arr = np.asarray(img)
    result = {}

    root = tk.Tk()
    root.title("clique na cor alvo")
    tk_img = ImageTk.PhotoImage(img)
    canvas = tk.Canvas(root, width=img.width, height=img.height)
    canvas.pack()
    canvas.create_image(0, 0, image=tk_img, anchor="nw")

    def on_click(event):
        x, y = event.x, event.y
        # Média 5x5 (com borda segura) para não pegar ruído de 1 pixel
        y0, y1 = max(0, y - 2), min(arr.shape[0], y + 3)
        x0, x1 = max(0, x - 2), min(arr.shape[1], x + 3)
        patch = arr[y0:y1, x0:x1]
        rgb = tuple(int(round(c)) for c in
                    patch.reshape(-1, 3).mean(axis=0))
        result["rgb"] = rgb
        result["pos"] = (x, y)
        root.destroy()

    canvas.bind("<Button-1>", on_click)
    root.mainloop()

    if "rgb" not in result:
        print("nenhum pixel escolhido.")
        return 1

    x, y = result["pos"]
    r, g, b = result["rgb"]
    print(f"cor em ({x},{y}): RGB {r},{g},{b}")
    print(f"uso no spin: --color {r},{g},{b}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
