# -*- coding: utf-8 -*-
"""
LinuxTask - ui_widgets.py
Description: The two widgets the toolbar is built from, drawn in code.
             AdwButton and AdwMenu paint themselves into a Tk canvas with a
             small supersampled rasteriser, so the toolbar needs no PNG, no
             icon font and no second toolkit, and it looks the same whether
             Tk found a scalable font or only a bitmap one.
Author: JADRT22 (https://github.com/JADRT22)
License: MIT

Why a rasteriser instead of create_polygon: Tk has no anti-aliasing, and an
un-anti-aliased 6px corner is exactly what makes a Tk toolbar read as "not a
GTK app" at a glance. Each shape is evaluated as a signed predicate and its
coverage is sampled on an SS x SS grid per pixel, then composited in Python
over the surface colour. The result is one RGB raster handed to PhotoImage,
so the edges are smooth at 1x and at 2x, and the whole thing is still code --
no asset file, nothing to keep in sync with the palette.

Glyph -> icon mapping is what lets the AppImage patch keep working: a text
value that names a glyph is drawn as a vector, and anything else ("REC",
"PLAY", "Open", "Save") is drawn as a label. tools/appimage/patch_ui.py
rewrites those glyph strings to ASCII at staging time, so the bundled
bitmap-font build lands on the label path automatically.
"""

from __future__ import annotations

import math
import tkinter as tk
from tkinter import font as tkfont

from ui_theme import Palette

# How many samples per pixel edge. 3 is enough to hide stair-stepping at
# 6px radii and stays cheap: one 32x32 button is ~9k predicate calls.
SS = 3

# Rendered rasters, keyed by everything that changes a pixel. The toolbar
# asks for the same idle image on every start-up and the same hover image on
# every mouse-over, so this cache is what keeps hover from costing a redraw.
_IMAGE_CACHE = {}


# ---------------------------------------------------------------- primitives
#
# Each shape is a callable with a `bounds` box. The box is what makes the
# rasteriser affordable: sampling a shape over the whole canvas costs a
# thousand times more than sampling it over the dozen pixels it occupies, and
# a gear is eleven shapes. `bounds` is also what keeps start-up under the
# frame budget -- the first toolbar paint is the only thing on the clock.

class _Shape:
    __slots__ = ("bounds",)

    def __call__(self, x, y):
        raise NotImplementedError


class _Rect(_Shape):
    __slots__ = ("x0", "y0", "x1", "y1")

    def __init__(self, x0, y0, x1, y1):
        self.x0, self.y0, self.x1, self.y1 = x0, y0, x1, y1
        self.bounds = (x0, y0, x1, y1)

    def __call__(self, x, y):
        return self.x0 <= x <= self.x1 and self.y0 <= y <= self.y1


def _rect(x0, y0, x1, y1):
    return _Rect(x0, y0, x1, y1)


class _RoundRect(_Shape):
    __slots__ = ("x0", "y0", "x1", "y1", "r", "cx0", "cx1", "cy0", "cy1")

    def __init__(self, x0, y0, x1, y1, r):
        self.x0, self.y0, self.x1, self.y1 = x0, y0, x1, y1
        self.r = max(0.0, min(r, (x1 - x0) / 2.0, (y1 - y0) / 2.0))
        self.cx0, self.cx1 = x0 + self.r, x1 - self.r
        self.cy0, self.cy1 = y0 + self.r, y1 - self.r
        self.bounds = (x0, y0, x1, y1)

    def __call__(self, x, y):
        if self.x0 <= x <= self.x1 and self.cy0 <= y <= self.cy1:
            return True
        if self.cx0 <= x <= self.cx1 and self.y0 <= y <= self.y1:
            return True
        px = self.cx0 if x < self.cx0 else self.cx1
        py = self.cy0 if y < self.cy0 else self.cy1
        return (x - px) ** 2 + (y - py) ** 2 <= self.r * self.r


def _rrect(x0, y0, x1, y1, r):
    """Rounded-rectangle predicate, corner arcs included."""
    return _RoundRect(x0, y0, x1, y1, r)


class _Circle(_Shape):
    __slots__ = ("cx", "cy", "r2")

    def __init__(self, cx, cy, r):
        self.cx, self.cy, self.r2 = cx, cy, r * r
        self.bounds = (cx - r, cy - r, cx + r, cy + r)

    def __call__(self, x, y):
        return (x - self.cx) ** 2 + (y - self.cy) ** 2 <= self.r2


def _circle(cx, cy, r):
    return _Circle(cx, cy, r)


class _Ring(_Shape):
    __slots__ = ("cx", "cy", "r2", "ir2")

    def __init__(self, cx, cy, r, thickness):
        self.cx, self.cy = cx, cy
        self.r2 = r * r
        self.ir2 = max(0.0, r - thickness) ** 2
        self.bounds = (cx - r, cy - r, cx + r, cy + r)

    def __call__(self, x, y):
        d = (x - self.cx) ** 2 + (y - self.cy) ** 2
        return self.ir2 <= d <= self.r2


