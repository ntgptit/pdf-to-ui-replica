"""Geometry and colour of a rebuilt page against the PDF, from a JSON list of checks.

Each check names a PDF side (a role from roles.json and a field) and a DOM side (an element carrying the `data-*` attribute measure-dom.cjs reads,
and a field), with a tolerance in points. The DOM is read in CSS pixels and divided by the sheet's pixels per point, so both sides are in points.

  {"name": "card top", "pdf": {"role": "card", "field": "top"}, "dom": {"id": "card", "field": "y"}, "tolerance": 0.6}
  {"name": "frame stroke", "expect": 0.46, "dom": {"id": "word-bank", "path": "frame.strokeWidth", "unit": "px"}, "tolerance": 0.03}
  {"name": "tab colour", "expect": "#45a665", "dom": {"id": "tab", "path": "style.background", "unit": "colour"}}

PDF fields: x0, x1, top, bottom, width, height, cx, cy, radius, linewidth. DOM fields: x, y, w, h, right, bottom, cx, cy (all of the box). `path` reads a
dotted path into the element's measured record instead (style.*, frame.*, rule.*); `unit: px` divides by the scale, `unit: colour` turns rgb() into hex.
`index` picks the n-th element or shape (default 0); `pdf.offset_from` / `dom.offset_from` subtract another role's field (position inside a parent).
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

from .report import field_value
from .roles import Rule, extract_roles
from .shapes import PageInfo


@dataclass
class Metric:
    name: str
    pdf: float | str
    lab: float | str
    tolerance: float

    @property
    def delta(self) -> float | None:
        if isinstance(self.pdf, str) or isinstance(self.lab, str):
            return None
        return self.lab - self.pdf  # exact: rounding happens only when the report is written

    @property
    def ok(self) -> bool:
        if self.delta is None:
            return self.pdf == self.lab
        return abs(self.delta) <= self.tolerance


class Dom:
    """The elements of one measured sheet, addressed in points."""

    def __init__(self, directory: str):
        data = json.loads((Path(directory) / "dom.json").read_text(encoding="utf-8"))
        self.elements: list[dict] = data["elements"]
        self.dpr: float = data["dpr"]
        self.scale: float = data["sheet"]["w"] / data["page_width_pt"]

    def element(self, identifier: str, index: int = 0) -> dict:
        found = [element for element in self.elements if element["role"] == identifier]
        if len(found) <= index:
            raise SystemExit(f"compare: the page has no element #{index} with the id \"{identifier}\"")
        return found[index]

    def box_field(self, element: dict, name: str) -> float:
        x, y, w, h = (element[key] / self.scale for key in ("x", "y", "w", "h"))
        return {"x": x, "y": y, "w": w, "h": h, "right": x + w, "bottom": y + h, "cx": x + w / 2, "cy": y + h / 2}[name]

    def path_value(self, element: dict, path: str, unit: str | None):
        node = element
        for part in path.split("."):
            node = node.get(part) if isinstance(node, dict) else None
            if node is None:
                return None
        if unit == "px":
            return float(node) / self.scale
        if unit == "colour":
            match = re.match(r"rgba?\((\d+),\s*(\d+),\s*(\d+)", str(node))
            return "#{:02x}{:02x}{:02x}".format(*(int(v) for v in match.groups())) if match else str(node)
        return node


def _round(value):
    return value if isinstance(value, str) else round(value, 2)


def run_checks(checks: list[dict], page: PageInfo, rules: list[Rule], dom: Dom, first_side: str = "left") -> list[Metric]:
    if not checks:
        raise SystemExit("compare: no checks, so nothing would be verified")
    found = extract_roles(page, rules, first_side)

    def pdf_value(spec: dict) -> float:
        shapes = found.get(spec["role"], [])
        index = spec.get("index", 0)
        if len(shapes) <= index:
            raise SystemExit(f"compare: PDF page {page.number} has no shape #{index} for the role \"{spec['role']}\"")
        value = field_value(shapes[index], spec["field"])
        if value is None:
            raise SystemExit(f"compare: field {spec['field']} of role {spec['role']} is not defined")
        if "offset_from" in spec:
            parent = found[spec["offset_from"]["role"]][spec["offset_from"].get("index", 0)]
            value -= field_value(parent, spec["offset_from"]["field"]) or 0.0
        return value

    def dom_value(spec: dict):
        element = dom.element(spec["id"], spec.get("index", 0))
        if "path" in spec:
            return dom.path_value(element, spec["path"], spec.get("unit"))
        value = dom.box_field(element, spec["field"])
        if "offset_from" in spec:
            parent = dom.element(spec["offset_from"]["id"], spec["offset_from"].get("index", 0))
            value -= dom.box_field(parent, spec["offset_from"]["field"])
        return value

    metrics: list[Metric] = []
    for check in checks:
        expected = check["expect"] if "expect" in check else pdf_value(check["pdf"])
        actual = dom_value(check["dom"])
        if actual is None:
            raise SystemExit(f"compare: \"{check['name']}\" is not measurable on the page")
        metrics.append(Metric(check["name"], expected, actual, check.get("tolerance", 0.6)))  # raw values: only the report rounds
    return metrics


def to_markdown(title: str, metrics: list[Metric]) -> str:
    bad = [metric for metric in metrics if not metric.ok]
    lines = [f"## {title}", "", f"{len(metrics) - len(bad)} of {len(metrics)} metrics within tolerance.", "", "| Metric | PDF | Rebuilt | Delta | Tolerance | |", "|---|---:|---:|---:|---:|:--:|"]
    for metric in metrics:
        delta = "" if metric.delta is None else f"{metric.delta:+.2f}"
        lines.append(f"| {metric.name} | {_round(metric.pdf)} | {_round(metric.lab)} | {delta} | ±{metric.tolerance} | {'ok' if metric.ok else '**off**'} |")
    lines.append("")
    return "\n".join(lines)
