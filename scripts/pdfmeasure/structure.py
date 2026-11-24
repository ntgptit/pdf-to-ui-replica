"""Folder architecture of the ebook module (React + shadcn/ui + Tailwind v4): shared components first, built for many books.

  core/kit/contract.ts      the list of kit primitives: the patterns every page repeats (example label, answer line with its lead arrow or speaker,
                            rule, frame, item number, table header…). One component per pattern, so a pattern cannot drift between pages.
  core/kit/reading/<p>/     the reading-view implementation of each primitive (the app's design)
  core/blocks/<kind>/       the renderer of a block kind, written once, composing kit primitives only (never drawing a label, line or arrow itself)
  books/<id>/kit/<p>/       the book's print-sheet implementation of every primitive (its measured style): <p>.tsx + <p>.css
  books/<id>/parts/<kind>/  rare: a block whose sheet structure exists only in this book; first line `// unique-structure: <reason>`

Rules (code in every message):
  L1 required files    L2 pure models    L3 folders and names    L4 inline style sets only custom properties    L5 data-block / data-kit marks
  L6 book CSS scoped to [data-book=<id>] (+ [data-view=sheet] except the palette); core CSS to a view    L7 public API    L8 fixtures
  L9 a block or part imports no other block or part    L10 no literal UI text    L11 file size    L12 generated palette
  L13 core imports no book    L14 a book imports no other book    L15 lazy registry
  L16 blocks and book parts draw nothing themselves (no <svg>, <line>, <rect>, <path>, no arrow glyphs): they use kit primitives
  L17 every primitive of the contract is implemented by the reading kit and by every book; no primitive outside the contract
  L18 a book part states why its structure is unique (`// unique-structure: <reason>` on its first line)
  L19 a series kit (books/_series/<series>/kit/) exists only when at least SERIES_MIN books use it; below that it is premature
  L20 every book's index.ts checks its definition at compile time (`satisfies BookStyle` or `defineBook(`)
"""
from __future__ import annotations

import json
import re
from pathlib import Path

DEFAULT_MAP = {"core": "core", "books": "books"}
CORE_REQUIRED = ("contracts.ts", "kit/contract.ts", "model/blocks.ts", "model/ids.ts", "model/scale.ts", "views/book-page.tsx", "views/page-view.tsx", "views/reader-view.ts")
BOOK_REQUIRED = ("index.ts", "model/tokens.ts", "styles/palette.css", "styles/sheet.css")
ROOT_REQUIRED = ("index.ts", "ebook-page.tsx")
MAX_LINES = 300
KEBAB = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
STYLE_OBJECT = re.compile(r"style=\{\{(.*?)\}\}", re.DOTALL)
STYLE_KEY = re.compile(r"(?:^|[,{])\s*(\[?\s*['\"`]?)([A-Za-z_$-][\w$-]*)['\"`]?\s*\]?\s*(?=:)")
IMPORT = re.compile(r"""(?:^\s*(?:import|export)\s[^'"]*?from\s+['"]([^'"]+)['"])|(?:\bimport\(\s*['"]([^'"]+)['"]\s*\))""", re.MULTILINE)
LITERAL_LABEL = re.compile(r"""\b(aria-label|title|alt|placeholder)=["']([^"']*[^\W\d_][^"']*)["']""")
OWN_DRAWING = re.compile(r"<(?:svg|line|rect|path|polyline|circle)\b|[→⟶➔➝]|\{\s*['\"]->['\"]\s*\}")
KIT_LIST = re.compile(r"KIT\s*=\s*\[([^\]]*)\]", re.DOTALL)
UNIQUE = re.compile(r"^\s*//\s*unique-structure:\s*(.{10,})")
TYPED_BOOK = re.compile(r"\bsatisfies\s+BookStyle\b|\bdefineBook\s*\(")
SERIES_DIR = "_series"
SERIES_MIN = 3
SOURCE = (".ts", ".tsx", ".css")