def _ring(cx, cy, r, thickness):
    return _Ring(cx, cy, r, thickness)


class _Capsule(_Shape):
    __slots__ = ("x0", "y0", "dx", "dy", "len2", "half2")

    def __init__(self, x0, y0, x1, y1, w):
        self.x0, self.y0 = x0, y0
        self.dx, self.dy = x1 - x0, y1 - y0
        self.len2 = self.dx * self.dx + self.dy * self.dy
        half = w / 2.0
        self.half2 = half * half
        self.bounds = (min(x0, x1) - half, min(y0, y1) - half,
                       max(x0, x1) + half, max(y0, y1) + half)

    def __call__(self, x, y):
        if self.len2 == 0:
            return (x - self.x0) ** 2 + (y - self.y0) ** 2 <= self.half2
        t = ((x - self.x0) * self.dx + (y - self.y0) * self.dy) / self.len2
        t = 0.0 if t < 0 else (1.0 if t > 1 else t)
        px = self.x0 + t * self.dx - x
        py = self.y0 + t * self.dy - y
        return px * px + py * py <= self.half2


def _capsule(x0, y0, x1, y1, w):
    """Thick line segment with round caps."""
    return _Capsule(x0, y0, x1, y1, w)


class _Polygon(_Shape):
    __slots__ = ("points",)

    def __init__(self, points):
        self.points = tuple(points)
        xs = [p[0] for p in self.points]
        ys = [p[1] for p in self.points]
        self.bounds = (min(xs), min(ys), max(xs), max(ys))

    def __call__(self, x, y):
        hit = False
        points = self.points
        n = len(points)
        for i in range(n):
            x0, y0 = points[i]
            x1, y1 = points[(i + 1) % n]
            if (y0 > y) != (y1 > y):
                span_x = x0 + (y - y0) * (x1 - x0) / (y1 - y0)
                if x < span_x:
                    hit = not hit
        return hit


def _polygon(points):
    """Even-odd fill for a closed polygon."""
    return _Polygon(points)


# --------------------------------------------------------------------- icons
#
# Each painter receives the icon box size in device pixels and returns a list
# of predicates expressed in the widget's own pixel space, already centred.

def _icon_shapes(name, w, h, size):
    cx, cy = w / 2.0, h / 2.0
    u = size / 16.0          # 16px design grid, scaled
    if name == "record":
        return [_circle(cx, cy, 5.2 * u)]
    if name == "stop":
        return [_rrect(cx - 4.6 * u, cy - 4.6 * u,
                       cx + 4.6 * u, cy + 4.6 * u, 1.4 * u)]
    if name == "play":
        return [_polygon([(cx - 4.2 * u, cy - 6.2 * u),
                          (cx - 4.2 * u, cy + 6.2 * u),
                          (cx + 6.6 * u, cy)])]
    if name == "loop":
        # Ring with a gap at the upper-right, plus one arrowhead closing it:
        # the silhouette of GTK's view-refresh-symbolic at this size. The
        # ring is drawn as four arc segments so the gap stays visible -- a
        # full ring with a triangle on top just reads as a blob.
        shapes = []
        gap_from, gap_to = -0.95, -0.35     # radians, right-hand side
        span = 2.0 * math.pi - (gap_to - gap_from)
        steps = 10
        for index in range(steps):
            a0 = gap_to + span * index / steps
            a1 = gap_to + span * (index + 1) / steps
            shapes.append(_capsule(
                cx + math.cos(a0) * 5.3 * u, cy + math.sin(a0) * 5.3 * u,
                cx + math.cos(a1) * 5.3 * u, cy + math.sin(a1) * 5.3 * u,
                1.9 * u))
        tip_x = cx + math.cos(gap_to) * 5.3 * u
        tip_y = cy + math.sin(gap_to) * 5.3 * u
        shapes.append(_polygon([
            (tip_x, tip_y - 3.0 * u),
            (tip_x + 2.6 * u, tip_y + 0.6 * u),
            (tip_x - 1.4 * u, tip_y + 2.2 * u),
        ]))
        return shapes
    if name == "gear":
        shapes = [_ring(cx, cy, 5.0 * u, 1.8 * u), _circle(cx, cy, 1.5 * u)]
        for step in range(8):
            angle = step * math.pi / 4.0
            x0 = cx + math.cos(angle) * 3.4 * u
            y0 = cy + math.sin(angle) * 3.4 * u
            x1 = cx + math.cos(angle) * 6.1 * u
            y1 = cy + math.sin(angle) * 6.1 * u
            shapes.append(_capsule(x0, y0, x1, y1, 2.1 * u))
        return shapes
    if name == "chevron":
        # A shallow V reads as a slash at 16px; this one is as deep as it is
        # wide, which is what makes the "opens a menu" affordance legible.
        return [_capsule(cx - 4.0 * u, cy - 2.2 * u, cx, cy + 2.4 * u, 1.9 * u),
                _capsule(cx, cy + 2.4 * u, cx + 4.0 * u, cy - 2.2 * u, 1.9 * u)]
    return []


