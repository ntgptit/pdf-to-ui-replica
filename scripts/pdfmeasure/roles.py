"""Names the shapes of a page by what they look like, from a JSON rule file, so a PDF's template can be read without a structure tree.

A PDF made for print carries no tags: a card is "a stroked rounded rectangle, grey, 1.2 pt, 427 x 527". Each rule says what a role looks like;
the engine returns, per page, the shapes that match each role. The rules are the only thing that is specific to a document; see
references/config-reference.md for the schema and examples/ for a worked file.

Rule fields (all optional except `role`): kind (rect | curve | line | image | glyph), fill / stroke ("#rrggbb", "none" or "any"), linewidth,
width, height, x0, x1, top, bottom (each [min, max], null = open), sides (["left"] / ["right"]: odd PDF pages are left pages by default),
tolerance (colour distance, default 12), pages ([first, last]).
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from .colors import to_hex
from .shapes import PageInfo, Shape

Range = tuple[float | None, float | None]


@dataclass
class Rule:
    role: str
    kind: str | None = None
    fill: str | None = None
    stroke: str | None = None
    ranges: dict[str, Range] = field(default_factory=dict)
    sides: tuple[str, ...] = ()
    tolerance: int = 12
    pages: tuple[int, int] | None = None


RANGE_FIELDS = ("linewidth", "width", "height", "x0", "x1", "top", "bottom")


def load_rules(path: str) -> list[Rule]:
    rules: list[Rule] = []
    for entry in json.loads(Path(path).read_text(encoding="utf-8")):
        ranges = {name: (entry[name][0], entry[name][1]) for name in RANGE_FIELDS if name in entry}
        pages = tuple(entry["pages"]) if "pages" in entry else None
        rules.append(
            Rule(
                role=entry["role"],
                kind=entry.get("kind"),
                fill=entry.get("fill"),
                stroke=entry.get("stroke"),
                ranges=ranges,
                sides=tuple(entry.get("sides", ())),
                tolerance=entry.get("tolerance", 12),
                pages=pages,  # type: ignore[arg-type]
            )
        )
    return rules


def page_side(number: int, first: str = "left") -> str:
    """Odd PDF pages are the left pages of a spread unless the document starts on a right page (first = 'right')."""
    left = number % 2 == 1
    if first == "right":
        left = not left
    return "left" if left else "right"


def _colour_ok(wanted: str | None, actual: str | None, tolerance: int) -> bool:
    if wanted is None or wanted == "any":
        return True
    if wanted == "none":
        return actual is None
    if actual is None:
        return False
    a, b = wanted.lstrip("#"), actual.lstrip("#")
    return sum(abs(int(a[i : i + 2], 16) - int(b[i : i + 2], 16)) for i in (0, 2, 4)) <= tolerance


def _value(shape: Shape, name: str) -> float:
    if name == "linewidth":
        return shape.linewidth
    if name == "width":
        return shape.width
    if name == "height":
        return shape.height
    return {"x0": shape.x0, "x1": shape.x1, "top": shape.top, "bottom": shape.bottom}[name]


def matches(rule: Rule, shape: Shape, side: str) -> bool:
    kind = shape.kind
    if rule.kind == "glyph":
        if not (kind != "image" and shape.is_glyph_sized and shape.fill is not None and shape.height > 0.8):
            return False
    elif rule.kind is not None and rule.kind != kind:
        return False
    if rule.sides and side not in rule.sides:
        return False
    if not _colour_ok(rule.fill, to_hex(shape.fill), rule.tolerance):
        return False
    if not _colour_ok(rule.stroke, to_hex(shape.stroke), rule.tolerance):
        return False
    for name, (low, high) in rule.ranges.items():
        value = _value(shape, name)
        if (low is not None and value < low) or (high is not None and value > high):
            return False
    return True


def extract_roles(page: PageInfo, rules: list[Rule], first_side: str = "left") -> dict[str, list[Shape]]:
    """Role name -> the shapes of the page that match its rules, ordered top to bottom then left to right."""
    side = page_side(page.number, first_side)
    found: dict[str, list[Shape]] = {}
    for rule in rules:
        if rule.pages is not None and not (rule.pages[0] <= page.number <= rule.pages[1]):
            continue
        for shape in page.shapes:
            if matches(rule, shape, side):
                found.setdefault(rule.role, []).append(shape)
    for shapes in found.values():
        shapes.sort(key=lambda item: (round(item.top, 1), item.x0))
    return found


def describe(found: dict[str, list[Shape]]) -> dict:
    return {role: [shape.describe() for shape in shapes] for role, shapes in found.items()}
