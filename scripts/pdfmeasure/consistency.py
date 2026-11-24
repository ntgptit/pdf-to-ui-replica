"""Kit consistency: the same primitive must render the same on every page of a book. `check-kit.cjs` measures every `[data-kit]` instance in the
lab (all fixture pages of one book, one view); this module compares instances of the same primitive and variant:
  height, font size, the text centre inside the box, and every `[data-kit-part]` (its centre relative to the box, its height).
A spread above the tolerance (default 1 px at the measured width) is an ERROR: one pattern drawn two ways, for example an example label whose text
sits lower on one page, or a lead arrow that rides on the answer rule on one page and above it on another. Widths may vary with content.
"""
from __future__ import annotations

import json
import subprocess
import time
from collections import defaultdict
from pathlib import Path

RESULT_FILE = "consistency.json"
TOLERANCE_PX = 1.0


def _metrics(item: dict) -> dict[str, float]:
    found = {"height": item["height"], "font size": item["fontSize"]}
    if item.get("text"):
        found["text centre x"] = item["text"]["cx"]
        found["text centre y"] = item["text"]["cy"]
    for name, part in (item.get("parts") or {}).items():
        found[f"{name} centre y"] = part["cy"]
        found[f"{name} height"] = part["height"]
    return found


def evaluate(raw: dict, tolerance: float = TOLERANCE_PX) -> dict:
    groups: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for item in raw["items"]:
        groups[(item["kit"], item["variant"])].append(item)
    problems, summary = [], []
    for (kit, variant), items in sorted(groups.items()):
        name = kit + (f" ({variant})" if variant else "")
        metrics: dict[str, list[tuple[float, str]]] = defaultdict(list)
        for item in items:
            for key, value in _metrics(item).items():
                metrics[key].append((value, item["page"]))
        worst = 0.0
        for key, values in metrics.items():
            if len(values) < len(items):  # a part missing in some instances is itself a drift
                missing = sorted({i["page"] for i in items} - {page for _, page in values})
                problems.append({"level": "ERROR", "kit": name, "text": f"{name}: {key} exists on some instances only (missing on page(s) {', '.join(missing) or '?'}): the pattern is built two ways"})
                continue
            low, high = min(values), max(values)
            spread = high[0] - low[0]
            worst = max(worst, spread)
            if spread > tolerance:
                problems.append({"level": "ERROR", "kit": name, "text": f"{name}: {key} varies by {spread:.2f} px ({low[0]:.2f} on page {low[1] or '?'}, {high[0]:.2f} on page {high[1] or '?'}): one pattern must render the same everywhere"})
        summary.append({"kit": name, "instances": len(items), "pages": sorted({i["page"] for i in items}, key=lambda p: (len(p), p)), "worst_spread_px": round(worst, 2)})
    return {"created": time.time(), "verdict": "ERROR" if problems else ("PASS" if raw["items"] else "ERROR"), "problems": problems or ([] if raw["items"] else [{"level": "ERROR", "kit": "-", "text": "no [data-kit] element found: primitives must carry data-kit"}]),
            "summary": summary, "tolerance_px": tolerance, "width": raw.get("width"), "view": raw.get("view")}


def to_markdown(result: dict) -> str:
    lines = [f"# Kit consistency ({result.get('view')} view at {result.get('width')} px, tolerance {result['tolerance_px']} px)", "", f"**Verdict: {result['verdict']}**", "",
             "| Primitive | Instances | Pages | Worst spread px |", "|---|---|---|---|"]
    lines += [f"| {s['kit']} | {s['instances']} | {', '.join(s['pages'])} | {s['worst_spread_px']} |" for s in result["summary"]]
    if result["problems"]:
        lines += ["", "## Problems", ""] + [f"- {p['text']}" for p in result["problems"][:60]]
    return "\n".join(lines) + "\n"


def read_result(output: str | Path) -> dict | None:
    path = Path(output) / RESULT_FILE
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def command_consistency(args) -> int:
    scripts = Path(__file__).resolve().parent.parent
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    raw_path = output / "consistency-raw.json"
    run = subprocess.run(["node", str(scripts / "check-kit.cjs"), args.url, str(raw_path), "--width", str(args.width), "--view", args.view], capture_output=True, text=True, check=False)
    if run.returncode != 0:
        print(f"consistency: the browser check failed:\n{run.stderr.strip()[-800:]}")
        return 2
    result = evaluate(json.loads(raw_path.read_text(encoding="utf-8")), args.tolerance)
    (output / RESULT_FILE).write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    (output / "consistency.md").write_text(to_markdown(result), encoding="utf-8")
    print(to_markdown(result))
    return 1 if result["verdict"] == "ERROR" else 0


def register(add) -> None:
    cmd = add("consistency", command_consistency, "the same kit primitive must render the same on every page: compare every [data-kit] instance of the lab")
    cmd.add_argument("--output", required=True)
    cmd.add_argument("--url", required=True, help="the lab page showing the book's fixture pages (each with data-page)")
    cmd.add_argument("--view", default="sheet", choices=["sheet", "reading"])
    cmd.add_argument("--width", type=int, default=1280)
    cmd.add_argument("--tolerance", type=float, default=TOLERANCE_PX)
