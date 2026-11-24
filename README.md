# pdf-to-ui-replica

An agent skill (for [Claude Code](https://claude.com/claude-code)) and a Python toolkit that rebuild the pages of a print-ready PDF (workbook, textbook, exam paper, form, picture book) as a **measured, reusable web template** and **prove the match against the PDF**, with a harness that stops an agent from calling a book "done" while the files say otherwise.

> **Tóm tắt (vi):** skill + bộ công cụ `pdfmeasure` để dựng lại trang sách PDF in thành giao diện web (React + shadcn/ui + Tailwind v4) có số đo chính xác theo điểm in (pt), rồi kiểm chứng với PDF gốc. Có harness (state, gate, Stop hook) buộc agent làm đủ bước, bàn giao artwork qua prompt cho agent khác, kiến trúc module nhiều sách dùng chung component, sổ knowhow cho các lỗi hay lặp lại.

Numbers come from tools, never from eyeballing: geometry, colours (CMYK to sRGB), strokes, corner radii, text size, weight, indent and line spacing are *measured* on the PDF and *verified* on the rebuilt page.

## What is in here

| Part | What it gives you |
|---|---|
| **Measuring** (`shapes`, `signatures`, `roles`, `report`, `palette`, `lines`) | Vector shapes of a PDF page, recurring components, per-page invariants, a generated CSS palette |
| **Verifying** (`verify`, `compare`, `zoom`, `text-layout`, `typography`, `tiles`) | Geometry in points, part-by-part zoom comparison, every text line (indent, spacing), typography scored per style (size, weight, family, indent, spacing: PASS ≥ 95 %, WARNING < 95 %, ERROR < 92 %), high-zoom tiles so small parts are not missed |
| **Visual QA loop** (`visual-compare`, `issue`, `codex-prompt`, `codex-run`, `qa-report`) | Whole-page diff, defect register with a status lifecycle, repair loop with a failed-round cap, hand-off prompts for hard defects |
| **Setup** (`init`) | Environment check with install commands, Stop hook registration, `.gitignore`, stack report |
| **Harness** (`state`, `gate`, Stop hook) | Page statuses that only move through checks, five quality gates, a hook that blocks ending a session with unfinished pages |
| **Artwork hand-off** (`artwork`) | Characters, objects and scenes are never copied: they are described (measured box, palette, identity, states, people with origin and skin tone), turned into a table prompt for another agent, delivered on a separate branch, then imported and validated |
| **Reading view on phones** (`reflow`) | A second, readable view of the same content model, checked in a real browser at 320/360/390/768 px (overflow, text sizes, targets, zoom lock, block parity and order) |
| **Ebook module architecture** (`structure`, `consistency`) | One layout for many books: shared kit primitives, blocks written once, one style pack per book, lazy registry; each repeated pattern renders the same on every page |
| **Knowhow register** (`knowhow`) | Defects that come back (for example: a 0.5 px border is painted 1 px by Chrome), with cause, fix, check and source-pattern detectors |

The workflow, rules and lessons are in [`SKILL.md`](SKILL.md) and [`references/`](references/).

## Requirements

- Python 3.10+ with `pdfplumber`, `numpy`, `Pillow` (`pip install -r scripts/requirements.txt`; `pytest` only for the tests)
- `poppler-utils` (`pdftoppm`)
- Node 18+ with `playwright` and a browser (`npm i -D playwright && npx playwright install chromium`) for the rebuilt-page measurements
- Vector PDFs measure best; scans only get visual analysis
- Supported UI stack for builds: **React + shadcn/ui + Tailwind CSS v4** (`gate scope` refuses others for now). Analysis-only runs work for any project.

## Install

Works on Windows, Linux and macOS. Run in the project you want to use the skill in:

```bash
npx skills@1.7.6 add ntgptit/pdf-to-ui-replica --agent claude-code -y
python .claude/skills/pdf-to-ui-replica/scripts/init.py      # Windows: py ...; Linux/macOS: python3 ...
```

The first line installs the skill into `.claude/skills/pdf-to-ui-replica/` (Claude Code loads it from there). The second line is the setup (`init`, Python 3.10+):

- **checks the environment** and prints the exact install command for every gap: Python packages (`pdfplumber`, `numpy`, `Pillow`), `pdftoppm` (poppler), Node 18+, Playwright and its browser;
- **registers the Stop hook** in the project's `.claude/settings.json` (merged, never twice, never overwriting);
- **adds `pdf-to-ui-output/` and `.tmp/pdf-to-ui/` to `.gitignore`** (they hold page images of the book);
- **reports the UI stack**: builds need React + shadcn/ui + Tailwind CSS v4; analysis works on any project.

Run `init` again after installing the missing tools until it says "Ready". Options: `--check` (report only), `--project DIR`. To update the skill, run the `npx` line again. A private repository needs a GitHub login on the machine.

Typical first run on a machine without the dependencies:

```
[MISSING] Python package numpy: missing
            install: pip install -r .../scripts/requirements.txt
[missing] Playwright: missing
            install: in the project: npm i -D playwright   (needed for measuring the rebuilt page)
```

Run the tools from the `scripts/` folder:

```bash
cd .claude/skills/pdf-to-ui-replica/scripts
PYTHONPATH=. python3 -m pdfmeasure --help        # also: python3 -m pdfmeasure init
```

## Quick start

```bash
export PYTHONPATH=.            # inside scripts/

# 1. look at the PDF
python3 -m pdfmeasure shapes --pdf book.pdf --pages 9-12
python3 -m pdfmeasure signatures --pdf book.pdf --pages 9-40

# 2. start a build (output kind web-fixed: desktop print sheet + phone reading view)
python3 -m pdfmeasure state init --output out --pages 9-40 --pilot 9,12,20 --root /path/to/your/repo
python3 -m pdfmeasure tiles --pdf book.pdf --page 9 --output out --mode pdf     # high-zoom tiles for the inventory
python3 -m pdfmeasure gate inventory --output out --inventory object-inventory.md

# 3. measure, build, verify (see SKILL.md for the full order)
python3 -m pdfmeasure typography --pdf book.pdf --page 9 --output out --spec-only
python3 -m pdfmeasure visual-compare --pdf book.pdf --page 9 --output out --label v0 --url <lab url> --verify-config verify.json
python3 -m pdfmeasure reflow --output out --page 9 --url <reading view> --fixed-url <print view> --auto-url <auto view>
python3 -m pdfmeasure state page --output out --page 9 --status VERIFIED --note "..."   # refused unless the evidence is there
python3 -m pdfmeasure gate book --output out
```

## How it works

1. **Inspect and inventory** (phases 0–2A): classify the PDF, find the page frame, cluster recurring shapes into roles, list every drawing, frame and small part on high-zoom tiles.
2. **Measure** (3): quantities per component, a generated palette, a typography spec per text style.
3. **Model, build, re-architect** (4–6): tokens in points, a content model, shared kit primitives and blocks, one style pack per book.
4. **Verify** (7–8): geometry, zoom per part, text layout of every line, typography, kit consistency across pages, reading view on phones.
5. **Visual QA and repair** (10): scan once, triage, fix in the same run, compare again; hard defects go to another agent with a self-contained prompt.
6. **Harness**: `state` and `gate` turn these rules into checks the files must pass; a Stop hook blocks "done" while pages are in progress or P0/P1 defects are open.

Every run ends with a report to the user in the chat, with the pictures to review.

## Repository layout

```
SKILL.md              the skill: workflow, rules, decisions taken without asking
references/          phase documents, harness, artwork, reflow, stack recipe, module layout, knowhow register
scripts/pdfmeasure/  the Python toolkit (python3 -m pdfmeasure <command>)
scripts/*.cjs        Playwright helpers (DOM measuring, crops, reflow, kit consistency)
scripts/init.py      setup of the skill in a project
scripts/tests/       pytest suite
hooks/               the Stop hook (registered by init)
examples/            configs and QA results of one real run (no PDF, no page images)
```

## Tests

```bash
cd scripts && PYTHONPATH=. python3 -m pytest tests -q
```

Typography tests use the DejaVu fonts when installed (they skip otherwise); `reflow` and `consistency` need Playwright with a browser to run for real, their judgement logic is tested without one.

## Status and limits

- Built and tested with synthetic fixtures (generated pages and HTML) and on pages of one real workbook. It has **not** yet driven a whole book end to end through every gate.
- Thresholds (typography 95 % / 92 %, reflow text sizes, 1 px consistency tolerance) are defaults: confirm them on the first real page and tune per project, writing the reason next to the change.
- Font-family scoring is a proxy (stroke contrast and ink proportion). With a text layer the real font name decides.
- Only the React + shadcn/ui + Tailwind v4 stack is supported for builds; other stacks are planned.

## Copyright

Never commit a PDF, its page images, its characters or its text. This repository holds measurements, configs and original fixture content only. The `examples/` folder contains measurements and QA text from one commercial workbook (numbers and defect descriptions, no pages or images); review it before making this repository public.

## License

Not chosen yet: until a license file is added, all rights are reserved by the author.