# ------------------------------------------------------------------ renderer

def _solid_span(pred):
    """Columns of a wide rounded rectangle that are covered edge to edge.

    Between the two corner arcs a rounded rectangle is a plain box, so every
    pixel there is fully covered and does not need to be sampled. A settings
    row is 264px wide with a 6px radius: skipping its middle takes the render
    from 108ms to a few, which is the difference between a window that appears
    and one that hesitates.
    """
    if not isinstance(pred, _RoundRect) or pred.r < 1:
        return None
    if (pred.x1 - pred.x0) <= 4 * pred.r:
        return None
    lo = int(math.ceil(pred.x0 + pred.r))
    hi = int(math.floor(pred.x1 - pred.r))
    return (lo, hi) if hi > lo else None


def _coverage(w, h, preds, ss):
    """Samples each shape on an ss x ss grid, inside its own bounds only."""
    masks = [bytearray(w * h) for _ in preds]
    offsets = [(i + 0.5) / ss for i in range(ss)]
    total = ss * ss
    for k, pred in enumerate(preds):
        bounds = getattr(pred, "bounds", None)
        if bounds is None:
            x0, y0, x1, y1 = 0, 0, w, h
        else:
            x0, y0, x1, y1 = bounds
        # One pixel of slack on every side: the sample grid sits inside the
        # pixel, so a shape that ends at 5.0 can still cover pixel 5.
        x0 = max(0, int(x0) - 1)
        y0 = max(0, int(y0) - 1)
        x1 = min(w, int(x1) + 2)
        y1 = min(h, int(y1) + 2)
        mask = masks[k]

        span = _solid_span(pred)
        solid_lo = max(x0, span[0]) if span else x1
        solid_hi = min(x1, span[1]) if span else x1
        fill = bytes([total]) * max(0, solid_hi - solid_lo)

        for y in range(y0, y1):
            row = y * w
            if solid_hi > solid_lo:
                mask[row + solid_lo:row + solid_hi] = fill
            for x in list(range(x0, solid_lo)) + list(range(solid_hi, x1)):
                hits = 0
                for ox in offsets:
                    px = x + ox
                    for oy in offsets:
                        if pred(px, y + oy):
                            hits += 1
                if hits:
                    mask[row + x] = hits
    return masks


# Colour -> "#rrggbb". A flat surface repeats one colour across thousands of
# pixels, so the formatting is done once per distinct colour instead of once
# per pixel.
_HEX_CACHE = {}


def _encode(buf, w, h):
    """Turns a flat [(r,g,b), ...] buffer into the string PhotoImage.put eats."""
    cache = _HEX_CACHE
    rows = []
    for y in range(h):
        base = y * w
        parts = []
        for x in range(w):
            channel = buf[base + x]
            key = (int(channel[0] + 0.5) & 255,
                   int(channel[1] + 0.5) & 255,
                   int(channel[2] + 0.5) & 255)
            text = cache.get(key)
            if text is None:
                text = "#%02x%02x%02x" % key
                cache[key] = text
            parts.append(text)
        rows.append("{" + " ".join(parts) + "}")
    return " ".join(rows)


def _render(w, h, bg_hex, layers):
    """Composites [(pred, color_hex), ...] over bg_hex and returns a PhotoImage.

    Layers are painted in order with their own edge coverage, which is what
    keeps an icon from having a hard 1px outline against its hover fill.
    """
    from ui_theme import hex_to_rgb
    bg = hex_to_rgb(bg_hex)
    buf = [list(bg) for _ in range(w * h)]
    total = float(SS * SS)
    # One scan for every layer: sampling per layer instead multiplies the
    # cost by the number of shapes, and a gear is eleven of them.
    masks = _coverage(w, h, [pred for pred, _ in layers], SS)
    for (_pred, color_hex), hits_by_pixel in zip(layers, masks, strict=True):
        color = hex_to_rgb(color_hex)
        # Entries are never mutated in place: a fully covered pixel shares the
        # layer's list, so mutating it would smear one colour across the run.
        solid = [color[0], color[1], color[2]]
        for idx, hits in enumerate(hits_by_pixel):
            if not hits:
                continue
            if hits == total:
                buf[idx] = solid
                continue
            a = hits / total
            px = buf[idx]
            buf[idx] = [px[0] + (color[0] - px[0]) * a,
                        px[1] + (color[1] - px[1]) * a,
                        px[2] + (color[2] - px[2]) * a]
    img = tk.PhotoImage(width=w, height=h)
    img.put(_encode(buf, w, h))
    return img


