# -*- coding: utf-8 -*-
"""
LinuxTask - ui_theme.py
Description: Adwaita dark colour tokens for the toolbar, each derived from a
             value in libadwaita's own stylesheet rather than from memory.
Author: JADRT22 (https://github.com/JADRT22)
License: MIT

Every entry in TOKENS carries the line it came from. The stylesheet is
extracted from the library that actually draws GNOME's widgets on this
machine:

    gresource extract /usr/lib/libadwaita-1.so.0 \
        /org/gnome/Adwaita/styles/gtk.css

Values that Adwaita expresses as `color-mix(in srgb, currentColor N%,
transparent)` are stored here as the same mix over a known base, because
Tk has no compositor to mix them for us. Nothing in this module imports
tkinter, so it stays importable and testable without a display, and the
capture script can ask it for a palette without opening a window.
"""

from __future__ import annotations

import shutil
import subprocess

# Where the citations point. Kept as one string so a report can print it.
SOURCE = ("libadwaita-1.so.0:/org/gnome/Adwaita/styles/gtk.css "
          "(extraído com gresource)")

# Literal tokens, straight out of the dark-mode block at gtk.css:94 plus the
# palette at the top of the file. rgba entries keep their alpha because
# Adwaita composites them over whatever is underneath.
TOKENS = {
    "window_bg":   ("#222226", "gtk.css:94 window_bg_color"),
    "window_fg":   ("#ffffff", "gtk.css:94 window_fg_color"),
    "view_bg":     ("#1d1d20", "gtk.css:94 view_bg_color"),
    "headerbar_bg": ("#2e2e32", "gtk.css:94 headerbar_bg_color"),
    "popover_bg":  ("#36363a", "gtk.css:94 popover_bg_color"),
    "dialog_bg":   ("#36363a", "gtk.css:94 dialog_bg_color"),
    "shade":       ("rgba(0,0,6,0.25)", "gtk.css:94 shade_color RGB(0 0 6 / 25%)"),
    "blue_3":      ("#3584e4", "gtk.css:5 @define-color blue_3"),
    "red_4":       ("#c01c28", "gtk.css:94 destructive_bg_color @red_4"),
    "green_5":     ("#26a269", "gtk.css:94 success_bg_color @green_5"),
    "warning":     ("#cd9309", "gtk.css:94 warning_bg_color #cd9309"),
}


def hex_to_rgb(value):
    """'#rrggbb' -> (r, g, b). Alpha 0.0-1.0 handled by parse()."""
    value = value.lstrip("#")
    return tuple(int(value[i:i + 2], 16) for i in (0, 2, 4))


def rgb_to_hex(rgb):
    return "#%02x%02x%02x" % tuple(max(0, min(255, int(round(c)))) for c in rgb)


def parse(value):
    """Accepts '#rrggbb' or 'rgba(r,g,b,a)' and returns (rgb, alpha)."""
    if value.startswith("rgba"):
        inner = value[value.index("(") + 1:value.index(")")]
        r, g, b, a = (float(p) for p in inner.split(","))
        return (r, g, b), a
    return hex_to_rgb(value), 1.0


def over(fg, alpha, bg):
    """Alpha-composites `fg` at `alpha` over `bg`; both are #rrggbb or rgba."""
    fg_rgb, fg_a = parse(fg)
    bg_rgb, bg_a = parse(bg)
    a = alpha * fg_a
    return rgb_to_hex(tuple(f * a + b * (1.0 - a)
                            for f, b in zip(fg_rgb, bg_rgb, strict=True)))


def relative_luminance(color):
    """WCAG 2.1 relative luminance of a solid #rrggbb."""
    channels = []
    for c in hex_to_rgb(color):
        s = c / 255.0
        channels.append(s / 12.92 if s <= 0.04045
                        else ((s + 0.055) / 1.055) ** 2.4)
    r, g, b = channels
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast_ratio(a, b):
    """WCAG 2.1 contrast ratio between two solid colours."""
    la, lb = relative_luminance(a), relative_luminance(b)
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)


# GNOME 47 accent names -> the Adwaita palette entry each one selects. Only
# names whose target is defined in the extracted stylesheet are listed; an
# accent we cannot cite falls back to blue_3 instead of guessing a hex.
_ACCENT_BY_NAME = {
    "blue": "#3584e4",
    "teal": "#2190a4",
    "green": "#3a944a",
    "yellow": "#c88800",
    "orange": "#ed5b00",
    "red": "#e62d42",
    "pink": "#d56199",
    "purple": "#9141ac",
    "slate": "#6f8396",
}

_GSETTINGS_SCHEMA = "org.gnome.desktop.interface"
_GSETTINGS_KEY = "accent-color"


