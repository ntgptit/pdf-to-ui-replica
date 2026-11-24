"""Typography of every text line, PDF against the rebuilt page, as match scores: size, weight, family, indent, line spacing.

Both sides are rasterised at the same zoom and measured by the same code, so it works for outlined text (no text layer) too. Lines are grouped into
styles by core height. Size, weight and family are font properties: they are scored per style from the ink of all its lines together (so the letters
of one line do not decide them). Indent and spacing are scored per line and averaged per style. The worst style and attribute decide the page:
    >= 0.95 PASS · < 0.95 WARNING · < 0.92 ERROR
What is measured (proxies, all in points, the same way on both sides):
- size: core height of the line = height of the dense ink band (rows holding at least 35 % of the densest row's ink): Hangul block height, Latin
    x-height. It hardly depends on which letters the line holds, unlike the full ink height (ascenders, descenders).
    score = 1 - |h_rebuilt - h_pdf| / h_pdf
- weight: stroke width (2 x ink area / ink perimeter, pooled) divided by the core height, so a size error is not counted twice.
    score = 1 - |w_r - w_p| / w_p
- family: stroke contrast = mean width of vertical strokes / mean thickness of horizontal strokes (gothic/sans ~1, myeongjo/serif clearly above 1),
    and the ink proportion of the line (ink area / (core height x width)). score = 1 - mean of both relative errors. A proxy, not a name: when the PDF has a
    text layer, `pdf_fonts` gives the real font name and size, and the name decides the family.
- indent: left edge difference relative to the core height (0.5 pt on a 10 pt core = 0.95). score = 1 - |dx| / h_pdf. The ink edge depends on the
    first letter's side bearing, so with different text on the two sides (fixtures, cfg `same_text: false`) indent is not scored and says so.
- spacing: pitch to the line above, between the centres of the dense bands. score = 1 - |pitch_r - pitch_p| / pitch_p
Lines that exist on one side only are not scored here; `text_layout` reports them.
"""
from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np

from . import textlayout

PASS, WARNING_BELOW, ERROR_BELOW = 0.95, 0.95, 0.92
ATTRIBUTES = ("size", "weight", "family", "indent", "spacing")
RESULT_FILE = "typography.json"
DENSE_ROW_SHARE = 0.35
STYLE_GAP = 0.08  # lines whose core heights differ by more than 8 % are different styles
MIN_ZOOM = 8  # px/pt: a 0.6 pt stroke is about 5 px; below this the stroke width is too coarse to score weight within 5 %


@dataclass
class LineMetrics:
    x0: float
    top: float
    width: float
    core_height: float  # pt, sub-pixel
    core_mid: float  # pt from the page top: the line's position for spacing, free of ascenders and descenders
    area: float  # px of ink
    perimeter: float  # px of ink edge
    across_vertical: float  # sum and count of horizontal runs crossing vertical strokes
    across_vertical_n: int
    across_horizontal: float  # sum and count of vertical runs crossing horizontal strokes
    across_horizontal_n: int
    box: float  # px: core height x width, for the ink proportion


def level(score: float) -> str:
    return "ERROR" if score < ERROR_BELOW else "WARNING" if score < WARNING_BELOW else "PASS"


def _runs(flags: np.ndarray) -> np.ndarray:
    """Lengths of the runs of True along the last axis, all rows together."""
    padded = np.pad(flags, ((0, 0), (1, 1))).astype(np.int8)
    starts, ends = np.nonzero(np.diff(padded, axis=1) == 1), np.nonzero(np.diff(padded, axis=1) == -1)
    return ends[1] - starts[1]


def _crossing(profile: np.ndarray, threshold: float, index: int, step: int) -> float:
    """Sub-pixel position where the row profile crosses `threshold` next to row `index` (step -1: before it, +1: after it)."""
    neighbour = index + step
    if neighbour < 0 or neighbour >= profile.size or profile[index] == profile[neighbour]:
        return float(index) if step < 0 else float(index + 1)
    fraction = (profile[index] - threshold) / (profile[index] - profile[neighbour])
    return index - fraction + 0.5 if step < 0 else index + fraction + 0.5


