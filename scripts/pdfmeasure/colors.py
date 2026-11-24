"""Colour conversion for PDF fill and stroke colours.

PDF shapes carry DeviceGray, DeviceRGB or DeviceCMYK values. Poppler renders CMYK through a fixed 16-corner interpolation, not the naive
`(1-c)(1-k)` formula, so a green of CMYK (0.75, 0.15, 0.75, 0) renders as a muted green. This module uses the same interpolation, so the
numbers match what a PDF reader shows (checked against sampled render pixels in `cli.py check-colors`).
"""
from __future__ import annotations

# Corner colours of the CMYK cube as (c, m, y, k) -> (r, g, b); from poppler's GfxDeviceCMYKColorSpace.
_CORNERS: dict[tuple[int, int, int, int], tuple[float, float, float]] = {
    (0, 0, 0, 0): (1.0, 1.0, 1.0),
    (0, 0, 0, 1): (0.1373, 0.1216, 0.1255),
    (0, 0, 1, 0): (1.0, 0.9490, 0.0),
    (0, 0, 1, 1): (0.1098, 0.1020, 0.0),
    (0, 1, 0, 0): (0.9255, 0.0, 0.5490),
    (0, 1, 0, 1): (0.1412, 0.0, 0.0),
    (0, 1, 1, 0): (0.9294, 0.1098, 0.1412),
    (0, 1, 1, 1): (0.1333, 0.0, 0.0),
    (1, 0, 0, 0): (0.0, 0.6784, 0.9373),
    (1, 0, 0, 1): (0.0, 0.0588, 0.1412),
    (1, 0, 1, 0): (0.0, 0.6510, 0.3137),
    (1, 0, 1, 1): (0.0, 0.0745, 0.0),
    (1, 1, 0, 0): (0.1804, 0.1922, 0.5725),
    (1, 1, 0, 1): (0.0, 0.0, 0.0078),
    (1, 1, 1, 0): (0.2118, 0.2119, 0.2235),
    (1, 1, 1, 1): (0.0, 0.0, 0.0),
}

Rgb = tuple[int, int, int]


def cmyk_to_rgb(c: float, m: float, y: float, k: float) -> Rgb:
    """CMYK in 0..1 to sRGB 0..255 with the 16-corner interpolation."""
    channels = [0.0, 0.0, 0.0]
    for corner, rgb in _CORNERS.items():
        weight = 1.0
        for value, bit in zip((c, m, y, k), corner):
            weight *= value if bit else 1.0 - value
        for index in range(3):
            channels[index] += rgb[index] * weight
    return tuple(max(0, min(255, round(channel * 255))) for channel in channels)  # type: ignore[return-value]


def to_rgb(color: object) -> Rgb | None:
    """A pdfplumber colour (number, 1/3/4 tuple) to sRGB; None when absent."""
    if color is None:
        return None
    if isinstance(color, (int, float)):
        gray = round(float(color) * 255)
        return (gray, gray, gray)
    values = tuple(float(value) for value in color)
    if len(values) == 1:
        gray = round(values[0] * 255)
        return (gray, gray, gray)
    if len(values) == 3:
        return tuple(round(value * 255) for value in values)  # type: ignore[return-value]
    if len(values) == 4:
        return cmyk_to_rgb(*values)
    return None


def to_hex(rgb: Rgb | None) -> str | None:
    if rgb is None:
        return None
    return "#{:02x}{:02x}{:02x}".format(*rgb)
