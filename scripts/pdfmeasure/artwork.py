"""Artwork handoff: the book's drawings (characters, objects, scenes) are not traced or copied. They are described (measured box, palette, context,
identity, action, states, the people in them), turned into a prompt for another agent that draws original artwork, delivered on a separate branch,
then checked and fitted into the rebuilt pages. Project-neutral: nothing here assumes a framework, a CSS library or a folder layout.

Flow (commands of `artwork`):
  brief   inventory rows whose Approach is `artwork` -> <output>/artwork/briefs.json: measured fields filled (box, aspect, minimum size, palette
          without the paper colour, skin-colour candidates), descriptive fields empty
  (agent) look at the high-zoom tiles; fill the set-level `common` fields once and every object's fields
  prompt  refuses an incomplete or contradictory brief; writes <output>/artwork/prompt.md in the brief's language (vi or en)
  import  reads the delivery branch without checking it out, validates every file, copies the good ones to --dest, writes artwork-map.json
  status  what is briefed, delivered, missing
"""
from __future__ import annotations

import io
import json
import math
import re
import subprocess
import time
from pathlib import Path

ARTWORK_DIR = "artwork"
BRIEFS = "briefs.json"
MAP = "artwork-map.json"
DELIVERY_ROOT = "artwork-delivery"
FORMATS = (".webp", ".svg", ".png")  # WebP with alpha first: small, sharp, transparent; SVG for flat vector art
THEMES = ("light", "night")  # `night` = a second file drawn for dark mode, swapped in by the app
LANGS = ("vi", "en")
MIN_PX_PER_PT = 4  # print size floor: 4 px per point (~288 dpi)
DISPLAY_LONG_PX = 1024  # screen floor: the long side of a raster must reach this, whatever the print size (pictures are shown larger than print on phones)
ASPECT_TOLERANCE = 0.03
MERGE_DISTANCE = 12  # colours closer than this on every channel are one colour (anti-aliasing shades)
PAPER_DISTANCE = 18  # colours this close to the measured paper colour are paper, not artwork
SKIN_DISTANCE = 40  # a declared skin colour must be this close to a measured colour of the area
SAME_PALETTE = 28  # mean distance of the main colours under which two pictures look alike
KINDS = ("character", "object", "scene", "decoration")
WITH_PEOPLE = ("character", "scene")
BRANCH = re.compile(r"^[A-Za-z0-9._/-]{1,120}$")
SET_ID = re.compile(r"^[a-z0-9][a-z0-9-]{0,40}$")
NAME = re.compile(r"^[a-z0-9][a-z0-9-]{0,30}$")
HEX = re.compile(r"^#[0-9a-fA-F]{6}$")
OBJ_ID = re.compile(r"^OBJ-\d+$")
UNSAFE_SVG = re.compile(r"<script|<foreignObject|<!DOCTYPE|<!ENTITY|\son[a-z]+\s*=|(?:xlink:)?href\s*=\s*[\"'](?:https?:|javascript:|data:text)", re.IGNORECASE)
# letters of scripts other than Latin: drawing them is drawing text
NON_LATIN = re.compile(r"[Ͱ-ϿЀ-ӿ֐-׿؀-ۿऀ-ॿ฀-๿ᄀ-ᇿ぀-ヿ㄰-㆏㐀-鿿가-힯]")
NUMERAL = re.compile(r"(?:\bnumber|\bdigit|\bnumeral|\bchiffre|\bzahl|chữ số|con số|\bsố|숫자|数字)\s*\d", re.IGNORECASE)
COPY_PHRASES = ("như hình in", "như bản in", "như trong sách", "giống sách", "giống hình gốc", "giống bản gốc", "theo hình in", "đồ lại theo",
                "as printed", "as in the book", "like the book", "same as the original", "copy the", "trace the")


class ArtworkError(ValueError):
    pass


def folder(output: str | Path) -> Path:
    return Path(output) / ARTWORK_DIR


