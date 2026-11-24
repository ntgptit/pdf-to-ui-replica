# Phase 2 — Object and component inventory

1. **Signatures**: `python3 -m pdfmeasure signatures --pdf X.pdf --pages 9-40` clusters shapes by (kind, coarse size class, fill, stroke, line width; corner radius is not part of the key, read it with `shapes`). Each cluster lists the pages it appears on. Recurring clusters are template parts; singletons are content. `--glyphs` adds letter-sized shapes (use it to find *coloured text*: the glyph signatures list each text colour with its count, which separates heading colour from body colour).
2. **Name roles**: write `roles.json` (format in `config-reference.md`): one rule per part (`tab`, `card`, `fold`, `bubble-stroke`, `hatch-ground`, …) matching kind + colour + size ranges. Colours are written as sRGB hex of the CMYK conversion; `tolerance` allows ±N per channel.
3. **Check coverage**: `python3 -m pdfmeasure roles --pdf X.pdf --pages 9-13 --rules roles.json --first-side left`. It prints only the matched roles per page. To find leftovers and double matches, compare it with `shapes` for the same page (shape counts per region), then tighten the rules until nothing in a template region is unnamed and nothing is matched twice.
4. **Components**: group roles into components (a *speech bubble* = bubble-stroke + bubble-fill + tail + shadow). Write `components.md`: component, its roles, variants (with/without number, left/right), what content slots it has.
5. Mark decorative bitmaps (hatch) and drawings (characters, animals, objects, scenes, stickers) with Approach `artwork`: they are described and handed to another agent to draw as originals ([11-artwork.md](11-artwork.md)), never copied.

Deliverables: `roles.json`, `components.md`.

## Phase 2A — Visual object inventory (agent-driven)
Signature clustering (above) only sees vector shapes. Pictures, characters and decoration must be found by looking.

1. Cut each page in scope into high-zoom tiles: `PYTHONPATH=. python3 -m pdfmeasure tiles --pdf X.pdf --page N --output O --mode pdf` (default 6 px/pt; each picture ≤ 1500 px so it is viewed unscaled; blank tiles skipped; the box in pt is on every tile). Look at **every tile**, covers and decorative pages included. A whole page (`pdftoppm -r 100`, 1.4 px/pt) is for orientation only: it hides numbered circles, arrowheads, dotted guides, hairlines and brush taper. Then record it: `state view --page N --view-kind inventory --note "<summary>" --tiles-file notes.json` (one observation per tile, smallest parts first; "nothing small" is allowed, a missing tile is not).
2. Identify: illustrations (people, animals, plants, objects), stickers, labels, icons, borders, backgrounds, and UI parts (frames, tables, bubbles, headings).
3. Group objects that need no independent rendering or interaction into one illustration, with a list of sub-objects. Split only for reuse, interaction or animation. **Small parts are listed even when they sit inside a drawing**: numbered markers (circle + digit), arrowheads, dotted guide lines, stroke taper, thin rules. They are the first thing a rebuild gets wrong and the first thing a low zoom hides.
4. Write `object-inventory.md`:

| ID | Page | Object | Region (pt) | Approach | Status |
|---|---|---|---|---|---|
| OBJ-001 | cover | decorative sticker | x, top, w, h | SVG | TODO |
| OBJ-004 | 9 | speech bubble | from `roles` | React/SVG | TODO |

   Status flows `TODO → DONE → VERIFIED`. Shared objects reference one component/asset.
5. Region, colour, stroke: from the measuring tools (`roles`, `report`), not by eye.
6. After building a page: look at the PDF image and the screenshot side by side, tick each row, add missed objects, build them.
7. `VERIFIED` = implemented, visually compared, and measured by phases 7–8 where measurable. No page is complete with a required row at `TODO` or `DONE`.
8. Keep the file updated whenever something new is found.

It is a mandatory coverage checklist, not a detection pipeline: do not add detection or segmentation models. Vision can miss small details, so the page-by-page inventory and the final screenshot review are required. Artwork is redrawn originally, never traced.

### Completion contract
Two levels, do not mix them up:
- `INVENTORY_COMPLETE`: every object in scope has been identified and recorded (an inventory-only task ends here; unbuilt rows stay `TODO`).
- `PAGE_COMPLETE`: a page you were asked to build, below.

- Every inventory row of a page being built ends as `VERIFIED` or `EXCLUDED: <reason>` (e.g. out of scope). The page is `PAGE_COMPLETE` only then.
- Evidence per row, written in the Notes column: *measurable* objects (frames, strokes, bubbles, fills) → the `verify` check/part names that cover them; *illustrations and other hard-to-measure objects* → a visual comparison note (what was compared, PDF image vs screenshot, what differs, accepted or not).
- A green `verify` run covers only the rows it names. Rows it does not name still need visual evidence; never infer them from passing measurements.
- Report counts: `VERIFIED n / total`, `EXCLUDED n`, and any row still `TODO`/`DONE`.
