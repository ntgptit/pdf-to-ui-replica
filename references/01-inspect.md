# Phase 0 — Scope and inspect the PDF

Goal: know what the PDF *is* before measuring anything.

1. **Page size**: `pdfplumber` gives width/height in points (1 pt = 1/72 in). Print PDFs often have bleed: note the page box and use the same box everywhere.
2. **Text layer?** Print-ready PDFs usually *outline* text: no extractable characters, but every letter is a filled vector shape. Check with `python3 -m pdfmeasure shapes --pdf X.pdf --pages N` (few shapes = text layer exists; hundreds of tiny `curve` shapes = outlined text). With outlined text you cannot read *content* (type your own original fixtures) but you can measure ink positions.
3. **What survives**: vector rects/curves/lines keep exact coordinates, line widths and **CMYK** fills. Raster images (hatch bitmaps, portraits) keep only their placement box.
4. **Pick pages**: a representative set (each layout variant, both left and right pages). Record `--first-side left|right`: the parity of the first page you list. Mirrored margins and binding-side decorations flip between sides.
5. **Raster for the eye**: `pdftoppm -r 100 -png -f 9 -l 13 X.pdf out/p`. Look at them for orientation only (1.4 px/pt: small parts are not visible); the inventory is done on `tiles` at ≥ 6 px/pt (phase 2A). Crop for detail: `pdftoppm -r 288 -x X -y Y -W W -H H -f N -l N`. (288 px/in = 4 px/pt, 864 = 12 px/pt.)
6. **Rights**: if the PDF is copyrighted, keep it out of the repo. You will commit measurements, original fixtures and original artwork only (no book characters, no book text).

## Classify the PDF (decides the tools)
| Type | How to recognise | Approach |
|---|---|---|
| Vector + text layer | `shapes` shows few glyph shapes; text extracts | read text, measure vectors |
| Outlined text | hundreds of tiny `curve` shapes per page, no text | measure glyph ink and lines; read content visually; fixtures are your own |
| Scan / raster | one full-page image, no vector shapes | visual analysis only; do not write `roles.json`; say the measuring tools do not apply |
| Mixed | some pages vector, some images | per page: vectors measured, pictures inventoried visually |
Also note crop box and rotation.

Deliverable: a note of page list, page size, text-layer status, sides.
