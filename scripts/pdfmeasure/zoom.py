"""Part-by-part comparison at high zoom: the same region of the PDF and of the lab page, cropped and rendered at one scale (12 px per point).

Measuring a whole page at a few pixels per point leaves errors of a pixel or two, which is the size of the differences that matter (a half-point
offset, a hairline's width). Here each part is cut out and compared at 1/12 pt per pixel. Three methods:

- align: the same shape on both sides (a corner, a frame end, a bubble, a fold): register the two masks, report the shift, the overlap before and
  after, the stroke thickness and the colour. A shift near 0 and an overlap near 1 mean the part is drawn in the same place and shape.
- ink: text that differs in font (a label, a number): the extent of its ink on both sides, edge by edge.
- line: a rule: its thickness, centre height and colour.
"""
from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image

from . import textmetrics

ZOOM = 12  # pixels per point (default; set_zoom changes it)
METHODS = {"align", "ink", "extent", "line", "lines", "words", "columns", "pitch"}
PAPER = np.array([255, 255, 255])

def parse_hex(colour: str) -> tuple[int, int, int]:
    value = colour.lstrip("#")
    return (int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16))


@dataclass(frozen=True)
class Part:
    name: str
    box: tuple[int, int, int, int]  # x, top, width, height in whole points
    method: str  # align | ink | line
    colour: str  # "#rrggbb" (pixels near that colour), "ink" (dark neutral pixels), "any" (anything that is not paper), "text" or "caption" for the text methods
    tolerance_shift: float = 0.5  # points
    tolerance_thickness: float = 0.15
    thickness: bool = True  # false for filled shapes, where the median vertical run is not a stroke width
    centre: bool = False  # lines of different text: compare the centre of each line (glyph tops and bottoms vary with the letters)
    tolerance_colour: int = 10  # hex-coloured parts: largest per-channel gap between the mean colours (0-255)
    min_overlap: float = 0.7  # align: least overlap (IoU) of the two masks after the shift; below it the shapes differ, not just the position
    spacing: float = 0.35  # points: tolerance of a line's top, bottom and height, of a word's edges, and of the letter pitch


def load_parts(path: str) -> list[Part]:
    """Parts from a JSON file: a list of {name, box:[x, top, width, height], method, colour, ...} (see references/config-reference.md)."""
    import json

    parts: list[Part] = []
    entries = json.loads(Path(path).read_text(encoding="utf-8"))
    if not entries:
        raise SystemExit(f"{path}: no parts, so nothing would be verified")
    for entry in entries:
        if entry.get("method") not in METHODS:
            raise SystemExit(f"{path}: part {entry.get('name')!r} has method {entry.get('method')!r}, expected one of {sorted(METHODS)}")
        box = tuple(int(value) for value in entry["box"])
        if len(box) != 4 or box[2] <= 0 or box[3] <= 0:
            raise SystemExit(f"{entry['name']}: box must be [x, top, width, height] in whole points, got {entry['box']}")
        parts.append(
            Part(
                name=entry["name"],
                box=box,  # type: ignore[arg-type]
                method=entry["method"],
                colour=entry.get("colour", "any"),
                tolerance_shift=entry.get("tolerance_shift", 0.5),
                tolerance_thickness=entry.get("tolerance_thickness", 0.15),
                thickness=entry.get("thickness", True),
                centre=entry.get("centre", False),
                tolerance_colour=entry.get("tolerance_colour", 10),
                min_overlap=entry.get("min_overlap", 0.7),
                spacing=entry.get("spacing", 0.35),
            )
        )
    return parts


@dataclass
class Result:
    part: Part
    values: dict[str, float | str]
    problems: list[str]


def crop_lab(sheet: np.ndarray, part: Part) -> np.ndarray:
    """The part cut out of the lab sheet raster by array indexing: exact to the device pixel, with no browser clip to round the origin."""
    x, top, width, height = part.box
    return sheet[top * ZOOM : (top + height) * ZOOM, x * ZOOM : (x + width) * ZOOM]


def crop_pdf(pdf_path: str, page: int, part: Part, out_dir: Path) -> Path:
    """The part of the PDF page at ZOOM px/pt, cut by pdftoppm itself so no full-page render is needed."""
    x, top, width, height = part.box
    prefix = out_dir / f"pdf-{part.name}"
    subprocess.run(
        ["pdftoppm", "-f", str(page), "-l", str(page), "-r", str(ZOOM * 72), "-x", str(x * ZOOM), "-y", str(top * ZOOM), "-W", str(width * ZOOM), "-H", str(height * ZOOM), "-png", "-singlefile", pdf_path, str(prefix)],
        check=True,
    )
    return Path(f"{prefix}.png")


