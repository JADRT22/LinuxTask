# -*- coding: utf-8 -*-
"""
LinuxTask - patch_ui.py
Description: Rewrites the toolbar labels of the staged main.py into ASCII for
             the AppImage bundle (the bundled Tk build has no symbol fonts).
             Used by tools/appimage/build.sh; kept as a module so the unit
             tests can assert every anchor against the real src/main.py
             instead of trusting a heredoc nobody checks.
Author: JADRT22 (https://github.com/JADRT22)
License: MIT
"""

import re
import sys

# ASCII toolbar labels: (source pattern, replacement). Anchored on the
# argument form the widgets are built with, so a label that disappears from
# main.py fails the build loudly rather than shipping a box of tofu glyphs.
ASCII_SUBS = [
    ('("●",', '("REC",'),
    ('("▶",', '("PLAY",'),
    ('("↻",', '("LOOP",'),
    ('text="⚙"', 'text="SET"'),
    ('text="▶"', 'text="PLAY"'),
    ('text="■"', 'text="STOP"'),
    ('text="●"', 'text="REC"'),
    # toggle_loop() repaints the loop button with the glyph, so the state
    # change needed a rule of its own: without it the button went back to
    # tofu on the first click (the creation-time rule above only covers
    # buttons_cfg).
    ('text="↻"', 'text="LOOP"'),
]

# The button whose font has to be lowered so the word labels fit the 32px
# row. Matched permissively ("...10)" plus whatever keyword arguments follow)
# because the line grew a width= when Open/Save got wider than the icons;
# an exact-substring anchor here rotted once already and the build died at
# staging with no test to catch it.
FONT_ANCHOR = re.compile(
    r'(?P<indent>[ \t]*)self\.btns\[1\]\.configure\('
    r'font=\("DejaVu Sans", 10\)[^\n]*\n'
)


def patch_source(src):
    """Returns `src` with ASCII labels and the smaller button font.

    Raises ValueError naming the pattern that is missing, so a UI edit and
    its staged copy cannot drift apart in silence.
    """
    for old, new in ASCII_SUBS:
        if old not in src:
            raise ValueError("label pattern not found in main.py: %s" % old)
        src = src.replace(old, new)

    match = FONT_ANCHOR.search(src)
    if not match:
        raise ValueError(
            "font anchor not found in main.py: self.btns[1].configure("
            "font=(\"DejaVu Sans\", 10)...)")
    indent = match.group('indent')
    extra = ("%sfor b in self.btns[2:5]:\n"
             "%s    b.configure(font=(\"DejaVu Sans\", 10))\n"
             % (indent, indent))
    return src[:match.end()] + extra + src[match.end():]


def main(path):
    with open(path, encoding="utf-8") as fp:
        source = fp.read()
    patched = patch_source(source)
    with open(path, "w", encoding="utf-8") as fp:
        fp.write(patched)
    print("staged + patched OK")
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("usage: patch_ui.py <path to staged linuxtask_main.py>",
              file=sys.stderr)
        sys.exit(2)
    try:
        sys.exit(main(sys.argv[1]))
    except ValueError as exc:
        print("ERROR: %s" % exc, file=sys.stderr)
        sys.exit(1)