def _imports(text: str) -> list[str]:
    return [a or b for a, b in IMPORT.findall(text)]


def _lines(path: Path) -> int:
    return sum(1 for line in path.read_text(encoding="utf-8").splitlines() if line.strip())


def _is_test(path: Path) -> bool:
    return ".test." in path.name or ".spec." in path.name


def _selectors(css: str) -> list[str]:
    css = re.sub(r"/\*.*?\*/", "", css, flags=re.DOTALL)
    found = []
    for header in re.findall(r"([^{}]+)\{", css):
        header = header.strip()
        if header and not header.startswith("@"):
            found += [part.strip() for part in header.split(",") if part.strip()]
    return found


def _inside(path: Path, folder: Path) -> tuple[str, ...] | None:
    try:
        return path.resolve().relative_to(folder.resolve()).parts
    except ValueError:
        return None


def _resolved_imports(path: Path) -> list[tuple[str, Path]]:
    return [(target, (path.parent / target).resolve()) for target in _imports(path.read_text(encoding="utf-8")) if target.startswith(".")]


def _folders(path: Path) -> list[Path]:
    return sorted(p for p in path.iterdir() if p.is_dir() and p.name != "shared" and not p.name.startswith("_")) if path.is_dir() else []


def kit_primitives(core: Path) -> list[str]:
    """The primitive names declared in core/kit/contract.ts (`export const KIT = ['example-label', …] as const`)."""
    contract = core / "kit" / "contract.ts"
    if not contract.is_file():
        return []
    match = KIT_LIST.search(contract.read_text(encoding="utf-8"))
    return re.findall(r"['\"]([a-z0-9-]+)['\"]", match.group(1)) if match else []


