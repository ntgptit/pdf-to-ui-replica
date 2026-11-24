"""Rebuilds text lines from glyph outlines. This PDF has no text layer (letters are curves), so lines are found by grouping small shapes."""
from __future__ import annotations

from dataclasses import dataclass

from .colors import Rgb, to_hex
from .shapes import PageInfo, Shape


@dataclass(frozen=True)
class TextLine:
    page: int
    x0: float
    x1: float
    top: float  # top of the tallest glyph
    bottom: float  # lowest glyph edge
    baseline: float  # robust bottom: median of glyph bottoms (descenders and punctuation do not move it)
    glyphs: int
    fill: Rgb | None
    typical_height: float  # median glyph height

    def describe(self) -> dict:
        return {
            "page": self.page,
            "x0": round(self.x0, 1),
            "x1": round(self.x1, 1),
            "top": round(self.top, 1),
            "bottom": round(self.bottom, 1),
            "baseline": round(self.baseline, 1),
            "glyphs": self.glyphs,
            "fill": to_hex(self.fill),
            "typical_height_pt": round(self.typical_height, 2),
        }


def _median(values: list[float]) -> float:
    ordered = sorted(values)
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[middle]
    return (ordered[middle - 1] + ordered[middle]) / 2


def glyphs_of(page: PageInfo) -> list[Shape]:
    """Glyph-sized filled shapes: letters, digits and punctuation."""
    return [shape for shape in page.shapes if shape.kind != "image" and shape.is_glyph_sized and shape.fill is not None and shape.height > 0.8]


def _merge_overlapping(rows: list[list[Shape]]) -> list[list[Shape]]:
    """Merges rows whose vertical spans overlap by more than half a point: they are one line split by a long final consonant or a descender."""
    ordered = sorted(rows, key=lambda row: min(item.top for item in row))
    merged: list[list[Shape]] = []
    for row in ordered:
        top = min(item.top for item in row)
        if merged and top < max(item.bottom for item in merged[-1]) - 0.5:
            merged[-1].extend(row)
            continue
        merged.append(list(row))
    return merged


def text_lines(page: PageInfo, min_overlap: float = 0.5) -> list[TextLine]:
    """Groups glyphs into lines by vertical overlap: a glyph joins the line whose vertical span it overlaps by at least `min_overlap`
    of the glyph's own height. A Hangul syllable is several outlines (initial, vowel, final) that all overlap its row."""
    glyphs = sorted(glyphs_of(page), key=lambda shape: (shape.top, shape.x0))
    rows: list[list[Shape]] = []
    spans: list[list[float]] = []
    for glyph in glyphs:
        for index, (top, bottom) in enumerate(spans):
            overlap = min(bottom, glyph.bottom) - max(top, glyph.top)
            if overlap >= min_overlap * glyph.height:
                rows[index].append(glyph)
                spans[index] = [min(top, glyph.top), max(bottom, glyph.bottom)]
                break
        else:
            rows.append([glyph])
            spans.append([glyph.top, glyph.bottom])
    rows = _merge_overlapping(rows)
    lines: list[TextLine] = []
    for row in rows:
        if len(row) < 2:
            continue
        heights = [item.height for item in row]
        bottoms = [item.bottom for item in row]
        colours = [item.fill for item in row]
        lines.append(
            TextLine(
                page=page.number,
                x0=min(item.x0 for item in row),
                x1=max(item.x1 for item in row),
                top=min(item.top for item in row),
                bottom=max(bottoms),
                baseline=_median(bottoms),
                glyphs=len(row),
                fill=max(set(colours), key=colours.count),
                typical_height=_median(heights),
            )
        )
    return sorted(lines, key=lambda line: (line.top, line.x0))
