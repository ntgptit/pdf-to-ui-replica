"""Groups the structural shapes of many pages by look (kind, colours, line width) to find the recurring page components."""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

from .colors import to_hex
from .shapes import PageInfo, Shape


@dataclass
class Signature:
    key: tuple
    count: int = 0
    pages: set[int] = field(default_factory=set)
    examples: list[Shape] = field(default_factory=list)


def signature_key(shape: Shape) -> tuple:
    """Look of a shape without its position: kind, fill, stroke, line width, and a coarse size class."""
    width_class = "wide" if shape.width > 200 else "mid" if shape.width > 40 else "small"
    height_class = "tall" if shape.height > 200 else "mid" if shape.height > 20 else "thin"
    return (shape.kind, to_hex(shape.fill), to_hex(shape.stroke), round(shape.linewidth, 2), width_class, height_class)


def collect(pages: list[PageInfo], include_glyphs: bool = False) -> list[Signature]:
    groups: dict[tuple, Signature] = defaultdict(lambda: Signature(key=()))
    for page in pages:
        for shape in page.shapes if include_glyphs else page.structural:
            key = signature_key(shape)
            group = groups[key]
            group.key = key
            group.count += 1
            group.pages.add(page.number)
            if len(group.examples) < 3:
                group.examples.append(shape)
    return sorted(groups.values(), key=lambda item: (-len(item.pages), -item.count))


def page_ranges(pages: set[int]) -> str:
    """{9,10,11,13} -> '9-11,13'."""
    ordered = sorted(pages)
    ranges: list[str] = []
    start = previous = ordered[0]
    for number in ordered[1:] + [None]:  # type: ignore[list-item]
        if number is not None and number == previous + 1:
            previous = number
            continue
        ranges.append(str(start) if start == previous else f"{start}-{previous}")
        if number is not None:
            start = previous = number
    return ",".join(ranges)
