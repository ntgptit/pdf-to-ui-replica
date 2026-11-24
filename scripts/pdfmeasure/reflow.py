"""Reading view on phones ("reflowable"): the print-sheet view is for matching the PDF and is not readable at 360 px (body text shrinks to a few
pixels). A second view of the same content model stacks the blocks vertically in reading order with real font sizes. This module judges it from the
numbers `check-reflow.cjs` measures in a real browser at several widths:
  ERROR    horizontal scroll; body text under 16 px; small text (caption, label, ruby) under 14 px; a target under 24 px (WCAG 2.5.8);
           zoom disabled; a content block of the print view missing; blocks out of reading order; a picture wider than the screen
  WARNING  a body line longer than about 75 characters (> 40 em); a target under 44 px (comfort size; a project rule may set its own list);
           a block only in the reading view
The print view's smallest body text at phone width is reported too: when it is under 12 px the phone must open the reading view by default.
Project-neutral: the page only has to mark content blocks with `data-block` and, where useful, text with `data-text-role`.
"""
from __future__ import annotations

import json
import re
import subprocess
import time
from pathlib import Path

RESULT_FILE = "reflow.json"
DEFAULTS = {"desktop_view": "sheet", "phone_view": "reading", "body_min_px": 16, "small_min_px": 14, "target_error_px": 24, "target_warn_px": 44, "line_max_em": 40, "fixed_readable_px": 12}
SMALL_ROLES = ("caption", "label", "ruby")
SKIPPED_ROLES = ("decorative",)
WIDTHS = (320, 360, 390, 768)


def _level(problems: list[dict]) -> str:
    return "ERROR" if any(p["level"] == "ERROR" for p in problems) else "WARNING" if problems else "PASS"


def evaluate(raw: dict, cfg: dict | None = None) -> dict:
    """Judge the measurements of every width. Returns per-width problems, the verdict and the print view's readability."""
    cfg = {**DEFAULTS, **(cfg or {})}
    problems: list[dict] = []
    add = lambda level, width, text: problems.append({"level": level, "width": width, "text": text})  # noqa: E731
    reference = (raw.get("fixed") or {}).get("blocks") or []
    for width_key, data in sorted(raw["widths"].items(), key=lambda item: int(item[0])):
        width = int(width_key)
        if data["scrollWidth"] > data["innerWidth"] + 1:
            add("ERROR", width, f"horizontal scroll: content is {data['scrollWidth']} px wide in a {data['innerWidth']} px screen")
        viewport = data.get("viewport", "").replace(" ", "").lower()
        scale = re.search(r"maximum-scale=([\d.]+)", viewport)
        if "user-scalable=no" in viewport or "user-scalable=0" in viewport or (scale and float(scale.group(1)) < 2):
            add("ERROR", width, f"zoom is disabled by the viewport meta ({data.get('viewport')}): readers must be able to enlarge text")
        for text in data["texts"]:
            if text["role"] in SKIPPED_ROLES:
                continue
            minimum = cfg["small_min_px"] if text["role"] in SMALL_ROLES else cfg["body_min_px"]
            if text["px"] + 0.01 < minimum:
                add("ERROR", width, f"{text['role']} text {text['px']:g} px (min {minimum}) in block {text['block'] or '?'}: {text['text']!r}")
            elif text["role"] == "body" and text["px"] and text["width"] / text["px"] > cfg["line_max_em"]:
                add("WARNING", width, f"line of {text['width'] / text['px']:.0f} em in block {text['block'] or '?'} (keep body lines under ~{cfg['line_max_em']} em, about 75 characters)")
        for target in data["targets"]:
            short = min(target["width"], target["height"])
            if short + 0.01 < cfg["target_error_px"]:
                add("ERROR", width, f"{target['tag']} {target['label']!r} is {target['width']:.0f}×{target['height']:.0f} px (min {cfg['target_error_px']})")
            elif short + 0.01 < cfg["target_warn_px"]:
                add("WARNING", width, f"{target['tag']} {target['label']!r} is {target['width']:.0f}×{target['height']:.0f} px (comfortable {cfg['target_warn_px']})")
        for item in data["media"]:
            if item["left"] < -1 or item["right"] > data["innerWidth"] + 1:
                add("ERROR", width, f"{item['tag']} in block {item['block'] or '?'} runs off the screen ({item['left']:.0f}..{item['right']:.0f} px)")
        if reference:
            blocks = data["blocks"]
            missing = [b for b in reference if b not in blocks]
            extra = [b for b in blocks if b not in reference]
            if missing:
                add("ERROR", width, f"blocks of the print view missing in the reading view: {', '.join(missing[:12])}")
            if extra:
                add("WARNING", width, f"blocks only in the reading view: {', '.join(extra[:12])}")
            common = [b for b in blocks if b in reference]
            expected = [b for b in reference if b in blocks]
            if common != expected:
                first = next(i for i, (a, b) in enumerate(zip(common, expected)) if a != b)
                add("ERROR", width, f"reading order differs from the content order at block {common[first]!r} (expected {expected[first]!r})")
    for width_key, data in sorted((raw.get("auto") or {}).items(), key=lambda item: int(item[0])):
        width = int(width_key)
        expected = cfg["phone_view"] if width < 768 else cfg["desktop_view"]
        if data.get("view") != expected:
            add("ERROR", width, f"auto view: the page opens the {data.get('view') or 'unmarked'} view at {width} px, expected {expected} (desktop and mobile are both required)")
        if data["scrollWidth"] > data["innerWidth"] + 1:
            add("ERROR", width, f"auto view: horizontal scroll at {width} px ({data['scrollWidth']} px of content)")
    fixed = raw.get("fixed")
    fixed_smallest = None
    if fixed:
        body = [t["px"] for t in fixed["texts"] if t["role"] not in SMALL_ROLES + SKIPPED_ROLES]
        fixed_smallest = min(body) if body else None
    return {
        "created": time.time(), "verdict": _level(problems), "problems": problems, "widths": sorted(int(w) for w in raw["widths"]), "settings": cfg,
        "fixed_body_px_at_phone": fixed_smallest,
        "phone_default": "reading" if fixed_smallest is None or fixed_smallest < cfg["fixed_readable_px"] else "either",
        "auto_checked": bool(raw.get("auto")), "auto": raw.get("auto") or {},
    }