def measure(mask: np.ndarray, seg: textlayout.Seg, zoom: int) -> LineMetrics | None:
    """Raw ink sums of one line inside its box; ratios are taken per style (pooled), so the letters of one line do not decide them."""
    y0, y1, x0, x1 = int(seg.top * zoom), int(np.ceil(seg.bottom * zoom)), int(seg.x0 * zoom), int(np.ceil(seg.x1 * zoom))
    ink = mask[y0:y1, x0:x1]
    area = float(ink.sum())
    if area < 4 * zoom * zoom:
        return None
    rows = ink.sum(axis=1).astype(float)
    threshold = DENSE_ROW_SHARE * rows.max()
    dense = np.flatnonzero(rows >= threshold)
    top_px, bottom_px = _crossing(rows, threshold, int(dense[0]), -1), _crossing(rows, threshold, int(dense[-1]), +1)
    core_px = bottom_px - top_px
    padded = np.pad(ink, 1)
    inner = padded[1:-1, 1:-1] & padded[:-2, 1:-1] & padded[2:, 1:-1] & padded[1:-1, :-2] & padded[1:-1, 2:]
    limit = max(2, int(0.35 * core_px))
    horizontal, vertical = _runs(ink), _runs(ink.T)
    horizontal, vertical = horizontal[horizontal <= limit], vertical[vertical <= limit]
    return LineMetrics(
        x0=seg.x0, top=seg.top, width=seg.x1 - seg.x0, core_height=core_px / zoom, core_mid=(y0 + (top_px + bottom_px) / 2) / zoom,
        area=area, perimeter=float((ink & ~inner).sum()), across_vertical=float(horizontal.sum()), across_vertical_n=int(horizontal.size),
        across_horizontal=float(vertical.sum()), across_horizontal_n=int(vertical.size), box=core_px * ink.shape[1],
    )


def pooled(metrics: list[LineMetrics], zoom: int) -> dict:
    """Font attributes of a style from all its lines together: core height (median), weight, contrast, ink proportion."""
    core = float(np.median([m.core_height for m in metrics]))
    stroke = 2 * sum(m.area for m in metrics) / max(1.0, sum(m.perimeter for m in metrics)) / zoom
    vertical_width = sum(m.across_vertical for m in metrics) / max(1, sum(m.across_vertical_n for m in metrics))
    horizontal_thickness = sum(m.across_horizontal for m in metrics) / max(1, sum(m.across_horizontal_n for m in metrics))
    return {
        "core_height": round(core, 3), "stroke": round(stroke, 3), "weight": stroke / core if core else 0.0,
        "contrast": round(vertical_width / horizontal_thickness, 3) if horizontal_thickness else 1.0,
        "proportion": sum(m.area for m in metrics) / max(1.0, sum(m.box for m in metrics)),
    }


def _rel(rebuilt: float, pdf: float) -> float:
    return abs(rebuilt - pdf) / pdf if pdf else 0.0


def _score(error: float) -> float:
    return round(max(0.0, 1.0 - error), 4)


