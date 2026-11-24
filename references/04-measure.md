# Phase 3 — Measure each component

1. **Quantities**: list in `quantities.json` every number you need (`name, role, field, pick, sides`). Fields: `x0 x1 top bottom width height linewidth corner_radius` plus path-derived ones in `report.field_value`. `pick` chooses the first/min/max shape of the role; `sides` restricts to left or right pages.
2. `python3 -m pdfmeasure report --pdf X.pdf --pages 9-40 --rules roles.json --quantities quantities.json --out report.md` → table with count, min, max, median, spread per quantity (and a `.json` copy). Constant = spread ≈ 0; otherwise investigate variant or per-page spacing.
3. **Palette**: `python3 -m pdfmeasure palette --pdf X.pdf --pages 9-40 --rules roles.json --out apps/.../palette.css` writes custom properties (`--pdf-green: #45a665`) for roles carrying `palette` (and `palette_from: stroke` when the colour is the stroke). CMYK→sRGB uses poppler-style 16-corner interpolation; do not hand-convert.
4. **Path details** (corner radius from the first arc, bubble tail base/length, fold corner, shadow offset): read from `shapes` output of that one shape and record in points in `components.md`.
5. **Text**: `python3 -m pdfmeasure lines ...` rebuilds text lines from glyph outlines (line ink boxes, line pitch). Record body line pitch, instruction pitch, item pitch per page type, and note where the page spaced items by hand (these become `layout` hints, phase 4).
6. **Typography spec** (before building, per page): `PYTHONPATH=. python3 -m pdfmeasure typography --pdf X.pdf --page N --output O --spec-only` writes `pages/page-NNN/typography-spec.{md,json}`. Per style (lines grouped by core height):
   - *core height*: the dense ink band (Hangul block height, Latin x-height), sub-pixel. It stands for the font size: with a text layer the exact size is listed too; without one, render a candidate font in the lab, measure it the same way and set `css size = candidate size × PDF core / candidate core`.
   - *weight*: stroke width / core height. Pick the weight (400/500/700…) whose ratio is closest; a bolder face changes it by 30 % or more.
   - *family*: contrast (vertical stroke width / horizontal stroke thickness; gothic/sans ≈ 1, myeongjo/serif clearly above) and ink proportion. With a text layer the font name decides.
   - *line pitch* (median, between dense-band centres) and *left edges* (indents in use).
   Record the chosen family, size, weight, line height and indents as tokens with the spec numbers next to them. Pick the face yourself (no question to the user): project faces first, then open-licensed ones (a brush face for a brush sample), keeping the best `typography --url` scores; report face, licence and scores. Text in a colour (white on a band, green heading) needs `--config` with `colours`.
7. **Hatch/pattern bitmaps**: measure the visible band (the vector rect), period and angle from a high-zoom crop, and per-side phase; the bitmap box is larger than what shows.

Deliverables: measurement report, palette css, numbers in `components.md`, `typography-spec.md` per page.
