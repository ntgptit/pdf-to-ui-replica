"""Command line: `python3 -m pdfmeasure <command> ...` from the skill's scripts/ folder (see SKILL.md for the workflow)."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent


def parse_pages(spec: str) -> list[int]:
    """'9-12,43' -> [9, 10, 11, 12, 43]."""
    pages: list[int] = []
    for part in spec.split(","):
        if "-" in part:
            first, last = part.split("-")
            pages.extend(range(int(first), int(last) + 1))
            continue
        pages.append(int(part))
    return pages


def page_width(pdf: str, page: int) -> float:
    import pdfplumber

    with pdfplumber.open(pdf) as document:
        return float(document.pages[page - 1].width)


# ---- inspection ---------------------------------------------------------------------------------------------------------------------------
def command_shapes(args: argparse.Namespace) -> int:
    from .shapes import read_pages

    for page in read_pages(args.pdf, parse_pages(args.pages)):
        print(f"== PDF page {page.number}: {page.width:.3f} x {page.height:.3f} pt")
        for shape in sorted(page.shapes if args.glyphs else page.structural, key=lambda item: (round(item.top), item.x0)):
            print(json.dumps(shape.describe(), ensure_ascii=False))
    return 0


def command_signatures(args: argparse.Namespace) -> int:
    from .shapes import read_pages
    from .signatures import collect, page_ranges

    for group in collect(read_pages(args.pdf, parse_pages(args.pages)), include_glyphs=args.glyphs):
        kind, fill, stroke, linewidth, width_class, height_class = group.key
        example = group.examples[0]
        print(
            f"{kind:5} fill={fill or '-':7} stroke={stroke or '-':7} lw={linewidth:<5} {width_class:5}/{height_class:4} "
            f"x{group.count:<4} pages {page_ranges(group.pages)}  e.g. p{example.page} bbox=({example.x0:.0f},{example.top:.0f})-({example.x1:.0f},{example.bottom:.0f})"
        )
    return 0


def command_lines(args: argparse.Namespace) -> int:
    from .shapes import read_pages
    from .textlines import text_lines

    for page in read_pages(args.pdf, parse_pages(args.pages)):
        print(f"== PDF page {page.number}")
        previous = None
        for line in text_lines(page):
            info = line.describe()
            pitch = "" if previous is None else f"  pitch {line.top - previous:5.1f}"
            print(f"top {info['top']:6.1f} bottom {info['bottom']:6.1f} ink_h {info['bottom'] - info['top']:5.1f} x {info['x0']:6.1f}-{info['x1']:6.1f} glyphs {info['glyphs']:3} {info['fill']}{pitch}")
            previous = line.top
    return 0


# ---- template analysis --------------------------------------------------------------------------------------------------------------------
def command_roles(args: argparse.Namespace) -> int:
    from .roles import describe, extract_roles, load_rules
    from .shapes import read_pages

    rules = load_rules(args.rules)
    out = {str(page.number): describe(extract_roles(page, rules, args.first_side)) for page in read_pages(args.pdf, parse_pages(args.pages))}
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


def command_report(args: argparse.Namespace) -> int:
    from .report import invariants, load_quantities, to_markdown
    from .roles import load_rules
    from .shapes import read_pages

    pages = parse_pages(args.pages)
    rows = invariants(read_pages(args.pdf, pages), load_rules(args.rules), load_quantities(args.quantities), args.first_side)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(to_markdown(rows, args.title, f"the vector shapes of PDF pages {pages[0]}-{pages[-1]} ({len(pages)} pages)"), encoding="utf-8")
    out.with_suffix(".json").write_text(json.dumps(rows, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {out} and {out.with_suffix('.json')}: {len(rows)} quantities from {len(pages)} pages")
    return 0


def command_palette(args: argparse.Namespace) -> int:
    from .palette import measured_colours, palette_css
    from .shapes import read_pages

    colours = measured_colours(read_pages(args.pdf, parse_pages(args.pages)), args.rules, args.first_side)
    Path(args.out).write_text(palette_css(colours, args.selector, args.header), encoding="utf-8")
    print(f"wrote {args.out}: {len(colours)} colours")
    return 0


# ---- rebuilt page against the PDF ------------------------------------------------------------------------------------------------------------
def run_compare(pdf: str, page_number: int, rules_path: str, checks_path: str, dom_dir: str, first_side: str) -> tuple[str, bool]:
    from .compare import Dom, run_checks, to_markdown
    from .roles import load_rules
    from .shapes import read_pages

    page = read_pages(pdf, [page_number])[0]
    metrics = run_checks(json.loads(Path(checks_path).read_text(encoding="utf-8")), page, load_rules(rules_path), Dom(dom_dir), first_side)
    return to_markdown(f"PDF page {page_number} vs the rebuilt page", metrics), all(metric.ok for metric in metrics)


def command_compare(args: argparse.Namespace) -> int:
    report, ok = run_compare(args.pdf, args.page, args.rules, args.checks, args.dom, args.first_side)
    print(report)
    if args.out:
        Path(args.out).write_text(report, encoding="utf-8")
    return 0 if ok else 1


def run_zoom(pdf: str, page_number: int, parts_path: str, url: str, sheet: int, images: Path, attr: str, sheet_selector: str | None, zoom_px: int, css_per_pt: float, image_link: str | None = None) -> tuple[str, bool]:
    from PIL import Image

    from . import zoom

    zoom.set_zoom(zoom_px)
    parts = zoom.load_parts(parts_path)
    images.mkdir(parents=True, exist_ok=True)
    command = ["node", str(SCRIPTS / "crop-dom.cjs"), url, str(images), "--page-width-pt", str(page_width(pdf, page_number)), "--sheet", str(sheet), "--zoom", str(zoom_px), "--css-per-pt", str(css_per_pt), "--attr", attr]
    if sheet_selector:
        command += ["--sheet-selector", sheet_selector]
    subprocess.run(command, check=True, stdout=subprocess.DEVNULL)
    Image.MAX_IMAGE_PIXELS = None
    lab_sheet = zoom.load(images / "sheet-zoom.png")
    results = []
    for part in parts:
        pdf_image = zoom.load(zoom.crop_pdf(pdf, page_number, part, images))
        lab_image = zoom.crop_lab(lab_sheet, part)
        Image.fromarray(lab_image.astype("uint8")).save(images / f"lab-{part.name}.png")
        results.append(zoom.compare_part(part, pdf_image, lab_image))
        zoom.triptych(pdf_image, lab_image, part, images / f"zoom-{part.name}.png")
    for leftover in [images / "sheet-zoom.png", *images.glob("lab-*.png")]:  # keep only the PDF | rebuilt | difference images
        leftover.unlink(missing_ok=True)
    for leftover in images.glob("pdf-*.png"):
        leftover.unlink(missing_ok=True)
    return zoom.to_markdown(f"PDF page {page_number} vs the rebuilt page (sheet {sheet}), part by part", results, image_link), all(not result.problems for result in results)


def command_zoom(args: argparse.Namespace) -> int:
    images = Path(args.images) if args.images else Path(tempfile.mkdtemp(prefix="pdf-zoom-"))
    report, ok = run_zoom(args.pdf, args.page, args.parts, args.url, args.sheet, images, args.attr, args.sheet_selector, args.zoom, args.css_per_pt)
    print(report)
    print(f"images (PDF | rebuilt | difference) in {images}")
    if args.out:
        Path(args.out).write_text(report, encoding="utf-8")
    return 0 if ok else 1


LAYERS = ("checks", "parts", "text_layout")


def run_text_layout(pdf: str, page_number: int, cfg: dict, url: str, sheet: int, images: Path, attr: str, sheet_selector: str | None, css_per_pt: float) -> tuple[str, bool]:
    """Every text line of the PDF page against every text line of the rebuilt sheet: left edges, tops, bottoms, line pitch (see textlayout.py)."""
    from . import textlayout, visual

    zoom_px = int(cfg.get("zoom", 6))
    images.mkdir(parents=True, exist_ok=True)
    pdf_path = visual.render_pdf_page(pdf, page_number, images / f"pdf-{page_number}.png", zoom_px)
    react_path = visual.capture_react(url, images, page_width(pdf, page_number), sheet, zoom_px, attr, sheet_selector, css_per_pt)
    pdf_segs = textlayout.segments(visual.load_rgb(pdf_path), zoom_px, cfg)
    react_segs = textlayout.segments(visual.load_rgb(react_path), zoom_px, cfg)
    for leftover in (pdf_path, react_path):
        leftover.unlink(missing_ok=True)
    result = textlayout.compare(pdf_segs, react_segs, cfg)
    return textlayout.to_markdown(f"PDF page {page_number}: text lines (left edge, top, bottom, line pitch)", result), result["ok"]


def command_text_layout(args: argparse.Namespace) -> int:
    cfg = json.loads(Path(args.config).read_text(encoding="utf-8")) if args.config else {}
    images = Path(tempfile.mkdtemp(prefix="pdf-textlayout-"))
    report, ok = run_text_layout(args.pdf, args.page, cfg, args.url, args.sheet, images, args.attr, args.sheet_selector, args.css_per_pt)
    print(report)
    return 0 if ok else 1


def validate_layers(entry: dict) -> dict:
    """The layers a page skips on purpose. Every layer (checks, parts, text_layout) must be present or skipped with a reason; not all may be skipped."""
    page = entry.get("pdf_page")
    skipped = entry.get("skip", {})
    if not isinstance(skipped, dict) or set(skipped) - set(LAYERS):
        raise SystemExit(f"verify: page {page}: \"skip\" must be an object with only the keys {', '.join(LAYERS)}")
    for layer, reason in skipped.items():
        if not isinstance(reason, str) or not reason.strip():
            raise SystemExit(f"verify: page {page}: skipping \"{layer}\" needs a reason")
    for layer in LAYERS:
        if layer not in entry and layer not in skipped:
            raise SystemExit(f"verify: page {page} has no \"{layer}\"; add it, or skip it on purpose with \"skip\": {{\"{layer}\": \"<reason>\"}}")
        if layer in entry and layer in skipped:
            raise SystemExit(f"verify: page {page} both has and skips \"{layer}\"")
    if len(skipped) == len(LAYERS):
        raise SystemExit(f"verify: page {page} skips every layer, so nothing would be verified")
    return skipped


def command_verify(args: argparse.Namespace) -> int:
    """Both layers for every page of a verify.json: geometry/colour against the PDF vectors, then part by part at high zoom."""
    config_path = Path(args.config)
    config = json.loads(config_path.read_text(encoding="utf-8"))
    base = config_path.parent
    url = args.url or config["url"]
    attr = config.get("attr", "data-wb")
    selector = config.get("sheet_selector")
    rules = str(base / config["rules"])
    first_side = config.get("first_side", "left")
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    geometry_lines = [f"# {config.get('title', 'Rebuilt page vs PDF')}: geometry and colour", "", "Generated by `verify`. Do not edit by hand. Units: points.", ""]
    zoom_lines = [f"# {config.get('title', 'Rebuilt page vs PDF')}: parts at {config.get('zoom', 12)} px per point", "", "Generated by `verify`. Do not edit by hand. Each image: PDF | rebuilt | difference (red only in the PDF, blue only in the rebuilt page).", ""]
    layout_lines = [f"# {config.get('title', 'Rebuilt page vs PDF')}: text layout of every line", "", "Generated by `verify`. Do not edit by hand. Units: points.", ""]
    status = 0
    if not config.get("pages"):
        raise SystemExit("verify: the config lists no pages, so nothing would be verified")
    css_per_pt = float(config.get("css_per_pt", 8))
    with tempfile.TemporaryDirectory(prefix="pdf-verify-") as work:
        for entry in config["pages"]:
            skipped = validate_layers(entry)
            for layer, reason in skipped.items():
                {"checks": geometry_lines, "parts": zoom_lines, "text_layout": layout_lines}[layer].append(f"## PDF page {entry['pdf_page']}: SKIPPED {layer} ({reason})\n")
            page, sheet = entry["pdf_page"], entry["sheet"]
            if "checks" in entry:
                dom_dir = Path(work) / f"dom-{page}-{sheet}"
                command = ["node", str(SCRIPTS / "measure-dom.cjs"), url, str(dom_dir), "--page-width-pt", str(page_width(args.pdf, page)), "--sheet", str(sheet), "--dpr", "4", "--width", str(round(page_width(args.pdf, page) * float(config.get("geometry_css_per_pt", css_per_pt)))), "--attr", attr]
                if selector:
                    command += ["--sheet-selector", selector]
                subprocess.run(command, check=True, stdout=subprocess.DEVNULL)
                report, ok = run_compare(args.pdf, page, rules, str(base / entry["checks"]), str(dom_dir), first_side)
                geometry_lines.append(report)
                status |= 0 if ok else 1
            if "text_layout" in entry:
                report, ok = run_text_layout(args.pdf, page, entry["text_layout"], url, sheet, out / "images" / f"layout-p{page}-s{sheet}", attr, selector, css_per_pt)
                layout_lines.append(report)
                status |= 0 if ok else 1
            if "parts" in entry:
                report, ok = run_zoom(args.pdf, page, str(base / entry["parts"]), url, sheet, out / "images" / f"p{page}-s{sheet}", attr, selector, config.get("zoom", 12), css_per_pt, f"images/p{page}-s{sheet}")
                zoom_lines.append(report)
                status |= 0 if ok else 1
    (out / "geometry.md").write_text("\n".join(geometry_lines), encoding="utf-8")
    (out / "zoom.md").write_text("\n".join(zoom_lines), encoding="utf-8")
    (out / "text-layout.md").write_text("\n".join(layout_lines), encoding="utf-8")
    print(f"wrote {out / 'geometry.md'}, {out / 'zoom.md'} and {out / 'text-layout.md'}")
    return status


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="pdfmeasure")
    commands = parser.add_subparsers(dest="command", required=True)

    def add(name: str, handler, help_text: str) -> argparse.ArgumentParser:
        command = commands.add_parser(name, help=help_text)
        command.set_defaults(handler=handler)
        return command

    for name, handler, help_text in (("shapes", command_shapes, "dump the structural shapes of pages (JSON lines)"), ("signatures", command_signatures, "group shapes by look across pages to find the recurring components"), ("lines", command_lines, "rebuild the text lines of pages from glyph outlines (ink boxes, line pitch)")):
        command = add(name, handler, help_text)
        command.add_argument("--pdf", required=True)
        command.add_argument("--pages", required=True, help="e.g. 9-12,43")
        command.add_argument("--glyphs", action="store_true", help="include glyph-sized shapes (letters)")

    roles = add("roles", command_roles, "the shapes of each page that match the roles of a rules file (JSON)")
    roles.add_argument("--pdf", required=True)
    roles.add_argument("--pages", required=True)
    roles.add_argument("--rules", required=True)
    roles.add_argument("--first-side", choices=["left", "right"], default="left")

    report = add("report", command_report, "invariants of the template across pages (min / max / median / spread)")
    report.add_argument("--pdf", required=True)
    report.add_argument("--pages", required=True)
    report.add_argument("--rules", required=True)
    report.add_argument("--quantities", required=True)
    report.add_argument("--out", required=True, help="markdown file; a .json copy is written beside it")
    report.add_argument("--title", default="Measured template invariants")
    report.add_argument("--first-side", choices=["left", "right"], default="left")

    palette = add("palette", command_palette, "write the measured colours as CSS custom properties")
    palette.add_argument("--pdf", required=True)
    palette.add_argument("--pages", required=True)
    palette.add_argument("--rules", required=True)
    palette.add_argument("--out", required=True)
    palette.add_argument("--selector", default=":root")
    palette.add_argument("--header", default="GENERATED by pdfmeasure palette: colours measured from the PDF. Do not edit by hand.")
    palette.add_argument("--first-side", choices=["left", "right"], default="left")

    compare = add("compare", command_compare, "geometry and colour of a measured page (measure-dom.cjs output) against a PDF page")
    compare.add_argument("--pdf", required=True)
    compare.add_argument("--page", type=int, required=True)
    compare.add_argument("--rules", required=True)
    compare.add_argument("--checks", required=True)
    compare.add_argument("--dom", required=True, help="directory with dom.json")
    compare.add_argument("--out")
    compare.add_argument("--first-side", choices=["left", "right"], default="left")

    zoom_command = add("zoom", command_zoom, "compare parts of a rebuilt page with the same parts of a PDF page at 12 px per point")
    zoom_command.add_argument("--pdf", required=True)
    zoom_command.add_argument("--page", type=int, required=True)
    zoom_command.add_argument("--parts", required=True, help="JSON list of parts (see references/config-reference.md)")
    zoom_command.add_argument("--url", required=True)
    zoom_command.add_argument("--sheet", type=int, default=0)
    zoom_command.add_argument("--images", help="directory for the crops and PDF | rebuilt | difference images")
    zoom_command.add_argument("--out")
    zoom_command.add_argument("--attr", default="data-wb")
    zoom_command.add_argument("--sheet-selector")
    zoom_command.add_argument("--zoom", type=int, default=12)
    zoom_command.add_argument("--css-per-pt", type=float, default=8)

    tl = add("text-layout", command_text_layout, "every text line of a PDF page against the rebuilt page: left edge, top, bottom, line pitch")
    tl.add_argument("--pdf", required=True)
    tl.add_argument("--page", type=int, required=True)
    tl.add_argument("--url", required=True)
    tl.add_argument("--sheet", type=int, default=0)
    tl.add_argument("--config", help="JSON: tolerance_left, tolerance_vertical, tolerance_pitch, regions [[x, top, w, h]], colours, zoom")
    tl.add_argument("--attr", default="data-wb")
    tl.add_argument("--sheet-selector")
    tl.add_argument("--css-per-pt", type=float, default=8)

    verify = add("verify", command_verify, "run every layer (checks, parts, text_layout) for every page listed in a verify.json")
    verify.add_argument("--config", required=True)
    verify.add_argument("--pdf", required=True)
    verify.add_argument("--url")
    verify.add_argument("--out", required=True, help="directory for geometry.md and zoom.md")

    from . import artwork, consistency, knowhow, qa_cli, reflow, state_cli, structure, tiles, typography

    qa_cli.register(add)
    state_cli.register(add)
    tiles.register(add)
    typography.register(add)
    artwork.register(add)
    reflow.register(add)
    structure.register(add)
    knowhow.register(add)
    consistency.register(add)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.handler(args)


if __name__ == "__main__":
    sys.exit(main())
