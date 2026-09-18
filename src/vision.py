# -*- coding: utf-8 -*-
"""
LinuxTask - vision.py
Description: Template matching for the find_image event (pure numpy NCC).
Author: JADRT22 (https://github.com/JADRT22)
License: MIT

Normalized cross-correlation (NCC) per RGB channel:
  - correlation computed via numpy.fft in O(screen log screen) — no
    sliding-window materialization (a 4K screen with a small template
    would blow memory the naive way);
  - local window variance normalized with integral images, so flat
    screen areas cannot produce false positives;
  - no OpenCV/SciPy dependency: numpy and Pillow only.

Algorithm proven experimentally (experimental/image_click/): score
1.000 with 0 px deviation between captures on a real Hyprland session.
"""

import base64
import logging

import numpy as np
from PIL import Image

logger = logging.getLogger(__name__)


def encode_template_png(image):
    """Encodes an RGB ndarray as base64 PNG (for macro JSON storage)."""
    buf = __import__("io").BytesIO()
    Image.fromarray(np.asarray(image, dtype=np.uint8)).save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode("ascii")


def decode_template_png(data):
    """Decodes a base64 PNG string back to an RGB ndarray."""
    raw = base64.b64decode(data)
    return np.asarray(Image.open(__import__("io").BytesIO(raw))
                      .convert("RGB"))


def color_fraction(img, target_rgb, tolerance):
    """Fraction of pixels within `tolerance` of `target_rgb` (RGB).

    Tolerance is the max per-channel distance (Chebyshev): intuitive to
    tune — 40 catches any "similar" color. Used by the wait_color event
    to detect a state color (success flash, loading bar, rare result).
    Returns a float 0..1.
    """
    target = np.array(target_rgb, dtype=np.int16)
    diff = np.abs(np.asarray(img, dtype=np.int16) - target)
    mask = diff.max(axis=2) <= tolerance
    return float(mask.mean())


def _cross_correlate(image_f, template_f):
    """Valid cross-correlation image×template via FFT (numpy only).

    Returns array (h-th+1, w-tw+1) where [iy, ix] is the sum of
    image[iy:iy+th, ix:ix+tw] * template. The FFT runs at the full
    linear-convolution size (h+th-1, w+tw-1) to avoid circular
    wrap-around contaminating edge windows.
    """
    h, w = image_f.shape
    th, tw = template_f.shape
    fh, fw = h - th + 1, w - tw + 1

    f_shape = (h + th - 1, w + tw - 1)
    f_image = np.fft.rfft2(image_f, s=f_shape)
    f_template = np.fft.rfft2(template_f[::-1, ::-1], s=f_shape)
    full = np.fft.irfft2(f_image * f_template, s=f_shape)

    # Window offset i maps to full[i + th - 1] (full convolution layout).
    return full[th - 1:th - 1 + fh, tw - 1:tw - 1 + fw]


def find_image(screen, template, min_confidence=0.80):
    """Finds `template` (HxWx3 uint8) inside `screen` (HxWx3 uint8).

    Returns (cx, cy, score): center of the best match in screen
    coordinates (ints) and the mean per-channel NCC score (-1..1).
    Raises LookupError when the best score is below `min_confidence`.
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
            continue  # monochromatic channel: no information
        t_zero /= t_norm

        corr = _cross_correlate(s, t_zero)

        # Local window sums via integral images:
        # win[i, j] = ii[i+th, j+tw] - ii[i, j+tw] - ii[i+th, j] + ii[i, j]
        ii = np.zeros((sh + 1, sw + 1))
        ii[1:, 1:] = s.cumsum(0).cumsum(1)
        win_sum = ii[th:, tw:] - ii[:-th, tw:] \
            - ii[th:, :-tw] + ii[:-th, :-tw]

        ii2 = np.zeros((sh + 1, sw + 1))
        ii2[1:, 1:] = (s * s).cumsum(0).cumsum(1)
        win_sqsum = ii2[th:, tw:] - ii2[:-th, tw:] \
            - ii2[th:, :-tw] + ii2[:-th, :-tw]

        # t_zero sums to zero => the NCC numerator IS the correlation.
        var = win_sqsum - win_sum ** 2 / n
        np.maximum(var, 0.0, out=var)  # floating-point noise
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