def parse_region(text: str) -> list[float]:
    numbers = [float(n) for n in re.findall(r"-?\d+(?:\.\d+)?", text)]
    if len(numbers) != 4 or numbers[2] <= 0 or numbers[3] <= 0:
        raise ArtworkError(f"region {text!r} must be 'x, top, w, h' in points")
    return numbers


def _rgb(hex_colour: str) -> tuple[int, int, int]:
    return tuple(int(hex_colour[i : i + 2], 16) for i in (1, 3, 5))


def _distance(a: str, b: str) -> int:
    return max(abs(x - y) for x, y in zip(_rgb(a), _rgb(b)))


# ---- measuring -----------------------------------------------------------------------------------------------------------------------------
def paper_colour(image) -> str:
    """The page's paper: median of the outer 3 % of the page on every side (printed pages are rarely pure white)."""
    import numpy as np

    array = np.asarray(image.convert("RGB"))
    edge = max(2, int(min(array.shape[:2]) * 0.03))
    border = np.concatenate([array[:edge].reshape(-1, 3), array[-edge:].reshape(-1, 3), array[:, :edge].reshape(-1, 3), array[:, -edge:].reshape(-1, 3)])
    return "#%02x%02x%02x" % tuple(int(v) for v in np.median(border, axis=0))


def palette(image, box_pt: list[float], zoom: int, paper: str = "#ffffff", colours: int = 6) -> list[dict]:
    """Main colours of the area without paper, as sRGB hex with their share; anti-aliasing shades are merged into their colour."""
    from PIL import Image

    x, top, width, height = (round(v * zoom) for v in box_pt)
    crop = image.crop((x, top, x + width, top + height)).convert("RGB")
    quantised = crop.quantize(colors=max(12, colours * 2), method=Image.Quantize.MEDIANCUT)
    lookup = quantised.getpalette()
    found: list[list] = []  # [count, hex]
    for count, index in sorted(quantised.getcolors() or [], reverse=True):
        colour = "#%02x%02x%02x" % tuple(lookup[index * 3 : index * 3 + 3])
        if min(_rgb(colour)) >= 240 or _distance(colour, paper) <= PAPER_DISTANCE:
            continue
        near = next((item for item in found if _distance(item[1], colour) <= MERGE_DISTANCE), None)
        if near:
            near[0] += count
            continue
        found.append([count, colour])
    found.sort(key=lambda item: -item[0])
    total = sum(count for count, _ in found) or 1
    return [{"hex": colour, "share": round(count / total, 3)} for count, colour in found[:colours]]


def skin_candidates(colours: list[dict]) -> list[str]:
    """Colours of the area that could be skin, light to dark (warm, R >= G >= B). Hints only: the agent confirms on the face."""
    found = []
    for colour in colours:
        r, g, b = _rgb(colour["hex"])
        if r >= g >= b and r >= 60 and 10 <= r - b <= 150 and g - b <= 100:
            found.append(colour["hex"])
    return sorted(found, key=lambda h: -sum(_rgb(h)))


def min_px(box: list[float]) -> list[int]:
    """Minimum raster size: 4 px/pt of the print box, and the long side at least DISPLAY_LONG_PX (screens show pictures larger than print)."""
    width, height = box[2] * MIN_PX_PER_PT, box[3] * MIN_PX_PER_PT
    scale = max(1.0, DISPLAY_LONG_PX / max(width, height))
    return [math.ceil(width * scale), math.ceil(height * scale)]


