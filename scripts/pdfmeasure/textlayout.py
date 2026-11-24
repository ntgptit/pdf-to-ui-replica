"""Page-wide text layout check: every text line of the PDF against every text line of the rebuilt page, on rasters at the same zoom.

Why: line spacing and left indents decide whether a book looks right. Part-by-part checks only cover the blocks somebody declared; this one
scans the whole page (or the declared regions), so no text block is skipped. For every matched line it compares the left edge (margin, indent,
hanging number), the top and bottom, and the pitch to the line above in the same column; unmatched lines are listed.

Ink to ink, so it does not depend on the DOM or on the typeface. With the same text on both sides the line count and positions must agree
within tolerances. With different text (fixtures) lines do not correspond and the check cannot be used: skip it with a reason.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass

import numpy as np

from . import zoom as zoom_module
from .textmetrics import text_mask

DEFAULTS = {"tolerance_left": 0.5, "tolerance_vertical": 0.5, "tolerance_pitch": 0.3, "gap_pt": 3.5, "min_height_pt": 3.5, "max_height_pt": 34.0, "min_width_pt": 3.0, "max_problems": 60}


@dataclass
class Seg:
    x0: float
    x1: float
    top: float
    bottom: float

    @property
    def centre(self) -> float:
        return (self.top + self.bottom) / 2


def ink_mask(image: np.ndarray, colours: list[str] | None = None) -> np.ndarray:
    mask = text_mask(image, "text")
    for colour in colours or []:
        mask = mask | zoom_module.mask_of(image, colour)
    return mask


def segments(image: np.ndarray, zoom: int, cfg: dict | None = None) -> list[Seg]:
    """Text line segments: ink grouped into runs on one line (letters and words closer than `gap_pt`), as boxes in points. A frame or picture is too tall or too thin to count."""
    settings = {**DEFAULTS, **(cfg or {})}
    mask = ink_mask(image, settings.get("colours"))
    rows, cols = -(-mask.shape[0] // zoom), -(-mask.shape[1] // zoom)
    padded = np.zeros((rows * zoom, cols * zoom), dtype=bool)
    padded[: mask.shape[0], : mask.shape[1]] = mask
    cells = padded.reshape(rows, zoom, cols, zoom).any(axis=(1, 3))
    gap = int(round(settings["gap_pt"]))
    cumulative = np.cumsum(np.pad(cells, ((0, 0), (gap + 1, gap)), constant_values=False).astype(np.int32), axis=1)
    hot = (cumulative[:, 2 * gap + 1 :] - cumulative[:, : -(2 * gap + 1)]) > 0 if gap else cells
    seen = np.zeros_like(hot)
    found: list[Seg] = []
    for r0, c0 in zip(*np.where(hot)):
        if seen[r0, c0]:
            continue
        queue, members = deque([(r0, c0)]), []
        seen[r0, c0] = True
        while queue:
            r, c = queue.popleft()
            members.append((r, c))
            for dr, dc in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                rr, cc = r + dr, c + dc
                if 0 <= rr < rows and 0 <= cc < cols and hot[rr, cc] and not seen[rr, cc]:
                    seen[rr, cc] = True
                    queue.append((rr, cc))
        rs, cs = [m[0] for m in members], [m[1] for m in members]
        y0, y1, x0, x1 = min(rs) * zoom, (max(rs) + 1) * zoom, min(cs) * zoom, (max(cs) + 1) * zoom
        sub = mask[y0:y1, x0:x1]
        if not sub.any():
            continue
        ys, xs = np.where(sub)
        seg = Seg((x0 + xs.min()) / zoom, (x0 + xs.max() + 1) / zoom, (y0 + ys.min()) / zoom, (y0 + ys.max() + 1) / zoom)
        height, width = seg.bottom - seg.top, seg.x1 - seg.x0
        if height < settings["min_height_pt"] or height > settings["max_height_pt"] or width < settings["min_width_pt"]:
            continue
        found.append(seg)
    return sorted(found, key=lambda s: (round(s.top), s.x0))


def in_regions(segs: list[Seg], regions: list[list[float]] | None) -> list[Seg]:
    if not regions:
        return segs
    return [s for s in segs if any(x <= s.x0 <= x + w and y <= s.centre <= y + h for x, y, w, h in regions)]


def match(pdf: list[Seg], react: list[Seg], reach_pt: float = 10.0) -> tuple[list[tuple[Seg, Seg]], list[Seg], list[Seg]]:
    """Pair each PDF line with the nearest unused React line (by centre and left edge). Returns pairs, PDF lines without a partner, React lines without one."""
    free = list(react)
    pairs: list[tuple[Seg, Seg]] = []
    only_pdf: list[Seg] = []
    for p in pdf:
        best, best_cost = None, None
        for r in free:
            dy, dx = abs(r.centre - p.centre), abs(r.x0 - p.x0)
            if dy > reach_pt or dx > 60:
                continue
            cost = dy * 3 + dx
            if best_cost is None or cost < best_cost:
                best, best_cost = r, cost
        if best is None:
            only_pdf.append(p)
            continue
        free.remove(best)
        pairs.append((p, best))
    return pairs, only_pdf, free


def compare(pdf: list[Seg], react: list[Seg], cfg: dict | None = None) -> dict:
    settings = {**DEFAULTS, **(cfg or {})}
    regions = settings.get("regions")
    pdf, react = in_regions(pdf, regions), in_regions(react, regions)
    pairs, only_pdf, only_react = match(pdf, react)
    problems: list[str] = []
    worst = {"left": 0.0, "top": 0.0, "bottom": 0.0, "pitch": 0.0}
    for p, r in pairs:
        for label, delta, tolerance in (("left edge", r.x0 - p.x0, settings["tolerance_left"]), ("top", r.top - p.top, settings["tolerance_vertical"]), ("bottom", r.bottom - p.bottom, settings["tolerance_vertical"])):
            key = label.split()[0]
            worst[key] = max(worst[key], abs(delta))
            if abs(delta) > tolerance:
                problems.append(f"line at ({p.x0:.1f}, {p.top:.1f}) pt: {label} off by {delta:+.2f} pt (allowed {tolerance})")
    ordered = sorted(pairs, key=lambda pair: pair[0].centre)
    for index, (p2, r2) in enumerate(ordered):
        above = [(p1, r1) for p1, r1 in ordered[:index] if min(p1.x1, p2.x1) - max(p1.x0, p2.x0) > 0.5 * min(p1.x1 - p1.x0, p2.x1 - p2.x0) and 0 < p2.centre - p1.centre < 60]
        if not above:
            continue
        p1, r1 = above[-1]
        delta = (r2.centre - r1.centre) - (p2.centre - p1.centre)
        worst["pitch"] = max(worst["pitch"], abs(delta))
        if abs(delta) > settings["tolerance_pitch"]:
            problems.append(f"line spacing at ({p2.x0:.1f}, {p2.top:.1f}) pt: pitch to the line above is {r2.centre - r1.centre:.2f} pt, the PDF has {p2.centre - p1.centre:.2f} (off {delta:+.2f}, allowed {settings['tolerance_pitch']})")
    for s in only_pdf:
        problems.append(f"line only in the PDF at ({s.x0:.1f}, {s.top:.1f}) pt, {s.x1 - s.x0:.0f} wide: missing or misplaced in the rebuilt page")
    for s in only_react:
        problems.append(f"line only in the rebuilt page at ({s.x0:.1f}, {s.top:.1f}) pt, {s.x1 - s.x0:.0f} wide: extra or misplaced")
    cap = settings["max_problems"]
    return {"pdf_lines": len(pdf), "react_lines": len(react), "matched": len(pairs), "worst": {k: round(v, 2) for k, v in worst.items()}, "problems": problems[:cap], "more": max(0, len(problems) - cap), "ok": not problems and bool(pdf), "empty": not pdf}


def to_markdown(title: str, result: dict) -> str:
    lines = [f"## {title}", ""]
    if result["empty"]:
        return "\n".join(lines + ["**No text lines found in the PDF region: nothing was verified.** Check the regions and the ink colours.", ""])
    lines.append(f"{result['matched']} of {result['pdf_lines']} PDF lines matched ({result['react_lines']} lines in the rebuilt page). Worst differences (pt): left {result['worst']['left']}, top {result['worst']['top']}, bottom {result['worst']['bottom']}, line pitch {result['worst']['pitch']}.")
    lines.append("")
    lines += [f"- **off:** {problem}" for problem in result["problems"]] or ["- every line within tolerance"]
    if result["more"]:
        lines.append(f"- ... and {result['more']} more")
    lines.append("")
    return "\n".join(lines)
