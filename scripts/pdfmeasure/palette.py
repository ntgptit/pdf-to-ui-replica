"""Writes the colours of a PDF as CSS custom properties, read from the shapes that carry them (never typed in).

A role with `"palette": "--var-name"` (and optionally `"palette_from": "fill" | "stroke"`, default fill for filled shapes else stroke) contributes
one variable: the colour of the first shape that matches. A role that matches nothing makes the command fail, so a palette cannot drift from the PDF.
Text colours: a `glyph` role with a fill rule gives the colour of the lettering (glyph shapes are filled outlines in an outlined-text PDF).
"""
from __future__ import annotations

import json
from pathlib import Path

from .colors import to_hex
from .roles import extract_roles
from .shapes import PageInfo


def measured_colours(pages: list[PageInfo], rules_path: str, first_side: str = "left") -> dict[str, str]:
    from .roles import load_rules

    entries = json.loads(Path(rules_path).read_text(encoding="utf-8"))
    rules = load_rules(rules_path)
    wanted = {entry["role"]: entry for entry in entries if "palette" in entry}
    colours: dict[str, str] = {}
    for page in pages:
        found = extract_roles(page, rules, first_side)
        for role, entry in wanted.items():
            variable = entry["palette"]
            if variable in colours or role not in found:
                continue
            shape = found[role][0]
            source = entry.get("palette_from")
            colour = to_hex(shape.stroke if source == "stroke" or (source is None and shape.fill is None) else shape.fill)
            if colour is not None:
                colours[variable] = colour
    missing = sorted({entry["palette"] for entry in wanted.values()} - set(colours))
    if missing:
        raise SystemExit(f"palette: no shape matched the roles of {', '.join(missing)} in the measured pages")
    return colours


def palette_css(colours: dict[str, str], selector: str, header: str) -> str:
    lines = [f"/* {header} */", f"{selector} {{"]
    lines.extend(f"  {name}: {value};" for name, value in sorted(colours.items()))
    lines.append("}")
    return "\n".join(lines) + "\n"