def check(module: str | Path, mapping: dict | None = None, max_lines: int = MAX_LINES) -> list[str]:
    root = Path(module)
    names = {**DEFAULT_MAP, **(mapping or {})}
    core, books_dir = root / names["core"], root / names["books"]
    if not root.is_dir():
        return [f"L1 module folder {root} does not exist"]
    problems: list[str] = []
    for name in ROOT_REQUIRED:
        if not (root / name).is_file():
            problems.append(f"L1 {name} is missing")
    for name in CORE_REQUIRED:
        if not (core / name).is_file():
            problems.append(f"L1 {names['core']}/{name} is missing")
    if not (books_dir / "registry.ts").is_file():
        problems.append(f"L1 {names['books']}/registry.ts is missing (lazy registry of the books)")
    books = _folders(books_dir)
    if not books:
        problems.append(f"L1 {names['books']}/ has no book (one folder per book or series)")
    blocks = _folders(core / "blocks")
    if not blocks:
        problems.append(f"L1 {names['core']}/blocks/ has no block renderer")
    primitives = kit_primitives(core)
    if (core / "kit" / "contract.ts").is_file() and not primitives:
        problems.append(f"L17 {names['core']}/kit/contract.ts declares no primitive (export const KIT = ['example-label', …] as const)")

    for model in [core / "model"] + [book / "model" for book in books]:
        for path in model.rglob("*") if model.is_dir() else []:
            if path.suffix == ".tsx":
                problems.append(f"L2 {path.relative_to(root)}: a model holds no JSX (.tsx)")
            elif path.suffix == ".ts" and re.search(r"""from\s+['"]react(?:-dom)?['"/]""", path.read_text(encoding="utf-8")):
                problems.append(f"L2 {path.relative_to(root)}: a model does not import React")

    for block in blocks:
        problems += _component_problems(root, block, needs_css=False, mark="data-block", draws=False)
    problems += _kit_problems(root, core / "kit" / "reading", primitives, needs_css=False, owner=f"{names['core']}/kit/reading")
    for book in books:
        if not KEBAB.match(book.name):
            problems.append(f"L3 {names['books']}/{book.name}: book ids are kebab-case")
        for name in BOOK_REQUIRED:
            if not (book / name).is_file():
                problems.append(f"L1 {names['books']}/{book.name}/{name} is missing")
        used = _series_used(book, books_dir)
        covered = {p.name for s in used for p in _folders(books_dir / SERIES_DIR / s / "kit")}
        problems += _kit_problems(root, book / "kit", primitives, needs_css=True, owner=f"{names['books']}/{book.name}/kit", covered=covered)
        index_file = book / "index.ts"
        if index_file.is_file() and not TYPED_BOOK.search(index_file.read_text(encoding="utf-8")):
            problems.append(f"L20 {names['books']}/{book.name}/index.ts: check the definition at compile time (`const style = {{ … }} satisfies BookStyle` or `defineBook({{ … }})`): a missing primitive must fail in the editor")
        for part in _folders(book / "parts"):
            problems += _component_problems(root, part, needs_css=True, mark="data-block", draws=False)
            tsx = part / f"{part.name}.tsx"
            if tsx.is_file() and not UNIQUE.match(tsx.read_text(encoding="utf-8").splitlines()[0] if tsx.read_text(encoding="utf-8") else ""):
                problems.append(f"L18 {part.relative_to(root)}: a book part is the exception; start it with `// unique-structure: <why no core block + kit fits>` or use the core block")
        problems += _book_css_problems(root, book)
        palette = book / "styles" / "palette.css"
        if palette.is_file() and "GENERATED" not in palette.read_text(encoding="utf-8")[:300]:
            problems.append(f"L12 {palette.relative_to(root)} is not the generated file (`pdfmeasure palette --selector '[data-book={book.name}]'`)")
        for path in book.rglob("*"):
            if path.suffix in (".ts", ".tsx") and not _is_test(path):
                for _, resolved in _resolved_imports(path):
                    inside = _inside(resolved, books_dir)
                    if inside and inside[0] != book.name and inside[0] != SERIES_DIR:
                        problems.append(f"L14 {path.relative_to(root)} imports book {inside[0]!r}: books are independent; share through {names['core']}/")
    problems += _series_problems(root, books_dir, books, primitives, names)
    for path in core.rglob("*") if core.is_dir() else []:
        if path.suffix in (".ts", ".tsx") and not _is_test(path):
            for target, resolved in _resolved_imports(path):
                if _inside(resolved, books_dir) is not None:
                    problems.append(f"L13 {path.relative_to(root)} imports {target!r}: the core never knows a book (books plug in through contracts.ts)")
        elif path.suffix == ".css":
            for selector in _selectors(path.read_text(encoding="utf-8")):
                if "[data-view" not in selector.replace(" ", ""):
                    problems.append(f"L6 {path.relative_to(root)}: selector {selector[:60]!r} is not scoped to a view")
                    break
    registry = books_dir / "registry.ts"
    if registry.is_file():
        text = registry.read_text(encoding="utf-8")
        for book in books:
            if not re.search(rf"""import\(\s*['"]\./{re.escape(book.name)}(?:/index)?['"]\s*\)""", text):
                problems.append(f"L15 {names['books']}/registry.ts does not load {book.name!r} lazily (import('./{book.name}'))")
        if re.search(r"""^\s*import\s[^(]*from\s+['"]\./""", text, re.MULTILINE):
            problems.append(f"L15 {names['books']}/registry.ts imports a book statically: every book would ship in the main bundle")
    index = root / "index.ts"
    if index.is_file():
        for target in _imports(index.read_text(encoding="utf-8")):
            clean = target.lstrip("./")
            if "/tokens" in clean or "/parts/" in clean or "/kit/" in clean or "fixtures" in clean or (clean.startswith(names["books"] + "/") and not clean.startswith(f"{names['books']}/registry")):
                problems.append(f"L7 index.ts exports {target!r}: the public API is EbookPage, the block schemas, types and the book ids")
    for path in sorted(root.rglob("*")):
        if path.suffix not in SOURCE or not path.is_file():
            continue
        relative = path.relative_to(root)
        text = path.read_text(encoding="utf-8")
        test = _is_test(path)
        if path.suffix == ".tsx" and not test:
            for body in STYLE_OBJECT.findall(text):
                fixed = sorted({key for _, key in STYLE_KEY.findall("{" + body) if not key.startswith("--") and not key.startswith("...")})
                if fixed:
                    problems.append(f"L4 {relative}: inline style sets {', '.join(fixed)}; set CSS custom properties only and write the rule in CSS")
                    break
            for attribute, value in LITERAL_LABEL.findall(text):
                problems.append(f"L10 {relative}: {attribute}=\"{value[:30]}\" is literal UI text; use the host's i18n")
                break
        if path.suffix in (".ts", ".tsx") and not test and "fixtures" not in relative.parts:
            for target in _imports(text):
                if "fixtures" in target.split("/"):
                    problems.append(f"L8 {relative} imports fixtures ({target}); only tests and the lab may")
                    break
        if not test and path.suffix in (".ts", ".tsx") and _lines(path) > max_lines:
            problems.append(f"L11 {relative}: {_lines(path)} non-empty lines (max {max_lines}); split by responsibility")
    return problems