def compare(pdf_image: np.ndarray, react_image: np.ndarray, zoom: int, cfg: dict | None = None) -> dict:
    """Score every style (size, weight, family from pooled ink) and every matched line (indent, spacing); the worst style decides the page."""
    cfg = cfg or {}
    same_text = bool(cfg.get("same_text", True))
    pdf_mask, react_mask = textlayout.ink_mask(pdf_image, cfg.get("colours")), textlayout.ink_mask(react_image, cfg.get("colours"))
    pdf_segs = textlayout.in_regions(textlayout.segments(pdf_image, zoom, cfg), cfg.get("regions"))
    react_segs = textlayout.in_regions(textlayout.segments(react_image, zoom, cfg), cfg.get("regions"))
    pairs, only_pdf, only_react = textlayout.match(pdf_segs, react_segs)
    measured = []
    for p, r in pairs:
        mp, mr = measure(pdf_mask, p, zoom), measure(react_mask, r, zoom)
        if mp and mr:
            measured.append((p, r, mp, mr))
    measured.sort(key=lambda item: item[2].core_mid)
    lines: list[dict] = []
    for index, (p, r, mp, mr) in enumerate(measured):
        scores: dict[str, float] = {}
        if same_text:
            scores["indent"] = _score(abs(r.x0 - p.x0) / mp.core_height)
        above = [item for item in measured[:index] if min(item[0].x1, p.x1) - max(item[0].x0, p.x0) > 0.5 * min(item[0].x1 - item[0].x0, p.x1 - p.x0) and 0 < mp.core_mid - item[2].core_mid < 60]
        if above:
            pitch_pdf, pitch_rebuilt = mp.core_mid - above[-1][2].core_mid, mr.core_mid - above[-1][3].core_mid
            scores["spacing"] = _score(_rel(pitch_rebuilt, pitch_pdf))
            line_pitch = {"pdf": round(pitch_pdf, 3), "rebuilt": round(pitch_rebuilt, 3)}
        else:
            line_pitch = None
        lines.append({"pdf": asdict(mp), "rebuilt": asdict(mr), "scores": scores, "pitch": line_pitch, "style": 0.0})
    _assign_styles(lines)
    summary = []
    for style in sorted({line["style"] for line in lines}):
        members = [line for line in lines if line["style"] == style]
        pdf_font = pooled([LineMetrics(**line["pdf"]) for line in members], zoom)
        rebuilt_font = pooled([LineMetrics(**line["rebuilt"]) for line in members], zoom)
        means = {
            "size": _score(_rel(rebuilt_font["core_height"], pdf_font["core_height"])),
            "weight": _score(_rel(rebuilt_font["weight"], pdf_font["weight"])),
            "family": _score((_rel(rebuilt_font["contrast"], pdf_font["contrast"]) + _rel(rebuilt_font["proportion"], pdf_font["proportion"])) / 2),
        }
        for attr in ("indent", "spacing"):
            values = [line["scores"][attr] for line in members if attr in line["scores"]]
            if values:
                means[attr] = round(float(np.mean(values)), 4)
        pitches = [line["pitch"] for line in members if line["pitch"]]
        summary.append({
            "style": f"core {style:g} pt", "lines": len(members), "scores": means, "levels": {attr: level(value) for attr, value in means.items()},
            "pdf": {k: round(v, 3) for k, v in pdf_font.items()}, "rebuilt": {k: round(v, 3) for k, v in rebuilt_font.items()},
            "line_pitch": {"pdf": round(float(np.median([x["pdf"] for x in pitches])), 3), "rebuilt": round(float(np.median([x["rebuilt"] for x in pitches])), 3)} if pitches else None,
        })
    worst = min(((value, item["style"], attr) for item in summary for attr, value in item["scores"].items()), default=(0.0, "-", "-"))
    verdict = "ERROR" if not lines else level(worst[0])
    return {
        "zoom": zoom, "created": time.time(), "verdict": verdict, "worst": {"score": worst[0], "style": worst[1], "attribute": worst[2]},
        "matched": len(lines), "pdf_lines": len(pdf_segs), "rebuilt_lines": len(react_segs), "unmatched_pdf": len(only_pdf), "unmatched_rebuilt": len(only_react),
        "styles": summary, "lines": lines, "empty": not lines, "indent_scored": same_text,
    }


def _assign_styles(lines: list[dict]) -> None:
    """Cluster lines by PDF core height: sorted, a new style starts where the next height is more than STYLE_GAP above the current style's first."""
    start = None
    for line in sorted(lines, key=lambda item: item["pdf"]["core_height"]):
        height = line["pdf"]["core_height"]
        if start is None or height > start * (1 + STYLE_GAP):
            start = height
        line["style"] = round(start, 2)


def pdf_fonts(pdf: str, page: int) -> list[dict]:
    """Font name and size of the text layer, grouped (empty for outlined text). The real name decides the family; the size is exact."""
    import pdfplumber

    groups: dict[tuple[str, float], int] = {}
    with pdfplumber.open(pdf) as document:
        for char in document.pages[page - 1].chars:
            key = (char.get("fontname", "?"), round(float(char.get("size", 0)), 2))
            groups[key] = groups.get(key, 0) + 1
    return [{"font": name.split("+", 1)[-1], "size_pt": size, "chars": count} for (name, size), count in sorted(groups.items(), key=lambda item: -item[1])]


