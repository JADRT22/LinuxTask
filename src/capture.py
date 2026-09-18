# -*- coding: utf-8 -*-
"""
LinuxTask - capture.py
Description: Screen capture backends for the find_image event.
Author: JADRT22 (https://github.com/JADRT22)
License: MIT

Each backend answers two questions for its desktop environment:
  - capture()  -> full-screen RGB ndarray (numpy, HxWx3, uint8)
  - select_region() -> (x, y, w, h) tuple picked interactively by the user

Only Hyprland (grim/slurp) is implemented for now. The other environments
raise NotImplementedError with a clear message; capture_backend() picks
the right backend from the same env vars the driver factory uses.
"""

import logging
import os
import subprocess
import time

import numpy as np
from PIL import Image

logger = logging.getLogger(__name__)


class CaptureError(RuntimeError):
    """Raised when a screen capture fails (missing tool or runtime error)."""


class GrimCapture:
    """Hyprland (and any wlroots compositor): grim + slurp."""

    name = "grim"

    def __init__(self, output=None, scale=None):
        self.output = output
        self.scale = scale

    def capture(self):
        """Full-screen capture via grim, decoded to an RGB ndarray.

        NOTE: recent grim builds only emit PNG to stdout when the output
        file argument is given explicitly as '-' (verified on Arch).
        """
        cmd = ["grim"]
        if self.output:
            cmd.append(f"--output={self.output}")
        if self.scale:
            cmd.append(f"--scale={self.scale}")
        cmd.append("-")
        try:
            png = subprocess.run(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                check=True,
            ).stdout
        except FileNotFoundError:
            raise CaptureError(
                "grim não encontrado. Instale com: pacman -S grim "
                "(ou o equivalente da sua distro)"
            )
        except subprocess.CalledProcessError as exc:
            raise CaptureError(
                "grim falhou: %s"
                % exc.stderr.decode(errors="replace").strip()
            )
        return np.asarray(Image.open(__import__("io").BytesIO(png))
                          .convert("RGB"))

    def select_region(self):
        """Interactive region selection via slurp.

        Returns (x, y, w, h) or None if the user cancelled (Esc).
        """
        try:
            geom = subprocess.check_output(["slurp"]).decode().strip()
        except FileNotFoundError:
            raise CaptureError(
                "slurp não encontrado. Instale com: pacman -S slurp "
                "(ou o equivalente da sua distro)"
            )
        except subprocess.CalledProcessError:
            return None  # user pressed Esc

        try:
            pos, _, size = geom.partition(" ")
            x_s, _, y_s = pos.partition(",")
            w_s, _, h_s = size.lower().partition("x")
            x, y = int(x_s), int(y_s)
            w, h = int(w_s), int(h_s)
        except ValueError:
            raise CaptureError(f"geometria inesperada do slurp: {geom!r}")
        if w <= 0 or h <= 0:
            return None
        return (x, y, w, h)

    def crop(self, screen, region):
        """Crops region (x, y, w, h) from a screen ndarray."""
        x, y, w, h = region
        return screen[y:y + h, x:x + w].copy()

    def capture_region(self, region):
        """Captures only a region (x, y, w, h) via grim -g "x,y WxH".

        Much cheaper than a full capture when polling a small UI area.
        Returns an RGB ndarray (h, w, 3).
        """
        x, y, w, h = region
        cmd = ["grim", "-g", f"{x},{y} {w}x{h}"]
        if self.output:
            cmd.append(f"--output={self.output}")
        if self.scale:
            cmd.append(f"--scale={self.scale}")
        cmd.append("-")
        try:
            png = subprocess.run(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                check=True,
            ).stdout
        except FileNotFoundError:
            raise CaptureError(
                "grim não encontrado. Instale com: pacman -S grim"
            )
        except subprocess.CalledProcessError as exc:
            raise CaptureError(
                "grim falhou: %s"
                % exc.stderr.decode(errors="replace").strip()
            )
        return np.asarray(Image.open(__import__("io").BytesIO(png))
                          .convert("RGB"))


def wait_region_stable(backend, region, poll=0.1, diff=2.5, need=15,
                       max_wait=20.0):
    """Waits until consecutive captures of `region` stop changing.

    Kills the classic roulette/gacha false positive: an animation that
    "passes" by a rare result must not be treated as the outcome. The
    caller only checks a condition once the image froze for `need`
    consecutive comparisons (need=15, poll=0.1 -> ~1.5s frozen; a
    decelerating animation does not pass as stopped).

    Args:
        backend: object with capture_region(region) -> ndarray.
        region: (x, y, w, h).
        poll: seconds between captures.
        diff: max mean per-pixel delta (0-255) to count as "no change".
        need: consecutive stable comparisons required.
        max_wait: give up after this many seconds (returns False).

    Returns (stable: bool, elapsed_seconds: float).
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


def capture_backend():
    """Picks a capture backend from the environment.

    Same detection order as drivers.factory. Environments without an
    implemented backend raise NotImplementedError (the UI catches it and
    shows a dialog).
    """
    if os.environ.get("HYPRLAND_INSTANCE_SIGNATURE"):
        return GrimCapture()
    desktop = os.environ.get("XDG_CURRENT_DESKTOP", "").upper()
    if "HYPRLAND" in desktop:
        return GrimCapture()
    # TODO(vision): X11 via python-xlib GetImage; GNOME/KDE via Portal
    # Screenshot. Keep the NotImplementedError message in sync with the
    # CHANGELOG "Known limitations" note.
    env = desktop or "desconhecido"
    raise NotImplementedError(
        "Captura de tela (evento de imagem) ainda não suportada neste "
        f"ambiente ({env}). Suportado hoje: Hyprland (grim/slurp)."
    )