def _component_problems(root: Path, folder: Path, needs_css: bool, mark: str, draws: bool) -> list[str]:
    """Folder shape, its mark, no import of a sibling, and (blocks, book parts) no drawing of its own."""
    problems = []
    rel = folder.relative_to(root)
    if not KEBAB.match(folder.name):
        problems.append(f"L3 {rel}: folders are kebab-case")
    tsx, css = folder / f"{folder.name}.tsx", folder / f"{folder.name}.css"
    if not tsx.is_file():
        problems.append(f"L3 {rel}/{folder.name}.tsx is missing")
    if needs_css and not css.is_file():
        problems.append(f"L3 {rel}/{folder.name}.css is missing (its sheet style)")
    if tsx.is_file():
        text = tsx.read_text(encoding="utf-8")
        if mark not in text and "data-decorative" not in text:
            problems.append(f"L5 {rel}/{folder.name}.tsx: mark it with {mark}")
    for path in folder.rglob("*"):
        if path.suffix in (".ts", ".tsx") and not _is_test(path):
            text = path.read_text(encoding="utf-8")
            if not draws:
                found = OWN_DRAWING.search(text)
                if found:
                    problems.append(f"L16 {path.relative_to(root)} draws {found.group(0)!r} itself: labels, lines, arrows and frames come from kit primitives (one component per pattern)")
            for _, resolved in _resolved_imports(path):
                inside = _inside(resolved, folder.parent)
                if inside and inside[0] not in (folder.name, "shared"):
                    problems.append(f"L9 {path.relative_to(root)} imports {inside[0]!r}: blocks and parts compose kit primitives, not each other")
    return problems


def _series_used(book: Path, books_dir: Path) -> set[str]:
    """The series kits a book builds on (imports into books/_series/<series>/)."""
    used = set()
    for path in book.rglob("*"):
        if path.suffix in (".ts", ".tsx") and not _is_test(path):
            for _, resolved in _resolved_imports(path):
                inside = _inside(resolved, books_dir)
                if inside and len(inside) > 1 and inside[0] == SERIES_DIR:
                    used.add(inside[1])
    return used