def load(path: Path) -> np.ndarray:
    return np.array(Image.open(path).convert("RGB")).astype(int)


def mask_of(image: np.ndarray, colour: str) -> np.ndarray:
    if colour == "any":
        return np.abs(image - PAPER).max(axis=2) > 60
    if colour == "ink":
        return (image @ np.array([0.299, 0.587, 0.114])) < 110
    target = np.array(parse_hex(colour))
    return np.abs(image - target).sum(axis=2) < 70


def set_zoom(pixels_per_point: int) -> None:
    """Zoom of every crop (px per point); also the one the text metrics assume. Call before comparing."""
    global ZOOM
    if pixels_per_point < 4 or pixels_per_point > 32:
        raise SystemExit(f"zoom must be between 4 and 32 px per point, got {pixels_per_point}")
    ZOOM = int(pixels_per_point)
    textmetrics.ZOOM = ZOOM


def register(a: np.ndarray, b: np.ndarray, limit: int | None = None) -> tuple[int, int]:
    """Shift (dx, dy) in pixels that moves mask b onto mask a, by FFT cross-correlation limited to +-limit pixels (default 3 pt)."""
    limit = 3 * ZOOM if limit is None else limit
    height, width = a.shape
    fa = np.fft.rfft2(a.astype(float), s=(height * 2, width * 2))
    fb = np.fft.rfft2(b.astype(float), s=(height * 2, width * 2))
    correlation = np.fft.irfft2(fa * np.conj(fb), s=(height * 2, width * 2))
    best, best_shift = -1.0, (0, 0)
    for dy in range(-limit, limit + 1):
        for dx in range(-limit, limit + 1):
            value = correlation[dy % (height * 2), dx % (width * 2)]
            if value > best:
                best, best_shift = value, (dx, dy)
    return best_shift


def overlap(a: np.ndarray, b: np.ndarray) -> float:
    union = np.logical_or(a, b).sum()
    return float(np.logical_and(a, b).sum() / union) if union else 1.0


def shifted(mask: np.ndarray, dx: int, dy: int) -> np.ndarray:
    out = np.zeros_like(mask)
    height, width = mask.shape
    ys, xs = slice(max(dy, 0), height + min(dy, 0)), slice(max(dx, 0), width + min(dx, 0))
    yd, xd = slice(max(-dy, 0), height + min(-dy, 0)), slice(max(-dx, 0), width + min(-dx, 0))
    out[ys, xs] = mask[yd, xd]
    return out


def extent(mask: np.ndarray) -> tuple[float, float, float, float] | None:
    rows, cols = np.where(mask)
    if rows.size == 0:
        return None
    return (cols.min() / ZOOM, rows.min() / ZOOM, (cols.max() + 1) / ZOOM, (rows.max() + 1) / ZOOM)


def colour_difference(a: np.ndarray, ma: np.ndarray, b: np.ndarray, mb: np.ndarray) -> int:
    """Largest per-channel gap between the mean colours of the two masked regions."""
    return int(np.abs(a[ma].mean(axis=0) - b[mb].mean(axis=0)).max().round())


def mean_colour(image: np.ndarray, mask: np.ndarray) -> str:
    if not mask.any():
        return "-"
    r, g, b = image[mask].mean(axis=0).round().astype(int)
    return f"#{r:02x}{g:02x}{b:02x}"