# ---- brief ---------------------------------------------------------------------------------------------------------------------------------
def make_briefs(rows: list[dict], pdf_images: dict[int, object], zoom: int, set_id: str, lang: str = "vi") -> dict:
    """Measured part of every brief. Descriptive fields stay empty for the agent to fill from the tiles."""
    if not SET_ID.match(set_id):
        raise ArtworkError("set id: lower-case letters, digits and dashes (it names the delivery folder and branch)")
    if lang not in LANGS:
        raise ArtworkError(f"lang must be one of {LANGS}")
    papers = {page: paper_colour(image) for page, image in pdf_images.items()}
    objects = []
    for row in rows:
        box, page = parse_region(row["region"]), int(row["page"])
        image = pdf_images.get(page)
        main = palette(image, box, zoom, papers[page]) if image is not None else []
        wide = palette(image, box, zoom, papers[page], colours=14) if image is not None else []
        objects.append({
            "id": row["id"], "page": page, "name": row["object"], "box_pt": box, "aspect": round(box[2] / box[3], 4), "min_px": min_px(box),
            "palette": main, "palette_wide": wide, "skin_candidates": skin_candidates(wide),
            "background": "transparent", "format": "webp", "themes": list(THEMES),
            "kind": "", "context": "", "identity": "", "action": "", "text_in_art": "",
            "states": [{"name": "default", "description": ""}], "layers": [], "night": "",
            "people": [], "people_none": "", "reuse_of": "", "distinct_from": [],
        })
    common = {"context": "", "style_people": "", "style_objects": "", "night": "", "avoid": ""}
    return {"set": set_id, "lang": lang, "created": time.time(), "paper": {str(k): v for k, v in papers.items()}, "common": common, "objects": objects}


def _text(value) -> str:
    return " ".join(str(value or "").split())


def _people_text(obj: dict) -> str:
    return " ".join(_text(person.get(key)) for person in obj.get("people") or [] for key in ("name", "role", "origin", "markers"))


def _descriptive(obj: dict) -> str:
    return " ".join([_text(obj.get(key)) for key in ("context", "identity", "action", "night")] + [_text(s.get("description")) for s in obj.get("states") or []] + [_people_text(obj)])


def _palette_distance(a: dict, b: dict) -> float:
    """Mean distance from each of a's three main colours to the nearest colour of b (both ways); large when either has no colours."""
    def one_way(x, y):
        main = [c["hex"] for c in x.get("palette", [])[:3]]
        other = [c["hex"] for c in y.get("palette", [])]
        return sum(min(_distance(m, o) for o in other) for m in main) / len(main) if main and other else 255.0
    return max(one_way(a, b), one_way(b, a))


def brief_problems(briefs: dict) -> list[str]:
    problems: list[str] = []
    objects = {obj["id"]: obj for obj in briefs["objects"]}
    drawn = [obj for obj in briefs["objects"] if not obj.get("reuse_of")]
    common = briefs.get("common") or {}
    if len(_text(common.get("context"))) < 10:
        problems.append("common.context: the set's shared context (book, audience, lesson) is empty; write it once there, not in every object")
    if any(obj.get("kind") in WITH_PEOPLE or obj.get("people") for obj in drawn) and len(_text(common.get("style_people"))) < 10:
        problems.append("common.style_people: the drawing style for people is empty")
    if any(obj.get("kind") in ("object", "decoration") or (obj.get("kind") == "scene") for obj in drawn) and len(_text(common.get("style_objects"))) < 10:
        problems.append("common.style_objects: the drawing style for objects and scenery is empty (kept apart from people: no faces on objects unless the brief says so)")
    if any("night" in (obj.get("themes") or []) for obj in drawn) and len(_text(common.get("night"))) < 10:
        problems.append("common.night: the rule for the dark-mode files is empty")
    for obj in briefs["objects"]:
        where = f"{obj['id']} ({obj['name']})"
        target = obj.get("reuse_of")
        if target:
            source = objects.get(target)
            if not source or source.get("reuse_of"):
                problems.append(f"{where}: reuse_of {target!r} must name an object that is drawn itself")
            elif abs(source["aspect"] - obj["aspect"]) / source["aspect"] > ASPECT_TOLERANCE:
                problems.append(f"{where}: reuse_of {target}: aspect {obj['aspect']} differs from {source['aspect']} by more than 3 % (the same file cannot fill both boxes; draw it separately)")
            continue
        problems += _object_problems(obj, where)
    problems += _cross_problems(briefs["objects"], objects)
    return problems


