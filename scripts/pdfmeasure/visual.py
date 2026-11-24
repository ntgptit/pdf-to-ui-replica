"""Full-page visual comparison of a PDF page and the rebuilt page: evidence images and metrics for the agent to judge.

Pixels never decide PASS or FAIL here. The result is `needs_review` (with regions to look at) or a refusal (`size_mismatch`). Anti-aliasing, font
rendering and artwork differ by nature, so the agent reads the images; the numbers say where to look and whether a later run improved.
Nothing is resized to hide a geometry error: images of different size are reported and not compared.
"""
from __future__ import annotations

import subprocess
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

from . import zoom as zoom_module

SIZE_TOLERANCE_PX = 2  # px: rounding of the browser's sheet size and of pdftoppm's page size
DIFF_THRESHOLD = 48  # largest per-channel difference counted as a different pixel
CELL_PT = 3.0  # coarse grid used to group different pixels into regions
CELL_MIN_RATIO = 0.04  # share of different pixels that makes a cell "different"
MIN_REGION_PT2 = 12.0  # smaller regions are noise (single glyph edges)
SHIFT_WARNING_PT = 0.75  # a global shift above this means the two images are not registered


@dataclass
class Region:
    index: int
    x: float
    top: float
    width: float
    height: float
    diff_ratio: float  # share of different pixels inside the box
    diff_pixels: int

    def box(self) -> list[float]:
        return [round(self.x, 2), round(self.top, 2), round(self.width, 2), round(self.height, 2)]


@dataclass
class Comparison:
    status: str  # needs_review | size_mismatch
    zoom: int
    pdf_size_px: tuple[int, int]
    react_size_px: tuple[int, int]
    diff_ratio: float = 0.0
    global_shift_pt: tuple[float, float] = (0.0, 0.0)
    warnings: list[str] = field(default_factory=list)
    regions: list[Region] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "status": self.status,
            "zoom_px_per_pt": self.zoom,
            "pdf_size_px": list(self.pdf_size_px),
            "react_size_px": list(self.react_size_px),
            "diff_ratio": round(self.diff_ratio, 5),
            "global_shift_pt": [round(v, 2) for v in self.global_shift_pt],
            "warnings": self.warnings,
            "regions": [{"index": r.index, "box_pt": r.box(), "diff_ratio": round(r.diff_ratio, 4), "diff_pixels": r.diff_pixels} for r in self.regions],
        }


# ---- capture ----------------------------------------------------------------------------------------------------------------------------
def render_pdf_page(pdf: str, page: int, out: Path, zoom: int) -> Path:
    """The whole PDF page at `zoom` px per point."""
    prefix = out.with_suffix("")
    subprocess.run(["pdftoppm", "-f", str(page), "-l", str(page), "-r", str(zoom * 72), "-png", "-singlefile", pdf, str(prefix)], check=True)
    return Path(f"{prefix}.png")


def capture_react(url: str, out_dir: Path, page_width_pt: float, sheet: int, zoom: int, attr: str, sheet_selector: str | None, css_per_pt: float) -> Path:
    """The rebuilt sheet at `zoom` px per point, with crop-dom.cjs (it waits for fonts and images and pins the sheet to a whole pixel)."""
    from .cli import SCRIPTS

    command = ["node", str(SCRIPTS / "crop-dom.cjs"), url, str(out_dir), "--page-width-pt", str(page_width_pt), "--sheet", str(sheet), "--zoom", str(zoom), "--css-per-pt", str(css_per_pt), "--attr", attr]
    if sheet_selector:
        command += ["--sheet-selector", sheet_selector]
    subprocess.run(command, check=True, stdout=subprocess.DEVNULL)
    return out_dir / "sheet-zoom.png"


# ---- comparison -------------------------------------------------------------------------------------------------------------------------
def load_rgb(path: Path) -> np.ndarray:
    Image.MAX_IMAGE_PIXELS = None
    return np.array(Image.open(path).convert("RGB")).astype(int)


