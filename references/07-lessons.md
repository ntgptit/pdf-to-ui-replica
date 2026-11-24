# Lessons and pitfalls (learned the hard way)

Process
- Zoom per part before judging. Whole-page overlays hid pixel errors; part crops at 12 px/pt exposed them.
- Layout first, then components, then numbers, then architecture, then verify. Skipping the page frame step produced constant offsets everywhere.
- Measure with the PDF's own vectors. Do not eyeball colours from a raster: CMYK shows differently.

Browser / CSS
- Chrome rounds SVG root positions to whole CSS px and draws borders < 1 px as 1 px: measure at 8 CSS px/pt; draw hairlines as SVG or backgrounds.
- Do not use browser `clip` for crops (rounding); cut the full-sheet raster by array index.
- `letter-spacing` / `word-spacing` in `em` is computed on the element that declares them: declare beside `font-size`, never on the sheet.
- SVG strokes are centred on the path: the outer box grows by half the stroke.
- Visible hatch band is the vector rect, not the larger bitmap box; phase differs per side.

Text
- Pitch estimator: first harmonic only (higher harmonics bias +4 %); ±0.3 pt with different content, exact with identical strings.
- Items on a page may be spaced by hand: record per-question spacing as `layout` hints instead of one constant.
- Compare line centres when content differs.

Repo hygiene
- One generated palette css file needs a colour-guard exemption; no other hex.
- Never commit the PDF, copyrighted characters or text; fixtures are original.
- Dev lab only: do not register as a product screen.
- Run long harnesses once, not after every edit.