def _object_problems(obj: dict, where: str) -> list[str]:
    problems = []
    kind = obj.get("kind")
    if kind not in KINDS:
        problems.append(f"{where}: kind must be one of {KINDS}")
    if len(_text(obj.get("identity"))) < 10:
        problems.append(f"{where}: identity is empty or too short (what it is and what makes it recognisable, from the tiles)")
    if len(_text(obj.get("action"))) < 3:
        problems.append(f"{where}: action is empty (write `none` for a still object)")
    states = obj.get("states") or []
    names = [s.get("name", "") for s in states]
    if not names or names[0] != "default":
        problems.append(f"{where}: the first state must be 'default'")
    for state in states:
        if not NAME.match(state.get("name", "")):
            problems.append(f"{where}: state name {state.get('name')!r} must be lower-case letters, digits, dashes")
        if len(_text(state.get("description"))) < 5:
            problems.append(f"{where}: state {state.get('name')!r} needs a description (pose, expression, what changes)")
    if len(set(names)) != len(names):
        problems.append(f"{where}: state names repeat")
    themes = obj.get("themes") or []
    if "light" not in themes or any(t not in THEMES for t in themes):
        problems.append(f"{where}: themes must include 'light' and may add 'night'")
    if f".{obj.get('format', '')}" not in FORMATS:
        problems.append(f"{where}: format must be one of {', '.join(f[1:] for f in FORMATS)}")
    for layer in obj.get("layers") or []:
        if not NAME.match(layer.get("name", "")) or len(_text(layer.get("description"))) < 5:
            problems.append(f"{where}: effect layer {layer.get('name')!r} needs a lower-case name and a description (what moves, how)")
    problems += _text_problems(obj, where)
    problems += _people_problems(obj, where)
    lowered = _descriptive(obj).lower()
    for phrase in COPY_PHRASES:
        if phrase in lowered:
            problems.append(f"{where}: {phrase!r} asks for a copy of the printed drawing (the other agent has no image and must not copy); describe what is needed instead")
    return problems


def _text_problems(obj: dict, where: str) -> list[str]:
    decision = _text(obj.get("text_in_art"))
    if not decision:
        return [f"{where}: text_in_art is not decided: `none` (no letters or numerals in the picture), or `glyphs: <exact characters>` when they are the subject (a numeral, a letter on a sign). Letters a learner must read are better left out and set as real text by the app"]
    if decision.lower() == "none":
        found = sorted(set(NON_LATIN.findall(_text(obj.get("identity")) + " " + " ".join(_text(s.get("description")) for s in obj.get("states") or []))))
        problems = []
        if found:
            problems.append(f"{where}: text_in_art is `none` but the description names characters {''.join(found)}: list them with `glyphs:` or describe that area blank (text added by the app)")
        if NUMERAL.search(_text(obj.get("name")) + " " + _text(obj.get("identity"))):
            problems.append(f"{where}: text_in_art is `none` but the picture is a numeral: use `glyphs: <the digits>`")
        return problems
    if not decision.lower().startswith("glyphs:") or len(decision) <= len("glyphs:"):
        return [f"{where}: text_in_art must be `none` or `glyphs: <exact characters>`"]
    return []


