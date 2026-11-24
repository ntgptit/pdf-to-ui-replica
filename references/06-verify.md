# Phases 7–8 — Verify in two layers

Run both with one command, per page listed in `verify.json`:

```
cd scripts
PYTHONPATH=. python3 -m pdfmeasure verify --config ../examples/sejong-workbook/verify.json --pdf /path/book.pdf --out out/
# starts nothing: your dev server must already serve the lab URL
```
Outputs `out/geometry.md` (layer 1) and `out/zoom.md` plus images (layer 2). Exit code 0 only when everything passes.

## Layer 1 — geometry in points (`compare`)
`measure-dom.cjs` opens the lab at a very large sheet scale (8 CSS px per point, e.g. 4263 px wide) with device scale factor, so Chrome's snapping of SVG roots to whole CSS px and 1 px minimum borders vanish, then records every `data-wb` element box and computed style. `compare` converts to points and checks each entry of `checks-pN.json`:
- `pdf` side: `{role, field, index}` from the PDF's vector shapes; or `expect`: a literal number/colour.
- `dom` side: `{id, field}` (x, y, w, h, right, bottom) or `{id, path, unit}` (`style.borderRadius`, `frame.strokeWidth`, `style.background` as colour).
- `tolerance` in points (0.1–0.6; colours 0). `offset_from` compares a distance between two elements.
Fix the part or token, rerun. Never raise a tolerance to pass.

## Layer 2 — zoom per part (`zoom`)
A small whole-page image hides 1–3 px errors. So per part (`parts-pN.json`: `[x, top, w, h]` in whole points):
1. Crop the PDF at 12 px/pt (`pdftoppm -x -y -W -H` at 864 dpi).
2. Crop the rebuilt sheet from a full-sheet raster laid out at 8 CSS px/pt and shot at 12 px/pt, **by array index** (never browser `clip`, which rounds).
3. Compare by `method` (colour selects the pixels): 
   - `align`: register masks, report shift (pt), IoU; for solid shapes (`thickness:false`).
   - `extent`: bounding edges of the colour mask.
   - `ink`: dark neutral pixels' extent (text blocks).
   - `line`: horizontal rule thickness + centre.
   - `lines`: text line bands (top, bottom, pitch between lines). Use `centre:true` when the content differs (glyph tops/bottoms vary with letters).
   - `words`: word edges; only meaningful for *identical strings* (instruction, caption). Reports gaps and line width.
   - `columns`: first word and column starts.
   - `pitch`: letter pitch by first-harmonic autocorrelation over several lines; tolerance ±0.35 pt with different content, exact with identical content.
4. `zoom.md` embeds PDF | rebuilt | difference images. Look at them.

## Text layout, every line (mandatory)
Run by `verify` for every page (`"text_layout": {}` in the page entry) and by every `visual-compare` scan; alone: `text-layout --pdf X --page N --url LAB_URL --sheet K [--config cfg.json]`. It finds the text lines of the PDF and of the rebuilt page on rasters at 6 px/pt (ink to ink, so no DOM and no typeface dependence), pairs them, and compares for each pair: left edge (margin, indent, hanging number), top, bottom, and the pitch to the line above in the same column. Lines present on one side only are listed. Output: `text-layout.md`.
- Defaults: `tolerance_left` 0.5, `tolerance_vertical` 0.5, `tolerance_pitch` 0.3 (pt). Same typeface and same text: tighten, never loosen. `regions` [[x, top, w, h]] limit the check, `colours` add coloured text (e.g. `#45a665`), `zoom` changes the raster scale.
- It assumes the same text on both sides. With different fixture text the lines do not correspond: skip with `"skip": {"text_layout": "<reason>"}`; the report shows SKIPPED. A page with no text lines found is a failure, not a pass.
- Frames, rules and pictures are ignored (too tall or too thin to be a line).
- Precision is one pixel at the zoom (0.17 pt at 6 px/pt).

## Typography confirmation
`PYTHONPATH=. python3 -m pdfmeasure typography --pdf X.pdf --page N --output O --url LAB_URL --sheet K [--different-text] [--config cfg.json]` (8 px/pt) writes `pages/page-NNN/typography.{md,json}`. Lines are matched by position (as in text-layout) and grouped into styles by core height.
| Attribute | Measured (same code on both sides) | Score |
|---|---|---|
| size | core height (dense ink band), median of the style | 1 − \|Δ\| / PDF |
| weight | pooled stroke width / core height | 1 − \|Δ\| / PDF |
| family | pooled stroke contrast and ink proportion | 1 − mean of both relative errors |
| indent | left edge of each line, relative to the core height | 1 − \|Δx\| / core |
| spacing | pitch between dense-band centres to the line above | 1 − \|Δ\| / PDF pitch |

Levels: **PASS ≥ 95 %, WARNING < 95 %, ERROR < 92 %**, per style and attribute; the worst decides the page. Size, weight and family are pooled over the style's lines, so the letters of one line do not decide them. Checked on real faces (DejaVu): the same face with other text passes; +10 % size, Bold for Book, Serif or Mono for Sans, 1 pt indent are ERROR; a 1.2 pt line-pitch change on 16 pt is WARNING (`scripts/tests/test_typography.py`). Not yet checked on a Hangul face (none installed where the tests ran): confirm on the first real page that an identical rebuild scores ≥ 99 %.
- Fixture text: `--different-text`; indent is then not scored (the ink edge depends on the first letter's side bearing) and the text box's left edge is checked with a geometry check instead.
- The family score is a proxy. With a text layer, use the font name it lists. A family WARNING with the right font name means the face renders differently (hinting, version): note it.
- Fix the cause (font, size, weight, line-height, indent tokens), never the levels.

## Reading results
- shift ≤ tolerance and no problems → pass; a listed problem is a real difference to fix or knowingly accept (e.g. different font).
- Hangul/CJK cannot be split into syllables by ink gaps; compare words/lines, not syllables.
- Different content: compare line centres, not tops/bottoms.

## Fail-closed rules (the verifier never passes by doing nothing)
- Empty `pages`, empty `checks`, empty `parts`, a page with neither, or an unknown `method` stop with an error.
- `align` also needs the masks' overlap (IoU) after the shift ≥ `min_overlap` (default 0.7): a different shape in the same place fails.
- `zoom` is a parameter (4–32 px/pt, tested at 8/12/16); the text metrics follow it.
- Fonts and image decoding are awaited before every measurement.
- `verify` keeps `out/images/p<page>-s<sheet>/zoom-<part>.png` and `zoom.md` links them.
- Every page needs both layers (`checks` and `parts`); leaving one out needs `"skip": {"parts": "reason"}` and the report shows SKIPPED.
- Hex-coloured parts also fail when the two sides' mean colours differ by more than `tolerance_colour` (default 10 per channel).
- Metric deltas are compared unrounded.
- Negative tests in `scripts/tests` cover: wrong shape (overlap), wrong colour (mask-level gate), unrounded tolerance, unknown method, empty lists. Offset and stroke failures are covered by `align`/`line` tests and `Metric` tolerance tests.