class _Shifted(_Shape):
    __slots__ = ("shape", "dx", "dy")

    def __init__(self, shape, dx, dy):
        self.shape, self.dx, self.dy = shape, dx, dy
        b = shape.bounds
        self.bounds = (b[0] + dx, b[1] + dy, b[2] + dx, b[3] + dy)

    def __call__(self, x, y):
        return self.shape(x - self.dx, y - self.dy)


def _shifted(shape, dx, dy):
    """Moves a shape's sample space, so icons can be placed off-centre."""
    return _Shifted(shape, dx, dy)


def _glyph_icon(text):
    """Maps a button label to an icon name, or None for a text label."""
    return {
        "●": "record",
        "■": "stop",
        "▶": "play",
        "↻": "loop",
        "⚙": "gear",
    }.get(text)


# -------------------------------------------------------------------- button

class AdwButton(tk.Canvas):
    """A flat Adwaita toolbar button, painted per state.

    The public surface mirrors what main.py, recorder.py and playback.py
    already call -- `configure(text=..., fg_color=...)` and `.grid()` -- so
    swapping the widget class does not move any call site, and
    tools/appimage/patch_ui.py keeps finding its literal anchors.
    """

    def __init__(self, master, text="", width=32, height=32, font=None,
                 fg_color=None, hover_color=None, command=None, scale=1.0,
                 palette=None, raised=False, **kwargs):
        self._palette = palette or Palette()
        self._scale = scale
        self._text = text
        self._font = font
        self._command = command
        self._fill = self._normalise(fg_color)
        self._hover_fill = self._normalise(hover_color)
        self._raised = raised
        self._hovered = False
        self._pressed = False
        self._enabled = True
        self._px_w = int(round(width * scale))
        self._px_h = int(round(height * scale))
        self._image = None

        tk.Canvas.__init__(
            self, master, width=self._px_w, height=self._px_h,
            highlightthickness=0, bd=0, takefocus=0,
            bg=self._palette.window_bg,
            **{k: v for k, v in kwargs.items()
               if k not in ("corner_radius", "border_width", "border_color")})

        self._item = self.create_image(0, 0, anchor="nw")
        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)
        self.bind("<ButtonPress-1>", self._on_press)
        self.bind("<ButtonRelease-1>", self._on_release)
        self._redraw()

    # -- compatibility helpers -------------------------------------------

    @staticmethod
    def _normalise(color):
        """Accepts CTk's 'transparent' and its light/dark colour pairs."""
        if color is None:
            return None
        if isinstance(color, (list, tuple)):
            color = color[0]
        if str(color).lower() in ("transparent", ""):
            return None
        return color

    def configure(self, **kwargs):
        redraw = False
        for key, value in kwargs.items():
            if key == "text":
                self._text = value
                redraw = True
            elif key == "fg_color":
                self._fill = self._normalise(value)
                redraw = True
            elif key == "hover_color":
                self._hover_fill = self._normalise(value)
                redraw = True
            elif key == "font":
                self._font = value
                redraw = True
            elif key == "command":
                self._command = value
            elif key == "state":
                self._enabled = str(value) != "disabled"
                redraw = True
            elif key == "width":
                self._px_w = int(round(float(value) * self._scale))
                tk.Canvas.configure(self, width=self._px_w)
                redraw = True
            elif key == "height":
                self._px_h = int(round(float(value) * self._scale))
                tk.Canvas.configure(self, height=self._px_h)
                redraw = True
            elif key == "raised":
                self._raised = bool(value)
                redraw = True
            else:
                tk.Canvas.configure(self, **{key: value})
        if redraw:
            self._redraw()
        return self

    config = configure

    def cget(self, key):
        if key == "text":
            return self._text
        if key == "fg_color":
            return self._fill
        if key == "width":
            return self._px_w
        return tk.Canvas.cget(self, key)

    # -- state -----------------------------------------------------------

    def _on_enter(self, _event=None):
        self._hovered = True
        self._redraw()

    def _on_leave(self, _event=None):
        self._hovered = False
        self._pressed = False
        self._redraw()

    def _on_press(self, _event=None):
        if not self._enabled:
            return
        self._pressed = True
        self._redraw()

    def _on_release(self, _event=None):
        if not self._enabled:
            return
        was_pressed = self._pressed
        self._pressed = False
        self._redraw()
        if was_pressed and self._command is not None:
            self._command()

    # -- painting --------------------------------------------------------

    def _surface(self):
        """The button's background for the current state."""
        if self._fill is not None:
            if self._pressed:
                return self._mix(self._fill, self._palette.window_fg, 0.14)
            if self._hovered and self._hover_fill:
                return self._hover_fill
            if self._hovered:
                return self._mix(self._fill, self._palette.window_fg, 0.07)
            return self._fill
        if not self._enabled:
            # A disabled button keeps its shape and loses its contrast, which
            # is what Adwaita's `filter: opacity(30%)` amounts to -- dropping
            # the fill entirely made the button disappear instead.
            return self._palette.raised_bg if self._raised \
                else self._palette.window_bg
        if self._pressed:
            return self._palette.active
        if self._hovered:
            return self._palette.hover
        if self._raised:
            return self._palette.raised_bg
        return self._palette.window_bg

    @staticmethod
    def _mix(a, b, t):
        from ui_theme import hex_to_rgb, rgb_to_hex
        ca, cb = hex_to_rgb(a), hex_to_rgb(b)
        return rgb_to_hex(tuple(x + (y - x) * t for x, y in zip(ca, cb, strict=True)))

    def _icon_color(self):
        if self._fill is not None:
            # Filled states carry their own foreground: white on the
            # destructive/success/accent tokens, which is what Adwaita does.
            return self._palette.window_fg
        if self._enabled:
            return self._palette.window_fg
        return self._palette.dim

    def _redraw(self):
        surface = self._surface()
        icon = _glyph_icon(self._text)
        label = "" if icon else self._text
        color = self._icon_color()
        key = (icon, label, surface, color, self._px_w, self._px_h, self._scale,
               tuple(self._font) if isinstance(self._font, (list, tuple))
               else self._font, self._enabled)

        image = _IMAGE_CACHE.get(key)
        if image is None:
            layers = []
            rounded = _rrect(0.5, 0.5, self._px_w - 0.5, self._px_h - 0.5,
                             self._palette.radius * self._scale)
            if surface != self._palette.window_bg:
                layers.append((rounded, surface))
            if self._raised and self._fill is None:
                border = _rrect(0.5, 0.5, self._px_w - 0.5, self._px_h - 0.5,
                                self._palette.radius * self._scale)
                layers.append((border, self._palette.border))
                inner = _rrect(0.5 + self._palette.border_width,
                               0.5 + self._palette.border_width,
                               self._px_w - 0.5 - self._palette.border_width,
                               self._px_h - 0.5 - self._palette.border_width,
                               self._palette.radius * self._scale)
                layers.insert(0, (inner, surface))
            if icon:
                box = 16.0 * self._scale
                for shape in _icon_shapes(icon, self._px_w, self._px_h, box):
                    layers.append((shape, color))
            image = _render(self._px_w, self._px_h, self._palette.window_bg, layers)
            _IMAGE_CACHE[key] = image
            # Fill-only layers are cheap; labels are drawn by Tk below.
        self._image = image
        self.itemconfigure(self._item, image=image)
        for tag in ("label",):
            self.delete(tag)
        if label:
            self.create_text(
                self._px_w / 2.0, self._px_h / 2.0, text=label, fill=color,
                font=("DejaVu Sans", self._label_size(label)),
                anchor="center", tags=("label",))

    def _label_size(self, label):
        """Largest font size at which `label` still fits inside the outline.

        A canvas does not clip its text, so without this an AppImage build
        (whose staged labels are REC/PLAY/LOOP/SET instead of glyphs) would
        spill words over the neighbouring buttons. Tk's own measurement is
        used rather than an estimate, so the result holds for any font the
        desktop resolves.
        """
        family = "DejaVu Sans"
        size = 10
        if isinstance(self._font, (list, tuple)) and len(self._font) > 1:
            family, size = self._font[0], int(self._font[1])
        size = int(round(size * self._scale))
        limit = self._px_w - 4 * self._scale
        measurement = tkfont.Font(family=family, size=size)
        while size > 6 and measurement.measure(label) > limit:
            size -= 1
            measurement.configure(size=size)
        return size