def to_markdown(page: int, result: dict) -> str:
    lines = [f"# Reading view (reflow): page {page}", "", f"**Verdict: {result['verdict']}** at {', '.join(map(str, result['widths']))} px."]
    if result["fixed_body_px_at_phone"] is not None:
        lines.append(f"Print view at {result['widths'][0]} px: smallest body text {result['fixed_body_px_at_phone']:.1f} px → phones open the **{result['phone_default']}** view by default.")
    for level in ("ERROR", "WARNING"):
        grouped: dict[str, list[int]] = {}
        for p in result["problems"]:
            if p["level"] == level:
                grouped.setdefault(p["text"], []).append(p["width"])
        if grouped:  # the same problem at several widths is one line
            lines += ["", f"## {level} ({len(grouped)})", ""] + [f"- {', '.join(map(str, widths))} px: {text}" for text, widths in list(grouped.items())[:60]]
    if result["verdict"] == "PASS":
        lines += ["", "- no problem at any width"]
    return "\n".join(lines) + "\n"


def read_result(folder: Path) -> dict | None:
    path = folder / RESULT_FILE
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def command_reflow(args) -> int:
    scripts = Path(__file__).resolve().parent.parent
    folder = Path(args.output) / "pages" / f"page-{args.page:03d}"
    folder.mkdir(parents=True, exist_ok=True)
    raw_path = folder / "reflow-raw.json"
    command = ["node", str(scripts / "check-reflow.cjs"), args.url, str(raw_path), "--widths", args.widths, "--shots", str(folder)]
    if args.fixed_url:
        command += ["--fixed-url", args.fixed_url]
    if args.auto_url:
        command += ["--auto-url", args.auto_url]
    run = subprocess.run(command, capture_output=True, text=True, check=False)
    if run.returncode != 0:
        print(f"reflow: the browser check failed:\n{run.stderr.strip()[-800:]}")
        return 2
    cfg = json.loads(Path(args.config).read_text(encoding="utf-8")) if args.config else {}
    result = evaluate(json.loads(raw_path.read_text(encoding="utf-8")), cfg)
    (folder / RESULT_FILE).write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    (folder / "reflow.md").write_text(to_markdown(args.page, result), encoding="utf-8")
    print(to_markdown(args.page, result))
    print(f"reflow: screenshots {folder}/reflow-<width>.png: look at them (layout, order, art scale) before recording `state view`")
    return 1 if result["verdict"] == "ERROR" else 0


def register(add) -> None:
    cmd = add("reflow", command_reflow, "reading view on phones: overflow, text sizes, targets, zoom, block parity and order at 320/360/390/768 px (PASS / WARNING / ERROR)")
    cmd.add_argument("--output", required=True)
    cmd.add_argument("--page", type=int, required=True)
    cmd.add_argument("--url", required=True, help="the reading (reflow) view of the page")
    cmd.add_argument("--fixed-url", help="the print-sheet view of the same page: block parity, order and its readability at phone width")
    cmd.add_argument("--auto-url", help="the page as readers open it (view chosen automatically): reading at 360 px, sheet at 1280 and 1920 px")
    cmd.add_argument("--widths", default=",".join(map(str, WIDTHS)))
    cmd.add_argument("--config", help="JSON overriding body_min_px, small_min_px, target_error_px, target_warn_px, line_max_em, fixed_readable_px")