def _people_problems(obj: dict, where: str) -> list[str]:
    people = obj.get("people") or []
    kind = obj.get("kind")
    problems = []
    if kind == "character" and not people:
        problems.append(f"{where}: a character needs `people` (one entry per person in the picture)")
    if kind == "scene" and not people and len(_text(obj.get("people_none"))) < 5:
        problems.append(f"{where}: a scene must list its `people` (one entry per person: teacher, each student…) or say in `people_none` why there are none")
    measured = [c["hex"] for c in obj.get("palette_wide") or obj.get("palette") or []]
    for index, person in enumerate(people, start=1):
        who = f"{where} person {index} ({person.get('name') or person.get('role') or '?'})"
        if len(_text(person.get("name")) or _text(person.get("role"))) < 2:
            problems.append(f"{who}: give a name or a role (teacher, student on the left…)")
        if len(_text(person.get("origin"))) < 3:
            problems.append(f"{who}: origin is required: the country or culture the book shows them as, with the clue (name, cast page, setting, clothes, text); `unknown: <why>` only when the page gives none")
        if len(_text(person.get("skin_tone"))) < 3:
            problems.append(f"{who}: skin_tone is required (light, medium, olive, tan, brown, dark; warm, neutral or cool undertone)")
        skin = person.get("skin_hex", "")
        if not HEX.match(skin):
            problems.append(f"{who}: skin_hex is required (#rrggbb measured on the face; see skin_candidates)")
        elif measured and min(_distance(skin, m) for m in measured) > SKIN_DISTANCE:
            problems.append(f"{who}: skin_hex {skin} is not near any colour measured in the area ({', '.join(measured[:8])}): measure it on the face in the tiles, do not guess")
    return problems


def _origin(person: dict) -> str:
    """The origin without its clue: `Korea (name in the dialogue)` and `Korea (cast page)` are the same origin."""
    return _text(str(person.get("origin", "")).split("(")[0]).lower()


def _cross_problems(all_objects: list[dict], by_id: dict[str, dict]) -> list[str]:
    problems = []
    persons: dict[str, tuple[str, dict]] = {}
    for obj in all_objects:
        for person in obj.get("people") or []:
            key = _text(person.get("name")).lower()
            if not key:
                continue
            first = persons.setdefault(key, (obj["id"], person))
            if first[1] is not person and (_origin(first[1]) != _origin(person) or str(first[1].get("skin_hex", "")).lower() != str(person.get("skin_hex", "")).lower()):
                problems.append(f"{obj['id']}: {person.get('name')!r} is also in {first[0]} with a different origin or skin_hex; one person keeps one look")
    drawn = [obj for obj in all_objects if not obj.get("reuse_of")]
    for index, a in enumerate(drawn):
        for b in drawn[index + 1 :]:
            linked = b["id"] in (a.get("distinct_from") or []) or a["id"] in (b.get("distinct_from") or [])
            if linked:
                continue
            alike = abs(a["aspect"] - b["aspect"]) / a["aspect"] <= 0.08 and _palette_distance(a, b) <= SAME_PALETTE
            same_text = _text(a.get("identity")).lower() == _text(b.get("identity")).lower() and len(_text(a.get("identity"))) >= 10
            if alike and same_text:
                problems.append(f"{a['id']} and {b['id']} are the same picture (same description, alike box and colours): draw it once, set `reuse_of: {a['id']}` on {b['id']}")
            elif alike:
                problems.append(f"{a['id']} and {b['id']} look alike (box and colours) but are described differently: check the labels on the tiles; if they are the same picture set `reuse_of`, else add the other id to `distinct_from`")
            elif same_text and _palette_distance(a, b) > 2 * SAME_PALETTE:
                problems.append(f"{a['id']} and {b['id']} have the same description but very different colours: one label is probably swapped; check both on the tiles")
    return problems


def file_name(obj_id: str, part: str, theme: str = "light", extension: str = "webp") -> str:
    """`OBJ-001--default.webp`, `OBJ-001--default-night.webp` (dark mode), `OBJ-001--layer-glow.webp` (an effect layer)."""
    return f"{obj_id}--{part}{'-night' if theme == 'night' else ''}.{extension}"


def expected_files(obj: dict) -> list[tuple[str, str]]:
    """(key, file name) of everything a drawn object needs: every state and effect layer, in every theme. A reused object needs none."""
    if obj.get("reuse_of"):
        return []
    parts = [s["name"] for s in obj["states"]] + [f"layer-{layer['name']}" for layer in obj.get("layers") or []]
    return [(f"{part}/{theme}", file_name(obj["id"], part, theme, obj.get("format", "webp"))) for part in parts for theme in obj.get("themes") or ["light"]]


def suggested_branch(set_id: str) -> str:
    return f"artwork/{set_id}-{time.strftime('%Y%m%d')}"