# ---------------------------------------------------------------------- menu

class AdwMenu(tk.Canvas):
    """Adwaita dropdown: a flat chevron button plus a popover of choices.

    Only the API main.py uses is implemented (`variable`, `values`, `get`,
    `set`, `grid`, `configure`), so the speed selector keeps driving the same
    StringVar and the same Tcl trace.
    """

    def __init__(self, master, values, variable, width=56, height=28,
                 scale=1.0, palette=None, command=None, **kwargs):
        self._palette = palette or Palette()
        self._scale = scale
        self._variable = variable
        self._values = list(values)
        self._command = command
        self._px_w = int(round(width * scale))
        self._px_h = int(round(height * scale))
        self._hovered = False
        self._popup = None
        self._image = None

        tk.Canvas.__init__(
            self, master, width=self._px_w, height=self._px_h,
            highlightthickness=0, bd=0, takefocus=0,
            bg=self._palette.window_bg,
            **{k: v for k, v in kwargs.items()
               if k not in ("font", "fg_color", "button_color",
                            "button_hover_color", "dropdown_fg_color",
                            "dropdown_hover_color")})

        self._item = self.create_image(0, 0, anchor="nw")
        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)
        self.bind("<Button-1>", self._toggle)
        self._draw(False)

    # -- API used by main.py ---------------------------------------------

    def get(self):
        return self._variable.get()

    def set(self, value):
        self._variable.set(value)
        self._draw(self._hovered)

    def configure(self, **kwargs):
        if "values" in kwargs:
            self._values = list(kwargs.pop("values"))
        if "width" in kwargs:
            self._px_w = int(round(float(kwargs.pop("width")) * self._scale))
            tk.Canvas.configure(self, width=self._px_w)
        if "height" in kwargs:
            self._px_h = int(round(float(kwargs.pop("height")) * self._scale))
            tk.Canvas.configure(self, height=self._px_h)
        if "command" in kwargs:
            self._command = kwargs.pop("command")
        for key in ("fg_color", "button_color", "button_hover_color",
                    "dropdown_fg_color", "dropdown_hover_color", "font",
                    "variable"):
            kwargs.pop(key, None)
        if kwargs:
            tk.Canvas.configure(self, **kwargs)
        self._draw(self._hovered)
        return self

    config = configure

    # -- painting --------------------------------------------------------

    def _draw(self, hovered, opened=False):
        surface = self._palette.hover if (hovered or opened) \
            else self._palette.raised_bg
        key = ("menu", surface, self._px_w, self._px_h, self._scale)
        image = _IMAGE_CACHE.get(key)
        if image is None:
            r = self._palette.radius * self._scale
            outer = _rrect(0.5, 0.5, self._px_w - 0.5, self._px_h - 0.5, r)
            inner = _rrect(1.5, 1.5, self._px_w - 1.5, self._px_h - 1.5,
                           max(0.0, r - 1))
            layers = [(outer, self._palette.border), (inner, surface)]
            # The chevron belongs in the same raster as the fill: painting it
            # as a second image would lay an opaque rectangle over the button.
            shift = self._px_w - 10 * self._scale - self._px_w / 2.0
            for shape in _icon_shapes("chevron", self._px_w, self._px_h,
                                      16.0 * self._scale):
                layers.append((_shifted(shape, shift, 0.0),
                               self._palette.window_fg))
            image = _render(self._px_w, self._px_h, self._palette.window_bg, layers)
            _IMAGE_CACHE[key] = image
        self._image = image
        self.itemconfigure(self._item, image=image)

        self.delete("label")
        self.create_text(
            (self._px_w - 18 * self._scale) / 2.0, self._px_h / 2.0,
            text=self._variable.get(), fill=self._palette.window_fg,
            font=("DejaVu Sans", int(round(9 * self._scale))),
            anchor="center", tags=("label",))

    # -- popover ---------------------------------------------------------

    def _on_enter(self, _event=None):
        self._hovered = True
        self._draw(True)

    def _on_leave(self, _event=None):
        self._hovered = False
        self._draw(False)

    def _toggle(self, _event=None):
        if self._popup is not None:
            self._close()
            return
        self._draw(True, opened=True)
        rows = len(self._values)
        row_h = int(round(28 * self._scale))
        pad = int(round(6 * self._scale))
        width = max(self._px_w, int(round(96 * self._scale)))
        height = rows * row_h + pad * 2

        popup = tk.Toplevel(self)
        popup.overrideredirect(True)
        popup.configure(bg=self._palette.window_bg)
        popup.geometry("+%d+%d" % (self.winfo_rootx(),
                                   self.winfo_rooty() + self._px_h + 2))
        shell = tk.Canvas(popup, width=width, height=height,
                          highlightthickness=0, bd=0,
                          bg=self._palette.window_bg)
        shell.pack()
        body = _rrect(0, 0, width - 1, height - 1,
                      self._palette.popover_radius * self._scale)
        shell_image = _render(width, height, self._palette.window_bg,
                              [(body, self._palette.popover_bg)])
        shell.create_image(0, 0, anchor="nw", image=shell_image)
        shell.shell_image = shell_image

        for index, value in enumerate(self._values):
            row = tk.Label(
                shell, text=value, anchor="w", padx=int(round(14 * self._scale)),
                bg=self._palette.popover_bg, fg=self._palette.window_fg,
                font=("DejaVu Sans", int(round(10 * self._scale))))
            row.place(x=0, y=pad + index * row_h, width=width, height=row_h)
            row.bind("<Button-1>",
                     lambda _e, v=value: self._choose(v))
            row.bind("<Enter>", lambda _e, r=row: r.configure(
                bg=self._palette.hover))
            row.bind("<Leave>", lambda _e, r=row: r.configure(
                bg=self._palette.popover_bg))

        popup.bind("<FocusOut>", lambda _e: self._close())
        popup.bind("<Escape>", lambda _e: self._close())
        popup.focus_set()
        self._popup = popup

    def _choose(self, value):
        self._variable.set(value)
        if self._command is not None:
            self._command(value)
        self._close()

    def _close(self):
        if self._popup is not None:
            try:
                self._popup.destroy()
            except tk.TclError:
                pass
            self._popup = None
        self._draw(self._hovered)