def to_markdown(page: int, result: dict, fonts: list[dict] | None = None) -> str:
    lines = [f"# Typography: page {page} ({result['zoom']} px/pt)", ""]
    if result["empty"]:
        return "\n".join(lines + ["**ERROR: no matched text line, nothing was scored.** Check the regions and ink colours (`colours`), and that the text lines are in place (text-layout).", ""])
    worst = result["worst"]
    lines.append(f"**Verdict: {result['verdict']}** (worst: {worst['attribute']} of style {worst['style']} at {worst['score']:.1%}; PASS >= 95 %, WARNING < 95 %, ERROR < 92 %). Lines scored: {result['matched']} of {result['pdf_lines']} in the PDF ({result['unmatched_pdf']} PDF / {result['unmatched_rebuilt']} rebuilt lines unmatched, see text-layout).")
    lines += ["", "| Style | Lines | Size | Weight | Family | Indent | Spacing | PDF core / stroke / contrast | Rebuilt core / stroke / contrast |", "|---|---|---|---|---|---|---|---|---|"]
    for style in result["styles"]:
        cells = [f"{style['scores'][a]:.1%} {'' if style['levels'][a] == 'PASS' else '**' + style['levels'][a] + '**'}".strip() if a in style["scores"] else "-" for a in ATTRIBUTES]
        p, r = style["pdf"], style["rebuilt"]
        lines.append(f"| {style['style']} | {style['lines']} | " + " | ".join(cells) + f" | {p['core_height']} / {p['stroke']} / {p['contrast']} | {r['core_height']} / {r['stroke']} / {r['contrast']} |")
    if not result.get("indent_scored", True):
        lines += ["", "**Indent not scored**: the two sides hold different text (`same_text: false`), so the ink edge differs by the first letter's side bearing. Check the text boxes' left edges with geometry checks (`data-wb` boxes) instead."]
    if fonts:
        lines += ["", "## Text layer of the PDF (exact: use these names and sizes)", "", "| Font | Size pt | Chars |", "|---|---|---|"]
        lines += [f"| {f['font']} | {f['size_pt']} | {f['chars']} |" for f in fonts[:15]]
    else:
        lines += ["", "No text layer (outlined text): sizes and families above are measured proxies. Set the CSS size from the ratio of core heights; choose the family whose contrast matches."]
    bad = [line for line in result["lines"] if min(line["scores"].values()) < WARNING_BELOW]
    if bad:
        lines += ["", "## Lines under 95 %", ""]
        for line in sorted(bad, key=lambda item: min(item["scores"].values()))[:30]:
            low = ", ".join(f"{k} {v:.1%}" for k, v in line["scores"].items() if v < WARNING_BELOW)
            lines.append(f"- line at ({line['pdf']['x0']:.1f}, {line['pdf']['top']:.1f}) pt: {low}")
    return "\n".join(lines) + "\n"


def write_result(folder: Path, page: int, result: dict, fonts: list[dict]) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    slim = {key: value for key, value in result.items() if key != "lines"}
    (folder / RESULT_FILE).write_text(json.dumps({**slim, "lines_scored": len(result["lines"]), "fonts": fonts}, indent=2), encoding="utf-8")
    (folder / "typography.md").write_text(to_markdown(page, result, fonts), encoding="utf-8")


def read_result(folder: Path) -> dict | None:
    path = folder / RESULT_FILE
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


# ---- spec (phase 3: determine) -------------------------------------------------------------------------------------------------------------
SPEC_FILE = "typography-spec.json"


def spec(pdf_image: np.ndarray, zoom: int, cfg: dict | None = None) -> dict:
    """The PDF's own typography, before anything is built: per style the core height, stroke, weight, contrast, line pitch and the left edges in use."""
    cfg = cfg or {}
    mask = textlayout.ink_mask(pdf_image, cfg.get("colours"))
    segs = textlayout.in_regions(textlayout.segments(pdf_image, zoom, cfg), cfg.get("regions"))
    lines = [{"pdf": asdict(m), "rebuilt": asdict(m), "scores": {}, "pitch": None, "style": 0.0, "x0": s.x0} for s in segs if (m := measure(mask, s, zoom))]
    lines.sort(key=lambda line: line["pdf"]["core_mid"])
    _assign_styles(lines)
    styles = []
    for style in sorted({line["style"] for line in lines}):
        members = [line for line in lines if line["style"] == style]
        font = pooled([LineMetrics(**line["pdf"]) for line in members], zoom)
        mids = sorted(line["pdf"]["core_mid"] for line in members)
        pitches = [b - a for a, b in zip(mids, mids[1:]) if 0 < b - a < 60]
        edges = sorted({round(line["x0"], 1) for line in members})
        styles.append({"style": f"core {style:g} pt", "lines": len(members), **{k: round(v, 3) for k, v in font.items()},
                       "line_pitch_median": round(float(np.median(pitches)), 3) if pitches else None, "left_edges": edges[:12]})
    return {"zoom": zoom, "created": time.time(), "styles": styles, "lines": len(lines)}