def _series_problems(root: Path, books_dir: Path, books: list[Path], primitives: list[str], names: dict) -> list[str]:
    problems = []
    for series in _folders(books_dir / SERIES_DIR):
        owner = f"{names['books']}/{SERIES_DIR}/{series.name}"
        if not KEBAB.match(series.name):
            problems.append(f"L3 {owner}: series ids are kebab-case")
        users = [book.name for book in books if series.name in _series_used(book, books_dir)]
        if len(users) < SERIES_MIN:
            problems.append(f"L19 {owner} is used by {len(users)} book(s) ({', '.join(users) or 'none'}): a series kit starts at {SERIES_MIN} books of one series; until then keep the primitives in each book's kit")
        for folder in _folders(series / "kit"):
            if primitives and folder.name not in primitives:
                problems.append(f"L17 {owner}/kit/{folder.name} is not in core/kit/contract.ts")
                continue
            problems += _component_problems(root, folder, needs_css=True, mark=f'data-kit="{folder.name}"', draws=True)
        scope = f"[data-series={series.name}]"
        for path in sorted(series.rglob("*.css")):
            for selector in _selectors(path.read_text(encoding="utf-8")):
                compact = selector.replace(" ", "").replace('"', "").replace("'", "")
                if scope not in compact or "[data-view=sheet]" not in compact:
                    problems.append(f"L6 {path.relative_to(root)}: selector {selector[:60]!r} is not scoped to {scope}[data-view=sheet]")
                    break
        for path in series.rglob("*"):
            if path.suffix in (".ts", ".tsx") and not _is_test(path):
                for _, resolved in _resolved_imports(path):
                    inside = _inside(resolved, books_dir)
                    if inside and not (inside[0] == SERIES_DIR and len(inside) > 1 and inside[1] == series.name):
                        problems.append(f"L14 {path.relative_to(root)} imports {'/'.join(inside[:2])!r}: a series kit knows no book and no other series")
    return problems


def _kit_problems(root: Path, kit: Path, primitives: list[str], needs_css: bool, owner: str, covered: set[str] | None = None) -> list[str]:
    problems = []
    present = {folder.name for folder in _folders(kit)} | (covered or set())
    for name in primitives:
        if name not in present:
            problems.append(f"L17 {owner}/{name} is missing: every primitive of the contract is implemented here")
    for folder in _folders(kit):
        if primitives and folder.name not in primitives:
            problems.append(f"L17 {owner}/{folder.name} is not in core/kit/contract.ts: a new pattern is added to the contract (and to every kit), never privately")
            continue
        problems += _component_problems(root, folder, needs_css=needs_css, mark=f'data-kit="{folder.name}"', draws=True)
    return problems


def _book_css_problems(root: Path, book: Path) -> list[str]:
    problems = []
    scope = f"[data-book={book.name}]"
    for path in sorted(book.rglob("*.css")):
        sheet_rules = path.name != "palette.css"
        for selector in _selectors(path.read_text(encoding="utf-8")):
            compact = selector.replace(" ", "").replace('"', "").replace("'", "")
            if scope not in compact:
                problems.append(f"L6 {path.relative_to(root)}: selector {selector[:60]!r} is not scoped to {scope} (books share class names; their CSS must not leak)")
                break
            if sheet_rules and "[data-view=sheet]" not in compact:
                problems.append(f"L6 {path.relative_to(root)}: selector {selector[:60]!r} is not scoped to [data-view=sheet] (a book styles only its print sheet)")
                break
    return problems


def command_structure(args) -> int:
    mapping = json.loads(args.map) if args.map else None
    problems = check(args.module, mapping, args.max_lines)
    if problems:
        print(f"structure: {len(problems)} problem(s) in {args.module}\n" + "\n".join(f"- {p}" for p in problems))
        return 1
    print(f"structure: {args.module} follows the ebook module layout (references/14-module-layout.md)")
    return 0


def register(add) -> None:
    cmd = add("structure", command_structure, "check the ebook module (core kit + blocks, books/<id> kits) against the folder architecture (references/14-module-layout.md)")
    cmd.add_argument("--module", required=True, help="the module folder")
    cmd.add_argument("--map", help='JSON mapping of the top folders to host names, e.g. {"core": "core", "books": "books"}')
    cmd.add_argument("--max-lines", type=int, default=MAX_LINES)