# ------------------------------------------------------------ settings rows

class AdwRow(tk.Canvas):
    """One Adwaita preference row: a title on the left, a key chip on the right.

    The whole row is the click target, the way a libadwaita action row is.
    `configure(text=...)` accepts "Record: F8" and splits it, because
    recorder.py and start_mapping() already talk to this widget in that
    shape -- keeping the call sites untouched keeps the mixins independent
    of the widget toolkit.
    """

    def __init__(self, master, text="", command=None, height=34, scale=1.0,
                 palette=None, raised=True, **kwargs):
        self._palette = palette or Palette()
        self._scale = scale
        self._text = text
        self._command = command
        self._fill = None
        self._raised = raised
        self._hovered = False
        self._enabled = True
        self._px_h = int(round(height * scale))
        self._px_w = 1
        self._image = None

        tk.Canvas.__init__(self, master, width=200, height=self._px_h,
                           highlightthickness=0, bd=0, takefocus=0,
                           bg=self._palette.window_bg, **kwargs)
        self.bind("<Configure>", self._on_configure)
        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)
        self.bind("<ButtonRelease-1>", self._on_release)
        self.configure(height=self._px_h)

    def _on_configure(self, event=None):
        width = (event.width if event is not None else self.winfo_width())
        if width > 1 and width != self._px_w:
            self._px_w = width
            self._redraw()

    def configure(self, **kwargs):
        if "text" in kwargs:
            self._text = kwargs.pop("text")
        if "fg_color" in kwargs:
            value = kwargs.pop("fg_color")
            if isinstance(value, (list, tuple)):
                value = value[0]
            self._fill = (None if str(value).lower() in ("transparent", "none", "")
                          else value)
        if "state" in kwargs:
            self._enabled = str(kwargs.pop("state")) != "disabled"
        if "command" in kwargs:
            self._command = kwargs.pop("command")
        if "height" in kwargs:
            self._px_h = int(round(float(kwargs.pop("height")) * self._scale))
            tk.Canvas.configure(self, height=self._px_h)
        if "raised" in kwargs:
            self._raised = bool(kwargs.pop("raised"))
        if kwargs:
            tk.Canvas.configure(self, **kwargs)
        self._redraw()
        return self

    config = configure

    def cget(self, key):
        if key == "text":
            return self._text
        return tk.Canvas.cget(self, key)

    # -- interaction -----------------------------------------------------

    def _on_enter(self, _event=None):
        self._hovered = True
        self._redraw()

    def _on_leave(self, _event=None):
        self._hovered = False
        self._redraw()

    def _on_release(self, _event=None):
        if self._enabled and self._command is not None:
            self._command()

    # -- painting --------------------------------------------------------

    def _split(self):
        """'Record: F8' -> ('Record', 'F8'); 'Press any key...' -> (text, '')."""
        title, sep, value = self._text.partition(": ")
        return (title, value) if sep else (self._text, "")

    def _redraw(self):
        if self._px_w <= 1:
            return
        palette = self._palette
        title, value = self._split()
        radius = palette.radius * self._scale
        if self._fill is not None:
            surface = self._fill
            title_color = palette.window_fg
        elif self._hovered and self._enabled:
            surface = palette.hover
            title_color = palette.window_fg
        else:
            surface = palette.raised_bg
            title_color = palette.window_fg if self._enabled else palette.dim
        chip_color = palette.window_fg if self._enabled else palette.dim

        size = int(round(10 * self._scale))
        measurement = tkfont.Font(family="DejaVu Sans", size=size)
        chip_w = 0
        if value:
            chip_w = measurement.measure(value) + int(round(16 * self._scale))
        key = ("row", title, value, surface, title_color, chip_color,
               self._px_w, self._px_h, self._enabled, chip_w)
        image = _IMAGE_CACHE.get(key)
        if image is None:
            layers = [(_rrect(0.5, 0.5, self._px_w - 0.5, self._px_h - 0.5, radius),
                       surface)]
            if self._raised and self._fill is None:
                layers.append((_rrect(0.5, 0.5, self._px_w - 0.5,
                                      self._px_h - 0.5, radius), palette.border))
                layers.append((_rrect(1.5, 1.5, self._px_w - 1.5,
                                      self._px_h - 1.5,
                                      max(0.0, radius - 1)), surface))
            if chip_w:
                pad = int(round(6 * self._scale))
                chip_h = self._px_h - 2 * pad
                layers.append((_rrect(self._px_w - chip_w - pad, pad,
                                      self._px_w - pad, pad + chip_h,
                                      max(2.0, radius - 1)),
                               palette.active))
            image = _render(self._px_w, self._px_h, palette.window_bg, layers)
            _IMAGE_CACHE[key] = image
        self._image = image
        self.delete("all")
        self.create_image(0, 0, anchor="nw", image=image)
        self.create_text(int(round(12 * self._scale)), self._px_h / 2.0,
                         text=title, anchor="w", fill=title_color,
                         font=("DejaVu Sans", size))
        if value:
            pad = int(round(6 * self._scale))
            self.create_text(self._px_w - chip_w - pad + chip_w / 2.0,
                             self._px_h / 2.0, text=value, anchor="center",
                             fill=chip_color, font=("DejaVu Sans", size))