def diff_mask(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    return np.abs(a - b).max(axis=2) > DIFF_THRESHOLD


def label_regions(mask: np.ndarray, zoom: int) -> list[Region]:
    """Group different pixels into regions through a coarse grid (flood fill on cells), largest first."""
    cell = max(1, int(round(CELL_PT * zoom)))
    rows, cols = -(-mask.shape[0] // cell), -(-mask.shape[1] // cell)
    padded = np.zeros((rows * cell, cols * cell), dtype=bool)
    padded[: mask.shape[0], : mask.shape[1]] = mask
    share = padded.reshape(rows, cell, cols, cell).mean(axis=(1, 3))
    hot = share >= CELL_MIN_RATIO
    seen = np.zeros_like(hot)
    regions: list[Region] = []
    for r0 in range(rows):
        for c0 in range(cols):
            if not hot[r0, c0] or seen[r0, c0]:
                continue
            queue, members = deque([(r0, c0)]), []
            seen[r0, c0] = True
            while queue:
                r, c = queue.popleft()
                members.append((r, c))
                for dr in (-1, 0, 1):
                    for dc in (-1, 0, 1):
                        rr, cc = r + dr, c + dc
                        if 0 <= rr < rows and 0 <= cc < cols and hot[rr, cc] and not seen[rr, cc]:
                            seen[rr, cc] = True
                            queue.append((rr, cc))
            rs, cs = [m[0] for m in members], [m[1] for m in members]
            y0, y1, x0, x1 = min(rs) * cell, min((max(rs) + 1) * cell, mask.shape[0]), min(cs) * cell, min((max(cs) + 1) * cell, mask.shape[1])
            box = mask[y0:y1, x0:x1]
            width_pt, height_pt = (x1 - x0) / zoom, (y1 - y0) / zoom
            if width_pt * height_pt < MIN_REGION_PT2:
                continue
            regions.append(Region(0, x0 / zoom, y0 / zoom, width_pt, height_pt, float(box.mean()), int(box.sum())))
    regions.sort(key=lambda region: region.diff_pixels, reverse=True)
    for index, region in enumerate(regions, start=1):
        region.index = index
    return regions


def global_shift(a: np.ndarray, b: np.ndarray, zoom: int) -> tuple[float, float]:
    """Translation between the two images, from the ink masks on a 1/4 grid (a registration check; nothing is moved)."""
    step = max(1, zoom // 3)
    ma = (a[::step, ::step].mean(axis=2) < 200)
    mb = (b[::step, ::step].mean(axis=2) < 200)
    if not ma.any() or not mb.any():
        return (0.0, 0.0)
    dx, dy = zoom_module.register(ma, mb, limit=max(2, int(round(6 * zoom / step))))
    return (dx * step / zoom, dy * step / zoom)


def compare_images(pdf_img: np.ndarray, react_img: np.ndarray, zoom: int) -> tuple[Comparison, np.ndarray | None]:
    """Compare two renders of the same page. Different sizes are reported, never resized. Returns the comparison and the difference mask."""
    comparison = Comparison("needs_review", zoom, (pdf_img.shape[1], pdf_img.shape[0]), (react_img.shape[1], react_img.shape[0]))
    d_w, d_h = react_img.shape[1] - pdf_img.shape[1], react_img.shape[0] - pdf_img.shape[0]
    if abs(d_w) > SIZE_TOLERANCE_PX or abs(d_h) > SIZE_TOLERANCE_PX:
        comparison.status = "size_mismatch"
        comparison.warnings.append(f"size differs: PDF {comparison.pdf_size_px} px, React {comparison.react_size_px} px (width {d_w:+d}, height {d_h:+d}); not compared and not resized. Fix the page box / sheet size first.")
        return comparison, None
    height, width = min(pdf_img.shape[0], react_img.shape[0]), min(pdf_img.shape[1], react_img.shape[1])
    a, b = pdf_img[:height, :width], react_img[:height, :width]  # at most SIZE_TOLERANCE_PX of rounding cropped, never scaled
    mask = diff_mask(a, b)
    comparison.diff_ratio = float(mask.mean())
    comparison.global_shift_pt = global_shift(a, b, zoom)
    if max(abs(comparison.global_shift_pt[0]), abs(comparison.global_shift_pt[1])) > SHIFT_WARNING_PT:
        comparison.warnings.append(f"the images are shifted by ({comparison.global_shift_pt[0]:+.2f}, {comparison.global_shift_pt[1]:+.2f}) pt: a registration or geometry error, not local differences")
    comparison.regions = label_regions(mask, zoom)
    return comparison, mask


# ---- evidence images ------------------------------------------------------------------------------------------------------------------
def _label(image: Image.Image, text: str) -> Image.Image:
    bar = Image.new("RGB", (image.width, 18), (235, 235, 235))
    ImageDraw.Draw(bar).text((4, 3), text, fill=(0, 0, 0))
    out = Image.new("RGB", (image.width, image.height + 18), (255, 255, 255))
    out.paste(bar, (0, 0))
    out.paste(image, (0, 18))
    return out


def _to_image(array: np.ndarray) -> Image.Image:
    return Image.fromarray(array.astype(np.uint8))


def side_by_side(images: list[tuple[str, np.ndarray]], out: Path) -> None:
    """Labelled images in a row (PDF | React V0, or PDF | React V0 | React V1). Sizes are kept; a shorter image is padded, not scaled."""
    tiles = [_label(_to_image(array), name) for name, array in images]
    height = max(tile.height for tile in tiles)
    sheet = Image.new("RGB", (sum(tile.width for tile in tiles) + 8 * (len(tiles) - 1), height), (200, 200, 200))
    x = 0
    for tile in tiles:
        sheet.paste(tile, (x, 0))
        x += tile.width + 8
    sheet.save(out)


def overlay(pdf_img: np.ndarray, react_img: np.ndarray, out: Path) -> None:
    """PDF in red, React in blue, on white: where they agree the ink is dark, where they differ it is coloured."""
    height, width = min(pdf_img.shape[0], react_img.shape[0]), min(pdf_img.shape[1], react_img.shape[1])
    ink_a = 255 - pdf_img[:height, :width].mean(axis=2)
    ink_b = 255 - react_img[:height, :width].mean(axis=2)
    canvas = np.full((height, width, 3), 255.0)
    canvas[..., 1] -= (ink_a + ink_b) * 0.5
    canvas[..., 0] -= ink_b
    canvas[..., 2] -= ink_a
    _to_image(np.clip(canvas, 0, 255)).save(out)


def heatmap(mask: np.ndarray, pdf_img: np.ndarray, regions: list[Region], zoom: int, out: Path) -> None:
    """Faded PDF with the different pixels in red and each region boxed and numbered."""
    base = 255 - (255 - pdf_img[: mask.shape[0], : mask.shape[1]]) * 0.35
    base[mask] = (220, 30, 30)
    image = _to_image(base)
    draw = ImageDraw.Draw(image)
    for region in regions:
        x, y, w, h = (region.x * zoom, region.top * zoom, region.width * zoom, region.height * zoom)
        draw.rectangle([x, y, x + w, y + h], outline=(0, 90, 220), width=max(1, zoom // 3))
        draw.text((x + 2, y + 2), str(region.index), fill=(0, 90, 220))
    image.save(out)


def crop_regions(images: dict[str, np.ndarray], regions: list[Region], zoom: int, out_dir: Path, limit: int = 40, pad_pt: float = 4.0) -> list[str]:
    """One enlarged strip per region (the images side by side) for the regions with the most different pixels."""
    out_dir.mkdir(parents=True, exist_ok=True)
    written: list[str] = []
    for region in regions[:limit]:
        x0, y0 = max(0, int((region.x - pad_pt) * zoom)), max(0, int((region.top - pad_pt) * zoom))
        x1, y1 = int((region.x + region.width + pad_pt) * zoom), int((region.top + region.height + pad_pt) * zoom)
        tiles = []
        for name, array in images.items():
            crop = _to_image(array[y0:y1, x0:x1])
            factor = max(1, 360 // max(1, crop.width))
            tiles.append((name, np.array(crop.resize((crop.width * factor, crop.height * factor), Image.NEAREST))))
        path = out_dir / f"region-{region.index:02d}.png"
        side_by_side(tiles, path)
        written.append(path.name)
    return written


def region_kind(region: Region) -> str:
    """A hint for the agent, not a verdict: what the region probably is, from its shape."""
    w, h = region.width, region.height
    if h <= 6 and w >= 30:
        return "rule / line"
    if w <= 12 and h <= 12:
        return "mark / glyph"
    if region.diff_ratio >= 0.5:
        return "solid block (fill or picture)"
    if w * h >= 2500:
        return "large area (picture, table, frame)"
    return "text or detail"


def scan_markdown(page: int, label: str, comparison: Comparison, crops: list[str], progress: dict | None, failing: list[str] | None, verify_note: str = "") -> str:
    """One report per scan: every different region with its crop, the registration warnings, progress against V0 and the failing geometry/zoom entries.
    The agent triages from this single file instead of running the comparison again and again."""
    lines = [f"# Scan: page {page}, {label}", ""]
    lines.append(f"- status: **{comparison.status}**; different pixels: {comparison.diff_ratio:.4f}; global shift (pt): {comparison.global_shift_pt[0]:+.2f}, {comparison.global_shift_pt[1]:+.2f}")
    lines += [f"- WARNING: {warning}" for warning in comparison.warnings]
    if progress and progress.get("comparable"):
        lines.append(f"- against V0: different pixels {progress['diff_ratio_before']} to {progress['diff_ratio_after']}; improved {len(progress['improved'])}, unchanged {len(progress['unchanged'])}, worse {len(progress['worse'])}, new {len(progress['new_regions'])}" + ("; **regression**" if progress["regression"] else ""))
        lines += [f"  - worse: region {w['region']} {w['box_pt']} {w['before']} to {w['after']}" for w in progress["worse"]]
        lines += [f"  - new: region {n['region']} {n['box_pt']} ({n['diff_ratio']})" for n in progress["new_regions"]]
    lines += ["", "## Regions to triage (largest first). Look at each crop, then record the real defects with `issue add` or `issue add-batch`.", "", "| # | Box [x, top, w, h] pt | Different | Hint | Crop |", "|---|---|---|---|---|"]
    crop_names = {int(name.split("-")[1].split(".")[0]): name for name in crops}
    for region in comparison.regions:
        crop = crop_names.get(region.index)
        link = f"[{crop}](crops/{label}/{crop})" if crop else "(no crop: over the limit, see heatmap)"
        lines.append(f"| {region.index} | {region.box()} | {region.diff_ratio:.2f} | {region_kind(region)} | {link} |")
    lines += ["", "## Failing geometry / zoom / text-layout entries (same run)", ""]
    lines += [f"- {item}" for item in failing] if failing else [verify_note or "- none, or verify was not requested"]
    lines += ["", "Text and artwork regions usually differ by design (fonts, original drawings): judge from the crops, severity is yours.",
              "This scan locates differences at low zoom; small parts (numbered markers, arrowheads, dotted guides, stroke weight) are judged on `tiles --mode pair` (>= 6 px/pt), not on these crops."]
    return "\n".join(lines) + "\n"


def region_overlap(a: Region, b: Region) -> float:
    x0, y0 = max(a.x, b.x), max(a.top, b.top)
    x1, y1 = min(a.x + a.width, b.x + b.width), min(a.top + a.height, b.top + b.height)
    inter = max(0.0, x1 - x0) * max(0.0, y1 - y0)
    union = a.width * a.height + b.width * b.height - inter
    return inter / union if union else 0.0


def compare_runs(before: Comparison, after: Comparison, mask_after: np.ndarray | None, zoom: int) -> dict:
    """Progress and regressions of V1 against V0, both measured against the PDF. A region improved when its different-pixel share fell by a third."""
    if before.status != "needs_review" or after.status != "needs_review" or mask_after is None:
        return {"comparable": False, "reason": "a run has size_mismatch"}
    improved, same, worse = [], [], []
    for region in before.regions:
        x0, y0 = int(region.x * zoom), int(region.top * zoom)
        box = mask_after[y0 : y0 + int(region.height * zoom), x0 : x0 + int(region.width * zoom)]
        now = float(box.mean()) if box.size else 0.0
        entry = {"region": region.index, "before": round(region.diff_ratio, 4), "after": round(now, 4), "box_pt": region.box()}
        if now <= region.diff_ratio * 0.67:
            improved.append(entry)
        elif now >= region.diff_ratio * 1.2:
            worse.append(entry)
        else:
            same.append(entry)
    new = [r for r in after.regions if not any(region_overlap(r, old) > 0.1 for old in before.regions)]
    big_new = [r for r in new if r.diff_pixels / (zoom * zoom) >= 60]  # under 60 pt2 of different ink (a speck, a tail tip) is noted, not a regression
    return {
        "comparable": True,
        "diff_ratio_before": round(before.diff_ratio, 5),
        "diff_ratio_after": round(after.diff_ratio, 5),
        "improved": improved,
        "unchanged": same,
        "worse": worse,
        "new_regions": [{"region": r.index, "box_pt": r.box(), "diff_ratio": round(r.diff_ratio, 4)} for r in new],
        "regression": bool(worse or big_new or after.diff_ratio > before.diff_ratio * 1.05),
    }


def write_evidence(page_dir: Path, pdf_img: np.ndarray, react_img: np.ndarray, comparison: Comparison, mask: np.ndarray | None, label: str, crop_limit: int = 40) -> tuple[dict, list[str]]:
    """Write pdf, react-<label>, side-by-side, overlay, heatmap, crops and metrics.json into the page folder."""
    import json

    page_dir.mkdir(parents=True, exist_ok=True)
    crops: list[str] = []
    _to_image(pdf_img).save(page_dir / "pdf.png")
    _to_image(react_img).save(page_dir / f"react-{label}.png")
    side_by_side([("PDF", pdf_img), (f"React {label}", react_img)], page_dir / f"pdf-vs-{label}.png")  # padded when sizes differ, never scaled
    if mask is not None:
        overlay(pdf_img, react_img, page_dir / f"overlay-{label}.png")
        heatmap(mask, pdf_img, comparison.regions, comparison.zoom, page_dir / f"heatmap-{label}.png")
        crops = crop_regions({"PDF": pdf_img, f"React {label}": react_img}, comparison.regions, comparison.zoom, page_dir / "crops" / label, limit=crop_limit)
    (page_dir / f"metrics-{label}.json").write_text(json.dumps(comparison.to_dict(), indent=2), encoding="utf-8")
    return comparison.to_dict(), crops
