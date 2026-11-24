"""Invariants of a template across pages: for each quantity (a role's edge, size, radius, stroke width) its min, max, median and spread.

A spread near zero across many pages means the quantity belongs to the page template (a margin, a header height, a stroke width) and can become a token.
Quantities come from a JSON file: [{name, role, field, pick: first | last | all, sides: both | left | right}].
"""
from __future__ import annotations

import json
import statistics
from pathlib import Path

from .roles import Rule, extract_roles, page_side
from .shapes import PageInfo, Shape

FIELDS = ("x0", "x1", "top", "bottom", "width", "height", "cx", "cy", "radius", "linewidth")


def field_value(shape: Shape, name: str) -> float | None:
    if name == "cx":
        return (shape.x0 + shape.x1) / 2
    if name == "cy":
        return (shape.top + shape.bottom) / 2
    if name == "radius":
        return shape.corner_radius
    return {"x0": shape.x0, "x1": shape.x1, "top": shape.top, "bottom": shape.bottom, "width": shape.width, "height": shape.height, "linewidth": shape.linewidth}[name]


def load_quantities(path: str) -> list[dict]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def invariants(pages: list[PageInfo], rules: list[Rule], quantities: list[dict], first_side: str = "left") -> list[dict]:
    per_page = [(page, page_side(page.number, first_side), extract_roles(page, rules, first_side)) for page in pages]
    rows: list[dict] = []
    for quantity in quantities:
        values: list[float] = []
        for page, side, found in per_page:
            wanted = quantity.get("sides", "both")
            if wanted != "both" and wanted != side:
                continue
            shapes = found.get(quantity["role"], [])
            if not shapes:
                continue
            pick = quantity.get("pick", "first")
            chosen = shapes if pick == "all" else [shapes[0] if pick == "first" else shapes[-1]]
            for shape in chosen:
                value = field_value(shape, quantity["field"])
                if value is not None:
                    values.append(value)
        if not values:
            continue
        rows.append(
            {
                "name": quantity["name"],
                "count": len(values),
                "min": round(min(values), 2),
                "max": round(max(values), 2),
                "median": round(statistics.median(values), 2),
                "spread": round(max(values) - min(values), 2),
            }
        )
    return rows


def to_markdown(rows: list[dict], title: str, source: str) -> str:
    lines = [
        f"# {title}",
        "",
        f"Generated from {source}. Units: PDF points (1 pt = 1/72 inch = 0.3528 mm). A spread near 0 across pages means the quantity belongs to the page template.",
        "",
        "| Quantity | Samples | Median | Min | Max | Spread |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for row in rows:
        lines.append(f"| {row['name']} | {row['count']} | {row['median']} | {row['min']} | {row['max']} | {row['spread']} |")
    lines.append("")
    return "\n".join(lines)
