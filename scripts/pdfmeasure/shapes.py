"""Reads the vector shapes and images of a PDF page into plain records, in PDF points (1 pt = 1/72 inch)."""
from __future__ import annotations

from dataclasses import dataclass, field

from .colors import Rgb, to_hex, to_rgb

MM_PER_PT = 25.4 / 72


@dataclass(frozen=True)
class Shape:
    kind: str  # rect | curve | line | image
    page: int  # 1-based PDF page number
    x0: float
    top: float
    x1: float
    bottom: float
    fill: Rgb | None = None
    stroke: Rgb | None = None
    linewidth: float = 0.0
    points: int = 0
    raw_fill: tuple[float, ...] | None = None
    raw_stroke: tuple[float, ...] | None = None
    source_size: tuple[int, int] | None = None  # images: pixel size of the bitmap
    path: tuple = ()  # curves and rects: pdfplumber path segments, e.g. ('c', (x, y), (x, y), (x, y))

    @property
    def width(self) -> float:
        return self.x1 - self.x0

    @property
    def height(self) -> float:
        return self.bottom - self.top

    @property
    def corner_radius(self) -> float | None:
        """Radius of the first rounded corner of a rounded rectangle (the first curve segment's extent), None for shapes without one."""
        previous: tuple[float, float] | None = None
        for segment in self.path:
            command, points = segment[0], segment[1:]
            if command == "c" and previous is not None:
                end = points[-1]
                return round(max(abs(end[0] - previous[0]), abs(end[1] - previous[1])), 2)
            if points:
                previous = points[-1]
        return None

    @property
    def is_glyph_sized(self) -> bool:
        """True for the small outlines a text line is made of (this PDF has no text layer, letters are curves)."""
        return self.width < 25 and self.height < 25

    def describe(self) -> dict:
        return {
            "kind": self.kind,
            "page": self.page,
            "bbox_pt": [round(self.x0, 2), round(self.top, 2), round(self.x1, 2), round(self.bottom, 2)],
            "size_pt": [round(self.width, 2), round(self.height, 2)],
            "size_mm": [round(self.width * MM_PER_PT, 2), round(self.height * MM_PER_PT, 2)],
            "fill": to_hex(self.fill),
            "stroke": to_hex(self.stroke),
            "linewidth_pt": round(self.linewidth, 3),
            "points": self.points,
            "raw_fill": list(self.raw_fill) if self.raw_fill else None,
            "raw_stroke": list(self.raw_stroke) if self.raw_stroke else None,
            "source_size": list(self.source_size) if self.source_size else None,
            "corner_radius_pt": self.corner_radius,
        }


def _raw(color: object) -> tuple[float, ...] | None:
    if color is None:
        return None
    if isinstance(color, (int, float)):
        return (float(color),)
    return tuple(float(value) for value in color)


def page_shapes(page, page_number: int) -> list[Shape]:
    """Every rect, curve, line and image of a pdfplumber page, with resolved colours."""
    shapes: list[Shape] = []
    for kind in ("rects", "curves", "lines"):
        for obj in getattr(page, kind):
            filled = bool(obj.get("fill"))
            stroked = bool(obj.get("stroke"))
            fill_raw = _raw(obj.get("non_stroking_color")) if filled else None
            stroke_raw = _raw(obj.get("stroking_color")) if stroked else None
            shapes.append(
                Shape(
                    kind=kind[:-1],
                    page=page_number,
                    x0=obj["x0"],
                    top=obj["top"],
                    x1=obj["x1"],
                    bottom=obj["bottom"],
                    fill=to_rgb(fill_raw),
                    stroke=to_rgb(stroke_raw),
                    linewidth=float(obj.get("linewidth") or 0.0) if stroked else 0.0,
                    points=len(obj.get("pts", [])),
                    path=tuple(tuple(segment) for segment in obj.get("path", [])),
                    raw_fill=fill_raw,
                    raw_stroke=stroke_raw,
                )
            )
    for image in page.images:
        size = image.get("srcsize")
        shapes.append(
            Shape(
                kind="image",
                page=page_number,
                x0=image["x0"],
                top=image["top"],
                x1=image["x1"],
                bottom=image["bottom"],
                source_size=(int(size[0]), int(size[1])) if size else None,
            )
        )
    return shapes


@dataclass
class PageInfo:
    number: int
    width: float
    height: float
    shapes: list[Shape] = field(default_factory=list)

    @property
    def structural(self) -> list[Shape]:
        """Shapes that are not glyph-sized (frames, rules, fills, bitmaps)."""
        return [shape for shape in self.shapes if not shape.is_glyph_sized]


def read_pages(pdf_path: str, pages: list[int]) -> list[PageInfo]:
    import pdfplumber

    infos: list[PageInfo] = []
    with pdfplumber.open(pdf_path) as pdf:
        for number in pages:
            page = pdf.pages[number - 1]
            infos.append(PageInfo(number, float(page.width), float(page.height), page_shapes(page, number)))
    return infos