def thickness(mask: np.ndarray) -> float:
    """Median length in points of the vertical runs of a mask: the thickness of a horizontal stroke."""
    runs: list[int] = []
    for column in mask.T[:: max(1, mask.shape[1] // 200)]:
        run = 0
        for value in column:
            if value:
                run += 1
            elif run:
                runs.append(run)
                run = 0
        if run:
            runs.append(run)
    return float(np.median(runs)) / ZOOM if runs else 0.0


def compare_text(part: Part, a: np.ndarray, b: np.ndarray) -> Result:
    """Spacing of text: lines (top, bottom, pitch), words (edges, so letter spacing and spaces) or the letter pitch of one line."""
    kind = "caption" if part.colour == "caption" else "text"
    ma, mb = textmetrics.text_mask(a, kind), textmetrics.text_mask(b, kind)
    values: dict[str, float | str] = {}
    problems: list[str] = []
    if part.method == "lines":
        la, lb = textmetrics.bands(ma), textmetrics.bands(mb)
        values["lines pdf / lab"] = f"{len(la)} / {len(lb)}"
        if len(la) != len(lb):
            problems.append(f"{len(la)} lines in the PDF, {len(lb)} in the lab")
        for index, (x, y) in enumerate(zip(la, lb), start=1):
            pitch_a = "-" if index == 1 else f"{x[0] - la[index - 2][0]:.2f}"
            pitch_b = "-" if index == 1 else f"{y[0] - lb[index - 2][0]:.2f}"
            values[f"line {index}: top / bottom (pt), pdf"] = f"{x[0]:.2f} / {x[1]:.2f}"
            values[f"line {index}: top / bottom (pt), lab"] = f"{y[0]:.2f} / {y[1]:.2f}   (pitch from the line above: pdf {pitch_a}, lab {pitch_b})"
            checks = (("centre", (y[0] + y[1]) / 2 - (x[0] + x[1]) / 2),) if part.centre else (("top", y[0] - x[0]), ("bottom", y[1] - x[1]))
            for label, delta in checks:
                if abs(delta) > (0.5 if part.centre else part.spacing):
                    problems.append(f"line {index} {label} off by {delta:+.2f} pt")
    if part.method == "words":
        wa, wb = textmetrics.words(ma), textmetrics.words(mb)
        values["words pdf / lab"] = f"{len(wa)} / {len(wb)}"
        if len(wa) != len(wb):
            problems.append(f"{len(wa)} words in the PDF, {len(wb)} in the lab")
        for index, (x, y) in enumerate(zip(wa, wb), start=1):
            values[f"word {index}: x0 / x1 (pt), pdf"] = f"{x[0]:.2f} / {x[1]:.2f}  (width {x[1] - x[0]:.2f})"
            values[f"word {index}: x0 / x1 (pt), lab"] = f"{y[0]:.2f} / {y[1]:.2f}  (width {y[1] - y[0]:.2f})"
            if abs(y[0] - x[0]) > 1.0 or abs(y[1] - x[1]) > 1.0:  # the printed face and the lab's differ, so single words vary by tenths of a point
                problems.append(f"word {index} edges off by ({y[0] - x[0]:+.2f}, {y[1] - x[1]:+.2f}) pt")
        if wa and wb and len(wa) == len(wb) and len(wa) > 1:
            width_a, width_b = wa[-1][1] - wa[0][0], wb[-1][1] - wb[0][0]
            gaps_a = [wa[i + 1][0] - wa[i][1] for i in range(len(wa) - 1)]
            gaps_b = [wb[i + 1][0] - wb[i][1] for i in range(len(wb) - 1)]
            mean_a, mean_b = sum(gaps_a) / len(gaps_a), sum(gaps_b) / len(gaps_b)
            values["line width pdf / lab (pt)"] = f"{width_a:.2f} / {width_b:.2f}"
            values["mean word gap pdf / lab (pt)"] = f"{mean_a:.2f} / {mean_b:.2f}"
            values["mean word width pdf / lab (pt)"] = f"{sum(x[1] - x[0] for x in wa) / len(wa):.2f} / {sum(x[1] - x[0] for x in wb) / len(wb):.2f}"
            starts_a = [wa[i + 1][0] for i, gap in enumerate(gaps_a) if gap > 20]
            starts_b = [wb[i + 1][0] for i, gap in enumerate(gaps_b) if gap > 20]
            if starts_a or starts_b:
                values["column starts pdf / lab (pt)"] = f"{[round(v, 2) for v in starts_a]} / {[round(v, 2) for v in starts_b]}"
                if len(starts_a) != len(starts_b) or any(abs(p - q) > 0.8 for p, q in zip(starts_a, starts_b)):
                    problems.append("column starts differ")
            if abs(width_a - width_b) > 0.5 and not (starts_a or starts_b):
                problems.append(f"line width off by {width_b - width_a:+.2f} pt")
            if abs(mean_a - mean_b) > 0.25:
                problems.append(f"mean word gap off by {mean_b - mean_a:+.2f} pt")
    if part.method == "columns":
        wa, wb = textmetrics.words(ma, 2.0), textmetrics.words(mb, 2.0)
        starts_a = [wa[i + 1][0] for i in range(len(wa) - 1) if wa[i + 1][0] - wa[i][1] > 20]
        starts_b = [wb[i + 1][0] for i in range(len(wb) - 1) if wb[i + 1][0] - wb[i][1] > 20]
        values["first word starts pdf / lab (pt)"] = f"{wa[0][0]:.2f} / {wb[0][0]:.2f}" if wa and wb else "-"
        values["column starts pdf / lab (pt)"] = f"{[round(v, 2) for v in starts_a]} / {[round(v, 2) for v in starts_b]}"
        if wa and wb and abs(wa[0][0] - wb[0][0]) > 0.5:
            problems.append(f"first word starts {wb[0][0] - wa[0][0]:+.2f} pt off")
        if len(starts_a) != len(starts_b) or any(abs(p - q) > 0.8 for p, q in zip(starts_a, starts_b)):
            problems.append("column starts differ")
    if part.method == "pitch":
        sa, sb = textmetrics.pitch(ma), textmetrics.pitch(mb)
        if sa is None or sb is None:
            problems.append("too little text to measure the pitch")
            return Result(part, {"measured pdf / lab": f"{sa is not None} / {sb is not None}"}, problems)
        values["letter pitch pdf / lab (pt)"] = f"{sa['pitch']:.3f} / {sb['pitch']:.3f}"
        values["median gap between words pdf / lab (pt)"] = f"{sa['space_gap']:.2f} / {sb['space_gap']:.2f}  ({int(sa['space_samples'])} / {int(sb['space_samples'])} spaces)"
        # Different sentences give an estimate that differs by up to about 0.3 pt (checked on the lab against the DOM), so this is a tolerance of 0.35 pt.
        if abs(sa["pitch"] - sb["pitch"]) > 0.35:
            problems.append(f"letter pitch off by {sb['pitch'] - sa['pitch']:+.3f} pt ({(sb['pitch'] / sa['pitch'] - 1) * 100:+.1f}%)")
        enough = min(sa["space_samples"], sb["space_samples"]) >= 12  # the median of a few gaps jumps between two modes
        if enough and abs(sa["space_gap"] - sb["space_gap"]) > 0.6:
            problems.append(f"gap between words off by {sb['space_gap'] - sa['space_gap']:+.2f} pt")
    return Result(part, values, problems)


def compare_part(part: Part, pdf_image: np.ndarray, lab_image: np.ndarray) -> Result:
    height = min(pdf_image.shape[0], lab_image.shape[0])
    width = min(pdf_image.shape[1], lab_image.shape[1])
    a, b = pdf_image[:height, :width], lab_image[:height, :width]
    if part.method in ("lines", "words", "pitch", "columns"):
        return compare_text(part, a, b)
    ma, mb = mask_of(a, part.colour), mask_of(b, part.colour)
    values: dict[str, float | str] = {}
    problems: list[str] = []
    if not ma.any() or not mb.any():
        return Result(part, {"mask pixels (pdf / lab)": f"{int(ma.sum())} / {int(mb.sum())}"}, ["a side has none of the part's colour in the region"])
    if part.method == "align":
        dx, dy = register(ma, mb)
        values["shift x (pt)"] = round(dx / ZOOM, 2)
        values["shift y (pt)"] = round(dy / ZOOM, 2)
        values["overlap before"] = round(overlap(ma, mb), 3)
        values["overlap after"] = round(overlap(ma, shifted(mb, dx, dy)), 3)
        values["thickness pdf / lab (pt)"] = f"{thickness(ma):.2f} / {thickness(mb):.2f}"
        values["colour pdf / lab"] = f"{mean_colour(a, ma)} / {mean_colour(b, mb)}"
        if abs(dx / ZOOM) > part.tolerance_shift or abs(dy / ZOOM) > part.tolerance_shift:
            problems.append(f"shifted by ({dx / ZOOM:+.2f}, {dy / ZOOM:+.2f}) pt")
        if values["overlap after"] < part.min_overlap:
            problems.append(f"shapes differ: overlap {values['overlap after']} after the shift, need {part.min_overlap}")
        if part.thickness and abs(thickness(ma) - thickness(mb)) > part.tolerance_thickness and thickness(ma) < 3:
            problems.append("stroke thickness differs")
    if part.method == "extent":
        ea, eb = extent(ma), extent(mb)
        assert ea is not None and eb is not None
        for label, index in (("left", 0), ("top", 1), ("right", 2), ("bottom", 3)):
            values[f"{label} edge pdf / lab (pt)"] = f"{ea[index]:.2f} / {eb[index]:.2f}"
            if abs(ea[index] - eb[index]) > part.tolerance_shift:
                problems.append(f"{label} edge off by {eb[index] - ea[index]:+.2f} pt")
        values["colour pdf / lab"] = f"{mean_colour(a, ma)} / {mean_colour(b, mb)}"
    if part.method == "ink":
        ea, eb = extent(ma), extent(mb)
        assert ea is not None and eb is not None
        for label, index in (("left", 0), ("top", 1), ("right", 2), ("bottom", 3)):
            values[f"ink {label} pdf / lab (pt)"] = f"{ea[index]:.2f} / {eb[index]:.2f}"
            if abs(ea[index] - eb[index]) > 1.0 and label in ("top", "bottom"):
                problems.append(f"ink {label} off by {eb[index] - ea[index]:+.2f} pt")
        values["colour pdf / lab"] = f"{mean_colour(a, ma)} / {mean_colour(b, mb)}"
    if part.method == "line":
        ea, eb = extent(ma), extent(mb)
        assert ea is not None and eb is not None
        values["thickness pdf / lab (pt)"] = f"{thickness(ma):.2f} / {thickness(mb):.2f}"
        values["centre y pdf / lab (pt)"] = f"{(ea[1] + ea[3]) / 2:.2f} / {(eb[1] + eb[3]) / 2:.2f}"
        values["colour pdf / lab"] = f"{mean_colour(a, ma)} / {mean_colour(b, mb)}"
        if abs((ea[1] + ea[3]) / 2 - (eb[1] + eb[3]) / 2) > part.tolerance_shift:
            problems.append("centre height differs")
        if abs(thickness(ma) - thickness(mb)) > part.tolerance_thickness:
            problems.append("thickness differs")
    if part.colour.startswith("#"):  # the mask accepts colours near the target on both sides, so compare what each side really shows
        difference = colour_difference(a, ma, b, mb)
        values["colour difference (max channel, 0-255)"] = difference
        if difference > part.tolerance_colour:
            problems.append(f"colour differs by {difference} (max channel), allowed {part.tolerance_colour}")
    return Result(part, values, problems)


def triptych(pdf_image: np.ndarray, lab_image: np.ndarray, part: Part, out: Path) -> None:
    """PDF | lab | difference (red = only in the PDF, blue = only in the lab) at the crop's zoom, for looking at."""
    height = min(pdf_image.shape[0], lab_image.shape[0])
    width = min(pdf_image.shape[1], lab_image.shape[1])
    a, b = pdf_image[:height, :width], lab_image[:height, :width]
    ma, mb = mask_of(a, "any"), mask_of(b, "any")
    diff = np.full((height, width, 3), 255, dtype=np.uint8)
    diff[np.logical_and(ma, mb)] = (170, 170, 170)
    diff[np.logical_and(ma, ~mb)] = (220, 40, 40)
    diff[np.logical_and(~ma, mb)] = (40, 80, 220)
    sheet = np.concatenate([a.astype(np.uint8), np.full((height, 8, 3), 200, np.uint8), b.astype(np.uint8), np.full((height, 8, 3), 200, np.uint8), diff], axis=1)
    Image.fromarray(sheet).save(out)


def to_markdown(title: str, results: list[Result], image_dir: str | None = None) -> str:
    bad = [result for result in results if result.problems]
    lines = [f"## {title}", "", f"{len(results) - len(bad)} of {len(results)} parts match at {ZOOM} px per point.", ""]
    for result in results:
        status = "ok" if not result.problems else "**off:** " + "; ".join(result.problems)
        lines.append(f"### {result.part.name} ({result.part.method}) {status}")
        lines.append("")
        if image_dir:
            lines.append(f"![{result.part.name}: PDF | rebuilt | difference]({image_dir}/zoom-{result.part.name}.png)")
            lines.append("")
        lines.append("| | |")
        lines.append("|---|---|")
        for key, value in result.values.items():
            lines.append(f"| {key} | {value} |")
        lines.append("")
    return "\n".join(lines)
