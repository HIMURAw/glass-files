"""(Copy of ~/.local/src/mor-theme/tema.py.) Colour themes for the whole desktop: one palette, every part recoloured from its violet original.

The sources stay violet (the original Mor look). Each part runs its colours through recolor():
colours in the violet family turn to the chosen theme's hue (or to grey); everything else (white
text, red warnings, green status, the Harvis robot) is left alone. The JS twin is theme.js in
each extension, and glassfiles/tint.py in Glass Files; keep the three identical.

The chosen theme lives in ~/.config/tema/current.json; the extensions and Glass Files watch it.
"""
import colorsys
import json
import os
import re
from pathlib import Path

CONFIG = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "tema" / "current.json"
BASE_HUE = 258  # the original violet

# hue: degrees; sat: saturation factor (0 = greyscale); lum: lightness factor for accent colours,
# so white text stays readable on light hues like turquoise; icon_hue: Papirus folders/apps.
THEMES = {
    "turkuaz": {"hue": 183, "sat": 1.0, "lum": 0.70, "accent": "teal", "label": "Turquoise"},
    "yesil": {"hue": 150, "sat": 0.85, "lum": 0.70, "accent": "green", "label": "Green"},
    "mavi": {"hue": 215, "sat": 1.0, "lum": 0.90, "accent": "blue", "label": "Blue"},
    "mor": {"hue": 258, "sat": 1.0, "lum": 1.0, "accent": "purple", "label": "Violet"},
    "gri": {"hue": 0, "sat": 0.0, "lum": 0.85, "accent": "slate", "label": "Grey"},
}
ALIASES = {"turquoise": "turkuaz", "green": "yesil", "yeşil": "yesil", "blue": "mavi", "purple": "mor",
           "violet": "mor", "grey": "gri", "gray": "gri", "siyah": "gri", "beyaz": "gri", "mono": "gri"}


def current():
    try:
        p = json.loads(CONFIG.read_text())
        return {**THEMES[p["name"]], "name": p["name"]}
    except (OSError, ValueError, KeyError):
        return {**THEMES["mor"], "name": "mor"}


def recolor(r, g, b, p=None):
    """0..255 in, 0..255 out."""
    p = p or current()
    if p["name"] == "mor":
        return r, g, b
    h, l, s = colorsys.rgb_to_hls(r / 255, g / 255, b / 255)
    deg = h * 360
    if s < 0.08 or not 225 <= deg <= 300:
        return r, g, b
    accent = s >= 0.3 and 0.35 <= l <= 0.85
    if p["sat"] == 0:
        s2, h2 = 0.0, h
    else:
        h2 = ((deg + p["hue"] - BASE_HUE) % 360) / 360
        s2 = min(1.0, s * p["sat"])
    l2 = l * p["lum"] if accent else l
    return tuple(round(c * 255) for c in colorsys.hls_to_rgb(h2, l2, s2))


_HEX = re.compile(r"#([0-9a-fA-F]{6}|[0-9a-fA-F]{3})\b")
_RGBA = re.compile(r"rgba?\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*(,\s*[\d.]+\s*)?\)")


def recolor_css(text, p=None):
    p = p or current()
    if p["name"] == "mor":
        return text

    def hex_(m):
        v = m.group(1)
        if len(v) == 3:
            v = "".join(c * 2 for c in v)
        r, g, b = recolor(*(int(v[i:i + 2], 16) for i in (0, 2, 4)), p)
        return f"#{r:02x}{g:02x}{b:02x}"

    def rgba(m):
        r, g, b = recolor(int(m.group(1)), int(m.group(2)), int(m.group(3)), p)
        a = m.group(4)
        return f"rgba({r}, {g}, {b}{a.rstrip()})" if a else f"rgb({r}, {g}, {b})"
    return _RGBA.sub(rgba, _HEX.sub(hex_, text))
