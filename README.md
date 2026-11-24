# pdf-to-ui-replica

Rebuild the pages of a print-ready PDF (workbook, textbook, exam paper, form, picture book) as a **measured, reusable web template**, then **prove the match against the PDF**.

It is an agent skill for [Claude Code](https://claude.com/claude-code) plus a Python toolkit (`pdfmeasure`). Every number comes from a tool, never from eyeballing: geometry, colours (CMYK to sRGB), strokes, corner radii, text size, weight, indent and line spacing are *measured* on the PDF and *verified* on the rebuilt page. A harness (state file, quality gates, Stop hook) stops an agent from calling a book "done" while the files say otherwise.

> **Tóm tắt (vi):** skill + bộ công cụ `pdfmeasure` dựng lại trang sách PDF in thành giao diện web (React + shadcn/ui + Tailwind v4) có số đo chính xác theo điểm in (pt), rồi kiểm chứng với PDF gốc. Có harness (state, gate, Stop hook) buộc agent làm đủ bước, bàn giao artwork qua prompt cho agent khác, kiến trúc module dùng chung component cho nhiều sách, và sổ knowhow cho các lỗi hay lặp lại. Cài bằng một lệnh: `npx github:ntgptit/pdf-to-ui-replica init`.

## Contents

[Install](#install) · [Use it](#use-it) · [What it does](#what-it-does) · [Harness](#harness-why-an-agent-cannot-skip-steps) · [Many books, one module](#many-books-one-module) · [Commands](#commands) · [Requirements](#requirements) · [Repository layout](#repository-layout) · [Tests](#tests) · [Status and limits](#status-and-limits) · [Copyright](#copyright) · [License](#license)

## Install

Works on Windows, Linux and macOS. Needs Node 18+ and Python 3.10+. In the project you want to use the skill in:

```bash
npx github:ntgptit/pdf-to-ui-replica init
```

(after the package is published to npm: `npx pdf-to-ui-replica init`). One command, no arguments. It:

1. **installs the skill** into `.claude/skills/pdf-to-ui-replica/` (Claude Code loads it from there);
2. **installs the missing libraries**: Python packages (`pdfplumber`, `numpy`, `Pillow`) with pip, Playwright with npm (inside the skill's `scripts/` folder, your `package.json` stays untouched) and its Chromium browser (a large download);
3. **checks the tools of the machine** and prints the exact command for each one that is missing, never installing them itself: Python 3.10+, `pdftoppm` (poppler), Node 18+;
4. **registers the Stop hook** in the project's `.claude/settings.json` (merged with what is there, never twice, never overwriting; an invalid `settings.json` is left untouched and reported);
5. **adds `pdf-to-ui-output/` and `.tmp/pdf-to-ui/` to `.gitignore`** (they hold page images of the book);
6. **reports the UI stack** of the project: builds need React + shadcn/ui + Tailwind CSS v4; analysis works on any project.

```
  pdf-to-ui-replica init
  /path/to/project

  Environment
    ✓ Python                     3.13
    ✓ Python package pdfplumber  found
    ✗ poppler (pdftoppm)         missing
        → sudo apt-get install -y poppler-utils   |   brew install poppler

  Project
    ✓ Skill       installed in .claude/skills/pdf-to-ui-replica
    ✓ Stop hook   registered in .claude/settings.json
    ✓ .gitignore  added pdf-to-ui-output/, .tmp/pdf-to-ui/
    ! UI stack    React + shadcn/ui + Tailwind CSS v4 not found

  ✗ Not ready  install the missing required tools first: poppler (pdftoppm)
```

Run it again after installing what it listed, until it says `Ready`. It is idempotent.

| Option | Effect |
|---|---|
| `--project DIR` | the project folder (default: the current directory) |
| `--update` | replace the installed copy with the latest version |
| `--no-install` | do not install libraries (pip packages, Playwright, Chromium) |
| `--check` | report only: write nothing, install nothing |

Colour appears only on a terminal (`NO_COLOR` turns it off); `PDF_TO_UI_ASCII=1` forces plain symbols. A private repository needs a GitHub login on the machine.

Without Node, or to install only the skill files: `npx skills@1.7.6 add ntgptit/pdf-to-ui-replica --agent claude-code -y`, then `python .claude/skills/pdf-to-ui-replica/scripts/init.py` (Windows: `py`; same options).

## Use it

In Claude Code, ask in plain words. The skill picks the workflow from the request:

| You ask for | The agent does |
|---|---|
| "Analyse this PDF" | inspect and classify it, analyse the pages |
| "List the objects this page needs" | inventory of every drawing, frame and small part on high-zoom tiles |
| "Rebuild page 9 in React" | measure, build, verify, visual QA, report |
| "Check the page I built against the PDF" | verify layers, visual QA, triage, report |
| "Replicate the whole book" | all phases, page type by page type, **under the harness** |

The agent follows [`SKILL.md`](SKILL.md) (workflow, rules, decisions taken without asking) and the phase documents in [`references/`](references/). A run ends with a report in the chat, with the pictures to review.

The tools can also be driven by hand. From the skill's `scripts/` folder:

```bash
cd .claude/skills/pdf-to-ui-replica/scripts
export PYTHONPATH=.                      # Windows PowerShell: $env:PYTHONPATH="."

python3 -m pdfmeasure shapes --pdf book.pdf --pages 9-12            # look at the PDF
python3 -m pdfmeasure signatures --pdf book.pdf --pages 9-40        # recurring components

python3 -m pdfmeasure state init --output out --pages 9-40 --pilot 9,12,20 --root /path/to/repo
python3 -m pdfmeasure tiles --pdf book.pdf --page 9 --output out --mode pdf        # high-zoom tiles
python3 -m pdfmeasure gate inventory --output out --inventory object-inventory.md

python3 -m pdfmeasure typography --pdf book.pdf --page 9 --output out --spec-only
python3 -m pdfmeasure visual-compare --pdf book.pdf --page 9 --output out --label v0 --url <lab url> --verify-config verify.json
python3 -m pdfmeasure reflow --output out --page 9 --url <reading view> --fixed-url <print view> --auto-url <auto view>

python3 -m pdfmeasure state page --output out --page 9 --status VERIFIED --note "..."   # refused unless the evidence is there
python3 -m pdfmeasure gate book --output out
```

`python3 -m pdfmeasure --help` lists every command. On Windows use `py -3` or `python`.

## What it does

| Phase | What happens | Main tools |
|---|---|---|
| 0–1 | Classify the PDF (vector or scan), find the page frame, left/right pages, regions | `shapes` |
| 2 | Cluster recurring vector shapes into components and roles | `signatures`, `roles` |
| 2A | **Visual inventory**: the agent looks at every page on high-zoom tiles and lists every drawing, frame and small part | `tiles`, `gate inventory` |
| 3 | Measure each component: quantities in points, a generated CSS palette, a typography spec per text style | `report`, `palette`, `lines`, `typography --spec-only` |
| 4–6 | Models in points, build with shared kit primitives and blocks, one style pack per book | `structure`, `consistency` |
| 7–8 | Verify: geometry in points, zoom per part, text layout of every line, typography | `verify`, `compare`, `zoom`, `text-layout`, `typography` |
| 7C | Reading view on phones (second view of the same content), checked at 320/360/390/768 px | `reflow` |
| 10 | Visual QA loop: whole-page diff, defect register, repair, compare again, hand hard defects to another agent | `visual-compare`, `issue`, `codex-prompt`, `qa-report` |

- **Typography is scored, not guessed.** Size, weight, family, indent and line spacing are scored per text style: PASS at 95 % or more, WARNING under 95 %, ERROR under 92 %.
- **Small parts are not missed.** Tiles are re-rendered from the PDF at 6 px per point or more, never enlarged from a small image.
- **Artwork is described, never copied.** Characters, objects and scenes get a brief (measured box, palette, identity, states, and for people their origin and skin tone), then a table prompt for another agent, delivered on a separate branch, then imported and fitted (`artwork`).
- **Knowhow register** (`knowhow`): defects that keep coming back, each with cause, fix, check and a source-pattern detector. Example: Chrome paints a `0.5px` border as 1 px; a 0.5 px rule is built with an SVG stroke or a scaled 1 px bar instead.

## Harness: why an agent cannot skip steps

- **`state`**: a state file (`<output>/ebook-state.json`) with a status for every page: `NOT_STARTED`, `IN_PROGRESS`, `VERIFIED`, `ACCEPTED_LIMITATION`, `BLOCKED`. A page reaches `VERIFIED` only through checks that read the evidence files; the command is refused otherwise.
- **`gate`**: five gates evaluated from the files: `scope`, `inventory`, `pilot`, `book`, `delivery`. A failing gate exits 1 and lists the problems.
- **Issues** have a lifecycle and a failed-round cap, so a defect cannot loop forever or be silently dropped.
- **Stop hook** (`hooks/ebook-gate-stop.py`): blocks ending a session while a page is `IN_PROGRESS` or a P0/P1 defect is open (up to four times per session). It is silent when no state file exists. Escape hatch: `state block --reason "..."`.
- **Output kind `web-fixed`** (default): the desktop print sheet and the phone reading view are both required and built together.

Details: [`references/10-harness.md`](references/10-harness.md).

## Many books, one module

Built for many books from the first one: a shared **core** (kit contract, blocks written once, behaviours, views, reading kit) and one **style pack per book** (`books/<id>/`: its kit, measured tokens, generated palette). A pattern that repeats (example label, answer line, rule, frame, item number…) is **one kit primitive** used on every page, so it cannot drift between pages.

- `structure` checks the folder layout (rules L1–L20: file places, no sibling imports, generated palettes, typed book definitions, series kits only from three books).
- `consistency` measures every kit primitive in a real browser and fails when the same primitive renders differently on two pages (1 px tolerance).
- Books load lazily through a registry (one chunk per book); no factory or strategy classes.

Details: [`references/14-module-layout.md`](references/14-module-layout.md) and [`references/13-react-shadcn-tailwind.md`](references/13-react-shadcn-tailwind.md).

## Commands

| Group | Commands |
|---|---|
| Setup | `init` |
| Measuring | `shapes`, `signatures`, `lines`, `roles`, `report`, `palette` |
| Verifying | `verify`, `compare`, `zoom`, `text-layout`, `typography`, `tiles` |
| Visual QA | `qa-start`, `visual-compare`, `issue`, `codex-prompt`, `codex-run`, `qa-report`, `qa-finish` |
| Harness | `state`, `gate` |
| Artwork | `artwork` (`brief`, `prompt`, `import`, `status`) |
| Reading view | `reflow` |
| Architecture | `structure`, `consistency` |
| Knowledge | `knowhow` (`list`, `search`, `show`, `add`, `update`, `seen`, `scan`, `render`) |

Config file formats: [`references/config-reference.md`](references/config-reference.md).

## Requirements

- Python 3.10+; `pdfplumber`, `numpy`, `Pillow` (installed by `init`)
- `poppler-utils` (`pdftoppm`); `init` prints the command, it does not install it
- Node 18+ for the measurements of the rebuilt page; Playwright and Chromium (installed by `init`)
- Vector PDFs measure best; scans only get visual analysis
- Builds support **React + shadcn/ui + Tailwind CSS v4** for now (`gate scope` refuses other stacks); analysis-only runs work for any project

## Repository layout

```
SKILL.md              the skill: workflow, rules, decisions taken without asking
README.md             this file
package.json          npm package: `npx pdf-to-ui-replica init`
bin/cli.js            the `init` command (install the skill, then run scripts/init.py)
references/           phase documents, harness, artwork, reflow, stack recipe, module layout, knowhow register
scripts/init.py       setup: environment, libraries, Stop hook, .gitignore, stack report
scripts/pdfmeasure/   the Python toolkit (python3 -m pdfmeasure <command>)
scripts/*.cjs         Playwright helpers (DOM measuring, crops, reflow, kit consistency)
scripts/tests/        pytest suite
scripts/export-standalone.py   mirror this folder into a clone of the standalone repository
hooks/                Stop hook and a settings.json example
examples/             configs and QA results of one real run (no PDF, no page images)
```

## Tests

```bash
cd scripts && PYTHONPATH=. python3 -m pytest tests -q
```

Typography tests use the DejaVu fonts when installed (they skip otherwise). `reflow` and `consistency` need Playwright with a browser to run for real; their judgement logic is tested without one.

## Status and limits

- Built and tested with synthetic fixtures (generated pages and HTML) and on pages of one real workbook. It has **not** yet driven a whole book end to end through every gate.
- Thresholds (typography 95 % / 92 %, reflow text sizes, 1 px consistency tolerance) are defaults: confirm them on the first real page and tune per project, writing the reason next to the change.
- Font-family scoring is a proxy (stroke contrast and ink proportion). With a text layer the real font name decides.
- `init` is tested on Linux. The Windows and macOS paths (Python launcher, `npm`/`npx` shims, console colours) are written for them but not run there yet.
- Only the React + shadcn/ui + Tailwind v4 stack is supported for builds; other stacks are planned.

## Copyright

Never commit a PDF, its page images, its characters or its text. This repository holds measurements, configs and original fixture content only. The `examples/` folder contains measurements and QA text from one commercial workbook (numbers and defect descriptions, no pages or images); review it before making this repository public.

## License

Not chosen yet: until a license file is added, all rights are reserved by the author.
