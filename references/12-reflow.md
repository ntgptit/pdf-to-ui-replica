# Reading view on phones (reflowable)

The print-sheet view (phases 4–6) reproduces the PDF page box in points: it is what geometry, zoom and typography checks compare. Scaled to a 360 px phone it is not readable: an A4 page shrinks to 0.6 px per point, so 10 pt body text becomes about 6 px. A web ebook therefore needs a **second view of the same content**, built for reading on a phone: blocks stacked vertically in reading order, real font sizes, nothing wider than the screen. This file is project-neutral: it describes the contract and the rules, not a framework.

## 1. Output kind
Chosen at `state init` (`references/10-harness.md`):
- `replica-lab`: print view only (a measuring lab); no reading view.
- `web-fixed` (the default, decided without asking): print view on wide screens **and** a reading view on phones, built together.
- `web-reflowable`: reading view everywhere; the print view stays as the measured reference.
- `epub-fixed`: fixed layout by definition; no reading view.
For `web-fixed` and `web-reflowable` the harness refuses VERIFIED until the page's reading view passes `reflow`.

## 2. One content model, two views
- The content model (phase 4) is the single source: sections, items, word banks, dialogues, exercises, artwork references, each with a stable id. Both views render it; **content is never duplicated or edited per view**.
- One build, two views of the same block props, chosen at run time: `sheet` (print page, positioned in points from the book's tokens) and `reading` (flow layout). Blocks are written once in the core and compose kit primitives; the reading view gets the reading kit (shared by every book), the sheet gets the book's kit, so the views differ only inside primitives. Behaviour (answers, audio) is one core hook used by both. Never fork the data handling. Stack recipe: `13-react-shadcn-tailwind.md`, layout: `14-module-layout.md`.
- Mark every content block with `data-block="<content id>"` in **both** views, and text that is not body text with `data-text-role="heading|caption|label|ruby|decorative"`. The checker uses these; deep links and "continue where you left off" use the same ids, so they work in both views.
- Reading order = content-model order, not x/y position on the sheet. A two-column page becomes one column in that order.

## 3. Which view opens
- `reflow` measures the print view at phone width and reports its smallest body text: under 12 px, phones open the **reading** view by default (`phone_default: reading`). In practice every printed A4/B5 page qualifies.
- Wide screens open the print view for `web-fixed`. The reader can switch at any time (a visible toggle, remembered per reader); switching keeps the position by scrolling to the current `data-block`.
- Decide by available width (container or viewport), not by device type.

## 4. Rules of the reading view
| Part of the page | In the reading view |
|---|---|
| Page box, margins, absolute positions | gone: normal flow, one column, side padding 16 px, readable measure (body lines ≤ ~70 characters, about 40 em) |
| Typography | from the typography spec (phase 3): body 16–18 px, line height 1.5–1.7; other styles keep their **ratio to body** from the measured core heights; captions, labels, ruby ≥ 14 px; sizes in rem so the reader's text size setting applies; same family and weight as the print view |
| Headings, section tabs, numbered sections | kept as headings in order; decorative tab shapes may shrink to a coloured marker |
| Wide grids and tables (8 vowels in a row, answer grids) | wrap into rows (`auto-fit` columns with a minimum cell width) or scroll **inside their own container** with a visible cue; the page itself never scrolls sideways |
| Word banks, chips | wrap |
| Speech bubbles, dialogues | stacked rows: speaker (name or avatar) then the line; no absolute bubbles |
| Exercises, answer boxes, inputs | full width; input text ≥ 16 px (smaller text makes some phones zoom on focus); every target at least 24 px (44 px comfortable; the project may define which controls get 44) |
| Artwork, stroke-order diagrams | scaled to the column (`max-width: 100%`, aspect kept) from `artwork-map.json`; fine diagrams may open larger on tap; decorative art may be smaller or dropped, never content art |
| Page numbers | kept as small anchors (teachers say "page 18"), not as layout |
| Decorations (hatch bands, frames, ornaments) | optional; never wider than the screen |
| Zoom | never disabled (`user-scalable=no` or `maximum-scale` < 2 is an error) |

## 5. Check
```
PYTHONPATH=. python3 -m pdfmeasure reflow --output O --page N --url <reading view URL> --fixed-url <print view URL> [--widths 320,360,390,768] [--config cfg.json]
```
`check-reflow.cjs` opens the reading view in a real browser at each width (320 px is the WCAG reflow width, 360 and 390 common phones, 768 a small tablet), measures every visible text, target, picture and block, and saves a full-page screenshot per width (`reflow-<width>.png`). `pdfmeasure` judges the numbers:
- **ERROR**: horizontal scroll; body text < 16 px; caption, label, ruby < 14 px; a target < 24 px; zoom disabled; a picture running off the screen; a block of the print view missing; blocks out of reading order.
- **WARNING**: a body line longer than about 40 em; a target < 44 px; a block only in the reading view.
With `--auto-url <the page as readers open it>` it also checks the automatic choice: the reading view at 360 px and the print sheet at 1280 and 1920 px, without horizontal scroll (screenshots `auto-<width>.png`); a `web-fixed` page is not VERIFIED without this check. Thresholds can be changed per project with `--config` (`body_min_px`, `small_min_px`, `target_error_px`, `target_warn_px`, `line_max_em`, `fixed_readable_px`); write the reason next to the config. Then **look at the screenshots** (order, grouping, art scale, nothing cramped) and include them in the chat report of the page.

## 6. Harness
For `web-fixed` and `web-reflowable` a page is VERIFIED only with a `reflow` result newer than the latest scan and without ERROR. A WARNING is allowed and listed. The print view's checks (geometry, zoom, typography, text layout) are unchanged: the reading view does not replace them.