class AdwSwitch(tk.Canvas):
    """Adwaita switch bound to a BooleanVar; toggles on click."""

    def __init__(self, master, variable, command=None, width=44, height=26,
                 scale=1.0, palette=None, **kwargs):
        self._palette = palette or Palette()
        self._scale = scale
        self._variable = variable
        self._command = command
        self._px_w = int(round(width * scale))
        self._px_h = int(round(height * scale))
        self._image = None

        tk.Canvas.__init__(self, master, width=self._px_w, height=self._px_h,
                           highlightthickness=0, bd=0, takefocus=0,
                           bg=self._palette.window_bg,
                           **{k: v for k, v in kwargs.items()
                              if k not in ("text", "onvalue", "offvalue")})
        self.bind("<Button-1>", self._toggle)
        variable.trace_add("write", lambda *_: self._draw())
        self._draw()

    def _toggle(self, _event=None):
        self._variable.set(not bool(self._variable.get()))
        if self._command is not None:
            self._command()

    def _draw(self):
        palette = self._palette
        on = bool(self._variable.get())
        key = ("switch", on, self._px_w, self._px_h, self._scale)
        image = _IMAGE_CACHE.get(key)
        if image is None:
            radius = self._px_h / 2.0
            track = _rrect(0.5, 0.5, self._px_w - 0.5, self._px_h - 0.5, radius)
            # 3px of margin around the knob, like the libadwaita switch, so
            # the knob never touches the track's rounded end.
            margin = 3 * self._scale
            knob_r = radius - margin
            knob_cx = (self._px_w - margin - knob_r if on
                       else margin + knob_r)
            layers = [(track, palette.accent if on else palette.track),
                      (_circle(knob_cx, self._px_h / 2.0, knob_r),
                       palette.window_fg)]
            image = _render(self._px_w, self._px_h, palette.window_bg, layers)
            _IMAGE_CACHE[key] = image
        self._image = image
        self.delete("all")
        self.create_image(0, 0, anchor="nw", image=image)


