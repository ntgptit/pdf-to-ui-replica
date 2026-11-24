# Phase 1 — Page analysis (layout first, components later)

Goal: the page frame and what is identical on every page.

1. Look at the rasters side by side (left page, right page, a page with a different section). Mark regions: running header/tab, title zone, main card or frame, columns, footer, page number, binding-side decoration.
2. For each region write coordinates in **points** (x0, top, x1, bottom) from the `shapes` output, not from the raster.
3. Decide per region: *constant* (same on all pages), *mirrored* (same distance from the outer edge, so x flips between left and right pages), *varying* (content).
4. After phase 2 (roles) run `report` to confirm with numbers (spread ≈ 0 = constant).
5. Write `layout.md`: page box, regions table, mirrored regions, which pages are which variants, and the open questions.

Rule: never start from components. A wrong page frame makes every later number wrong by a constant offset.