def system_accent():
    """Returns (accent_hex, how_it_was_found).

    Tries the GNOME settings key first, because that is the same source
    libadwaita reads: when it answers, the toolbar follows the desktop's
    accent instead of pinning a colour. On a KDE session the schema or the
    key is usually absent, and the documented default takes over — the
    capture script pins the result anyway so PNGs stay reproducible.
    """
    if shutil.which("gsettings") is None:
        return _ACCENT_BY_NAME["blue"], "default blue_3 (gsettings ausente)"
    try:
        found = subprocess.run(
            ["gsettings", "get", _GSETTINGS_SCHEMA, _GSETTINGS_KEY],
            capture_output=True, text=True, timeout=2, check=False)
    except (OSError, subprocess.SubprocessError):
        return _ACCENT_BY_NAME["blue"], "default blue_3 (gsettings falhou)"
    raw = found.stdout.strip().strip("'\"")
    if found.returncode != 0 or not raw:
        return (_ACCENT_BY_NAME["blue"],
                "default blue_3 (%s.%s ausente)"
                % (_GSETTINGS_SCHEMA, _GSETTINGS_KEY))
    name = raw.split("-")[0].lower()
    return (_ACCENT_BY_NAME.get(name, _ACCENT_BY_NAME["blue"]),
            "gsettings %s = %s" % (_GSETTINGS_KEY, raw))


class Palette:
    """The dark Adwaita palette, pre-composited for a Tk canvas.

    Tk draws in solid colours only, so every token Adwaita writes as an
    alpha mix is resolved here against the surface it sits on. The
    attributes are plain #rrggbb strings; `citations` says where each one
    came from, which is what `visual.md` quotes.
    """

    def __init__(self, accent=None):
        self.window_bg = TOKENS["window_bg"][0]
        self.window_fg = TOKENS["window_fg"][0]
        self.view_bg = TOKENS["view_bg"][0]
        self.headerbar_bg = TOKENS["headerbar_bg"][0]
        self.popover_bg = TOKENS["popover_bg"][0]
        self.dialog_bg = TOKENS["dialog_bg"][0]

        if accent is None:
            accent, self.accent_source = system_accent()
        else:
            self.accent_source = "fixado para captura"
        self.accent = accent
        self.accent_fg = self.window_fg          # accent_fg_color = white
        self.destructive = TOKENS["red_4"][0]
        self.destructive_fg = self.window_fg
        self.success = TOKENS["green_5"][0]
        self.success_fg = self.window_fg
        self.warning = TOKENS["warning"][0]
        self.warning_fg = self.window_fg

        # button.flat: transparent, hover 10% currentColor, active 19%.
        # gtk.css: `button.flat:hover { background: color-mix(in srgb,
        # currentColor 10%, transparent) }` and `:active` at 19%.
        self.raised_bg = over(self.window_fg, 0.10, self.window_bg)
        self.hover = over(self.window_fg, 0.10, self.window_bg)
        self.active = over(self.window_fg, 0.19, self.window_bg)
        # borders: color-mix(in srgb, currentColor 15%, transparent)
        self.border = over(self.window_fg, 0.15, self.window_bg)
        self.popover_border = over(self.window_fg, 0.15, self.popover_bg)
        # .dim-label { opacity: 0.55 } -- the caption colour Adwaita uses for
        # secondary text such as the hint under a preference section.
        self.dim = over(self.window_fg, 0.55, self.window_bg)
        # Track of a switch or a progress bar at rest: currentColor 15%.
        self.track = over(self.window_fg, 0.15, self.window_bg)
        self.track_fg = self.window_fg

        # Adwaita metrics. 6px radius on buttons, 12px on popovers; the
        # 34px headerbar button is what the 44px toolbar row is built from.
        self.radius = 6
        self.popover_radius = 12
        self.border_width = 1

        self.citations = {
            "window_bg": TOKENS["window_bg"][1],
            "window_fg": TOKENS["window_fg"][1],
            "accent": self.accent_source,
            "destructive": TOKENS["red_4"][1],
            "success": TOKENS["green_5"][1],
            "warning": TOKENS["warning"][1],
            "raised_bg": "button.flat/hover: currentColor 10% sobre window_bg",
            "hover": "button.flat:hover: currentColor 10% sobre window_bg",
            "active": "button.flat:active: currentColor 19% sobre window_bg",
            "border": "borders: currentColor 15% sobre window_bg",
            "dim": ".dim-label { opacity: 0.55 } sobre window_bg",
            "track": "switch/progress em repouso: currentColor 15% sobre window_bg",
            "radius": "libadwaita button border-radius 6px",
            "popover_radius": "libadwaita popover border-radius 12px",
        }

    # -- measurement helpers used by the report and the tests -------------

    def pairs(self):
        """The contrast pairs the redesign must answer for.

        Returns (label, foreground, background, threshold, kind). Text
        labels are held to WCAG 1.4.5 (4.5:1); icons are graphical
        objects under 1.4.11 (3:1). See visual.md for why the two differ.
        """
        return [
            ("rótulo 'Open' sobre botão elevado", self.window_fg,
             self.raised_bg, 4.5, "texto"),
            ("ícone de gravação sobre o vermelho", self.destructive_fg,
             self.destructive, 3.0, "glifo"),
            ("ícone de reprodução sobre o verde", self.success_fg,
             self.success, 3.0, "glifo"),
            ("ícone neutro sobre hover", self.window_fg,
             self.hover, 3.0, "glifo"),
            ("ícone neutro em repouso, sobre a janela", self.window_fg,
             self.window_bg, 3.0, "glifo"),
            ("loop ligado sobre o acento", self.accent_fg,
             self.accent, 3.0, "glifo"),
            ("texto do menu sobre o popover", self.window_fg,
             self.popover_bg, 4.5, "texto"),
        ]


_DEFAULT = None


def default_palette():
    """The process-wide palette. Built once so gsettings runs once."""
    global _DEFAULT
    if _DEFAULT is None:
        _DEFAULT = Palette()
    return _DEFAULT