class AdwProgress(tk.Canvas):
    """Adwaita progress bar: 6px track, accent fill, rounded ends."""

    def __init__(self, master, height=6, scale=1.0, palette=None, **kwargs):
        self._palette = palette or Palette()
        self._scale = scale
        self._px_h = int(round(height * scale))
        self._px_w = 1
        self._value = 0.0
        self._image = None

        tk.Canvas.__init__(self, master, width=200, height=self._px_h,
                           highlightthickness=0, bd=0, takefocus=0,
                           bg=self._palette.window_bg, **kwargs)
        self.bind("<Configure>", self._on_configure)

    def _on_configure(self, event=None):
        width = (event.width if event is not None else self.winfo_width())
        if width > 1 and width != self._px_w:
            self._px_w = width
            self._draw()

    def set(self, value):
        self._value = max(0.0, min(1.0, float(value)))
        self._draw()

    def get(self):
        return self._value

    def _draw(self):
        if self._px_w <= 1:
            return
        palette = self._palette
        radius = self._px_h / 2.0
        key = ("progress", round(self._value, 3), self._px_w, self._px_h,
               self._scale)
        image = _IMAGE_CACHE.get(key)
        if image is None:
            layers = [(_rrect(0, 0, self._px_w, self._px_h, radius),
                       palette.track)]
            filled = self._px_w * self._value
            if filled > 1:
                layers.append((_rrect(0, 0, max(filled, self._px_h), self._px_h,
                                      radius), palette.accent))
            image = _render(self._px_w, self._px_h, palette.window_bg, layers)
            _IMAGE_CACHE[key] = image
        self._image = image
        self.delete("all")
        self.create_image(0, 0, anchor="nw", image=image)