# ---- import --------------------------------------------------------------------------------------------------------------------------------
def _git(root: Path, *args: str, binary: bool = False):
    result = subprocess.run(["git", "-C", str(root), *args], capture_output=True, check=False)
    if result.returncode != 0:
        raise ArtworkError(f"git {' '.join(args)}: {result.stderr.decode(errors='replace').strip()[:300]}")
    return result.stdout if binary else result.stdout.decode()


def validate_file(name: str, data: bytes, obj: dict) -> list[str]:
    """Format, aspect, size, transparency and (SVG) safety of one delivered file."""
    problems = []
    suffix = Path(name).suffix.lower()
    if suffix not in FORMATS:
        return [f"{name}: format {suffix or '?'} not accepted ({', '.join(FORMATS)})"]
    if len(data) > 8 * 1024 * 1024:
        return [f"{name}: larger than 8 MB"]
    if suffix == ".svg":
        text = data.decode("utf-8", errors="replace")
        if UNSAFE_SVG.search(text):
            return [f"{name}: unsafe SVG (script, event handler, foreignObject, DOCTYPE/ENTITY or external link)"]
        match = re.search(r"viewBox\s*=\s*[\"']\s*[-\d.]+[\s,]+[-\d.]+[\s,]+([\d.]+)[\s,]+([\d.]+)", text)
        if not match:
            return [f"{name}: SVG has no viewBox"]
        aspect = float(match.group(1)) / float(match.group(2))
    else:
        from PIL import Image

        try:
            image = Image.open(io.BytesIO(data))
            image.load()
        except Exception as error:  # noqa: BLE001 - any decoder error means the file is unusable
            return [f"{name}: not a readable image ({error.__class__.__name__})"]
        width, height = image.size
        aspect = width / height
        need = obj.get("min_px") or obj.get("min_png_px")
        if width < need[0] or height < need[1]:
            problems.append(f"{name}: {width}×{height} px is under the minimum {need[0]}×{need[1]} px")
        if obj["background"] == "transparent":
            rgba = image.convert("RGBA")
            corners = [rgba.getpixel(p)[3] for p in ((0, 0), (width - 1, 0), (0, height - 1), (width - 1, height - 1))]
            if max(corners) > 16:
                problems.append(f"{name}: background is not transparent (corner alpha {max(corners)})")
    if abs(aspect - obj["aspect"]) / obj["aspect"] > ASPECT_TOLERANCE:
        problems.append(f"{name}: aspect {aspect:.3f} differs from {obj['aspect']} by more than 3 %")
    return problems