def spec_markdown(page: int, result: dict, fonts: list[dict]) -> str:
    lines = [f"# Typography spec: page {page} ({result['zoom']} px/pt)", "", "Measured from the PDF before building. Build the CSS from these, then confirm with `typography --url` (>= 95 % per attribute).", ""]
    lines += ["| Style | Lines | Core height pt | Stroke pt | Weight (stroke/core) | Contrast | Ink proportion | Line pitch pt | Left edges pt |", "|---|---|---|---|---|---|---|---|---|"]
    for s in result["styles"]:
        lines.append(f"| {s['style']} | {s['lines']} | {s['core_height']} | {s['stroke']} | {s['weight']:.3f} | {s['contrast']} | {s['proportion']:.3f} | {s['line_pitch_median'] or '-'} | {', '.join(map(str, s['left_edges']))} |")
    if fonts:
        lines += ["", "## Text layer (exact)", "", "| Font | Size pt | Chars |", "|---|---|---|"] + [f"| {f['font']} | {f['size_pt']} | {f['chars']} |" for f in fonts[:15]]
    else:
        lines += ["", "No text layer: the font size is not in the file. Render a candidate font in the lab, measure its core height the same way, and scale: css size = candidate size x (PDF core / candidate core). Contrast near 1 = gothic/sans; clearly above 1 = myeongjo/serif."]
    return "\n".join(lines) + "\n"


# ---- command -------------------------------------------------------------------------------------------------------------------------------
def _load(path: Path) -> np.ndarray:
    from PIL import Image

    Image.MAX_IMAGE_PIXELS = None
    return np.array(Image.open(path).convert("RGB"))  # uint8: a whole page at 8 px/pt stays affordable


def command_typography(args) -> int:
    from . import visual
    from .cli import page_width

    if args.zoom < MIN_ZOOM:
        print(f"typography: zoom {args.zoom} is under the minimum {MIN_ZOOM} px/pt (stroke widths need it)")
        return 2
    cfg = json.loads(Path(args.config).read_text(encoding="utf-8")) if args.config else {}
    if args.different_text:
        cfg["same_text"] = False
    folder = Path(args.output) / "pages" / f"page-{args.page:03d}"
    work = Path(args.run_dir) / "working-images" if args.run_dir else folder / "_work"
    work.mkdir(parents=True, exist_ok=True)
    pdf_image = _load(visual.render_pdf_page(args.pdf, args.page, work / f"pdf-{args.page}-z{args.zoom}.png", args.zoom))
    fonts = pdf_fonts(args.pdf, args.page)
    if args.spec_only:
        result = spec(pdf_image, args.zoom, cfg)
        folder.mkdir(parents=True, exist_ok=True)
        (folder / SPEC_FILE).write_text(json.dumps({**result, "fonts": fonts}, indent=2), encoding="utf-8")
        (folder / "typography-spec.md").write_text(spec_markdown(args.page, result, fonts), encoding="utf-8")
        print(spec_markdown(args.page, result, fonts))
        return 0 if result["styles"] else 1
    if not args.url:
        print("typography: give --url (the rebuilt page), or --spec-only to measure the PDF alone")
        return 2
    react_image = _load(visual.capture_react(args.url, work / f"react-z{args.zoom}", page_width(args.pdf, args.page), args.sheet, args.zoom, args.attr, args.sheet_selector, args.css_per_pt))
    result = compare(pdf_image, react_image, args.zoom, cfg)
    write_result(folder, args.page, result, fonts)
    print(to_markdown(args.page, result, fonts))
    return 1 if result["verdict"] == "ERROR" else 0


def register(add) -> None:
    cmd = add("typography", command_typography, "font size, weight, family, indent and line spacing per text style: --spec-only measures the PDF; with --url it scores the rebuilt page (PASS >= 95%%, WARNING < 95%%, ERROR < 92%%)")
    cmd.add_argument("--pdf", required=True)
    cmd.add_argument("--page", type=int, required=True)
    cmd.add_argument("--output", required=True)
    cmd.add_argument("--spec-only", action="store_true", help="phase 3: measure the PDF's typography before building")
    cmd.add_argument("--url", help="the lab URL of the rebuilt page")
    cmd.add_argument("--different-text", action="store_true", help="the rebuilt page holds other text (fixtures): indent is not scored")
    cmd.add_argument("--config", help="JSON: regions [[x, top, w, h]], colours (extra ink colours, e.g. a coloured heading)")
    cmd.add_argument("--zoom", type=int, default=MIN_ZOOM)
    cmd.add_argument("--sheet", type=int, default=0)
    cmd.add_argument("--attr", default="data-wb")
    cmd.add_argument("--sheet-selector")
    cmd.add_argument("--css-per-pt", type=float, default=8)
    cmd.add_argument("--run-dir")