def import_delivery(root: str | Path, output: str | Path, branch: str, dest: str | Path, remote: str = "origin") -> dict:
    if not BRANCH.match(branch) or branch.startswith("-") or ".." in branch:
        raise ArtworkError(f"branch name {branch!r} is not accepted")
    root, briefs_path = Path(root), folder(output) / BRIEFS
    if not briefs_path.exists():
        raise ArtworkError("no briefs.json: run `artwork brief` first")
    briefs = json.loads(briefs_path.read_text(encoding="utf-8"))
    _git(root, "fetch", "--quiet", remote, f"refs/heads/{branch}")
    ref = "FETCH_HEAD"
    delivery = f"{DELIVERY_ROOT}/{briefs['set']}"
    listed = [line for line in _git(root, "ls-tree", "-r", "--name-only", ref, "--", delivery).splitlines() if line]
    outside = _git(root, "diff", "--name-only", f"{_git(root, 'merge-base', 'HEAD', ref).strip()}..{ref}").splitlines()
    stray = [path for path in outside if path and not path.startswith(delivery + "/")]
    manifest_path = f"{delivery}/manifest.json"
    if manifest_path not in listed:
        raise ArtworkError(f"the branch has no {manifest_path}")
    manifest = json.loads(_git(root, "show", f"{ref}:{manifest_path}"))
    dest = Path(dest)
    dest.mkdir(parents=True, exist_ok=True)
    mapping, report = {}, {"branch": branch, "accepted": [], "rejected": [], "missing": [], "stray_files": stray, "notes": manifest.get("notes", "")}
    by_stem = {Path(path).stem: path for path in listed if Path(path).suffix.lower() in FORMATS and path.count("/") == delivery.count("/") + 1}
    for obj in briefs["objects"]:
        for key, name in expected_files(obj):
            path = by_stem.get(Path(name).stem)  # the brief's format is preferred; another accepted format of the same file is taken too
            if not path:
                report["missing"].append(Path(name).stem)
                continue
            delivered_name = Path(path).name
            data = _git(root, "show", f"{ref}:{path}", binary=True)
            problems = validate_file(delivered_name, data, obj)
            if problems:
                report["rejected"] += problems
                continue
            (dest / delivered_name).write_bytes(data)
            entry = mapping.setdefault(obj["id"], {"page": obj["page"], "name": obj["name"], "box_pt": obj["box_pt"], "files": {}})
            entry["files"][key] = str(dest / delivered_name)
            report["accepted"].append(delivered_name)
    for obj in briefs["objects"]:  # a reused picture points at the drawn one's files, placed in its own box
        source = mapping.get(obj.get("reuse_of") or "")
        if source:
            mapping[obj["id"]] = {"page": obj["page"], "name": obj["name"], "box_pt": obj["box_pt"], "reuse_of": obj["reuse_of"], "files": dict(source["files"])}
    (folder(output) / MAP).write_text(json.dumps({"branch": branch, "dest": str(dest), "objects": mapping, "created": time.time()}, indent=2, ensure_ascii=False), encoding="utf-8")
    (folder(output) / "import-report.md").write_text(import_markdown(report), encoding="utf-8")
    return report


def import_markdown(report: dict) -> str:
    lines = [f"# Artwork import from `{report['branch']}`", "", f"- accepted: {len(report['accepted'])}", f"- rejected: {len(report['rejected'])}", f"- missing: {len(report['missing'])}"]
    if report["stray_files"]:
        lines.append(f"- **files changed outside the delivery folder (not imported, tell the user):** {', '.join(report['stray_files'][:20])}")
    lines += ["", "## Accepted", ""] + ([f"- {n}" for n in report["accepted"]] or ["- none"])
    lines += ["", "## Rejected (ask for a new version)", ""] + ([f"- {p}" for p in report["rejected"]] or ["- none"])
    lines += ["", "## Missing (not delivered)", ""] + ([f"- {m}" for m in report["missing"]] or ["- none"])
    if report.get("notes"):
        lines += ["", "## Notes from the delivering agent", "", str(report["notes"])]
    return "\n".join(lines) + "\n"


def page_problems(output: str | Path, page: int) -> list[str]:
    """Artwork of a page that is still missing (used by the harness). A reused picture is missing while the drawn one is."""
    path = folder(output) / BRIEFS
    if not path.exists():
        return []
    briefs = json.loads(path.read_text(encoding="utf-8"))
    by_id = {obj["id"]: obj for obj in briefs["objects"]}
    mapped = folder(output) / MAP
    objects = json.loads(mapped.read_text(encoding="utf-8"))["objects"] if mapped.exists() else {}
    problems = []
    for obj in briefs["objects"]:
        if obj["page"] != page:
            continue
        source = by_id.get(obj.get("reuse_of") or "", obj)
        got = objects.get(source["id"], {}).get("files", {})
        missing = [key for key, _ in expected_files(source) if key not in got]
        if missing:
            via = f" (reuses {source['id']})" if source is not obj else ""
            problems.append(f"artwork {obj['id']} ({obj['name']}){via} not delivered: {', '.join(missing)}: hand the prompt to the user, wait for the branch, `artwork import`")
    return problems


# ---- command -------------------------------------------------------------------------------------------------------------------------------
def command_artwork(args) -> int:
    from PIL import Image

    from . import artwork_prompt, visual
    from .ebook_state import inventory_rows

    out = folder(args.output)
    out.mkdir(parents=True, exist_ok=True)
    try:
        if args.action == "brief":
            if (out / BRIEFS).exists() and not args.force:
                raise ArtworkError("briefs.json exists (descriptions would be lost); edit it, or pass --force to start over")
            rows = [row for row in inventory_rows(args.inventory) if "artwork" in row["approach"].lower() and not row["status"].startswith("EXCLUDED")]
            if not rows:
                raise ArtworkError("no inventory row with Approach `artwork`")
            images = {}
            work = out / "_work"
            work.mkdir(exist_ok=True)
            Image.MAX_IMAGE_PIXELS = None
            for page in sorted({int(row["page"]) for row in rows}):
                images[page] = Image.open(visual.render_pdf_page(args.pdf, page, work / f"pdf-{page}.png", args.zoom)).convert("RGB")
            briefs = make_briefs(rows, images, args.zoom, args.set, args.lang)
            (out / BRIEFS).write_text(json.dumps(briefs, indent=2, ensure_ascii=False), encoding="utf-8")
            print(f"artwork: {len(rows)} brief(s) in {out / BRIEFS}. Fill `common` once, then each object (kind, identity, action, text_in_art, states, people…) from the high-zoom tiles; then `artwork prompt`.")
        elif args.action == "prompt":
            briefs = json.loads((out / BRIEFS).read_text(encoding="utf-8"))
            problems = brief_problems(briefs)
            if problems:
                print("artwork prompt: brief incomplete or contradictory\n" + "\n".join(f"- {p}" for p in problems))
                return 1
            text = artwork_prompt.render(briefs, args.branch or suggested_branch(briefs["set"]))
            (out / "prompt.md").write_text(text, encoding="utf-8")
            print(text)
            print(f"artwork: prompt written to {out / 'prompt.md'}. Send it to the user in the chat with the steps (references/11-artwork.md).")
        elif args.action == "import":
            if not args.branch or not args.dest:
                raise ArtworkError("import needs --branch (the user's delivery branch) and --dest (asset folder of the rebuild)")
            report = import_delivery(args.root, args.output, args.branch, args.dest)
            print(import_markdown(report))
            return 0 if not report["rejected"] and not report["missing"] and not report["stray_files"] else 1
        elif args.action == "status":
            briefs = json.loads((out / BRIEFS).read_text(encoding="utf-8"))
            incomplete = brief_problems(briefs)
            print(f"briefs: {len(briefs['objects'])} object(s), {'complete' if not incomplete else f'{len(incomplete)} problem(s)'}")
            for page in sorted({o["page"] for o in briefs["objects"]}):
                print(f"page {page}: " + ("; ".join(page_problems(args.output, page)) or "all artwork delivered"))
    except (ArtworkError, FileNotFoundError, json.JSONDecodeError) as error:
        print(f"artwork: {error}")
        return 2
    return 0


def register(add) -> None:
    cmd = add("artwork", command_artwork, "artwork handoff: brief (measure) | prompt (table for another agent) | import (from the delivery branch) | status")
    cmd.add_argument("action", choices=["brief", "prompt", "import", "status"])
    cmd.add_argument("--output", required=True)
    cmd.add_argument("--pdf", help="brief: the PDF (to measure the palette)")
    cmd.add_argument("--inventory", help="brief: object-inventory.md; rows with Approach `artwork` are briefed")
    cmd.add_argument("--set", default="book", help="brief: id of this artwork set (names the delivery folder and branch)")
    cmd.add_argument("--lang", choices=LANGS, default="vi", help="brief: language of the prompt (the user's language)")
    cmd.add_argument("--zoom", type=int, default=4)
    cmd.add_argument("--force", action="store_true")
    cmd.add_argument("--branch", help="prompt: branch name to suggest; import: the delivery branch the user gave")
    cmd.add_argument("--dest", help="import: asset folder of the rebuild (files are copied there)")
    cmd.add_argument("--root", default=".", help="import: repository root")
