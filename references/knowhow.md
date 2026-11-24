# Knowhow: defects that come back

GENERATED from `knowhow.json` by `pdfmeasure knowhow`. Do not edit by hand; add or update entries with the command.

| ID | Title | Tags | Seen | Detector |
|---|---|---|---|---|
| KH-001 | Hairline thinner than 1 CSS px is drawn 1 px thick | lines, css | 0 | ERROR, ERROR, WARNING, WARNING, WARNING |
| KH-002 | em letter or word spacing declared on an ancestor | text, css | 0 | - |
| KH-003 | SVG stroke is centred on its path | svg, lines | 0 | - |
| KH-004 | Inline geometry blocks the reading view | react, layout, reading | 0 | - |
| KH-005 | Tailwind variant named print clashes with @media print | tailwind, css | 0 | ERROR |
| KH-006 | Answer input under 16 px makes the phone zoom on focus | reading, tailwind | 0 | WARNING |
| KH-007 | Pattern bitmap box is larger than its visible band | measuring, css | 0 | - |
| KH-008 | Small parts lost at low zoom | measuring, artwork | 0 | - |
| KH-009 | Fixed pixel font size in the sheet | text, css | 0 | WARNING |
| KH-010 | Printed text is outlined: no font name or size in the PDF | fonts, text, measuring | 0 | - |
| KH-011 | One pattern built by several components drifts between pages | react, layout, text | 1 | ERROR, ERROR |

## KH-001 · Hairline thinner than 1 CSS px is drawn 1 px thick

- **Symptom:** Printed rules of 0.25-0.5 pt (answer lines, table rules, frames) come out 1 px and heavy: the code says 0.5px or the agent rounded it to 1px, and the page looks darker and coarser than the book.
- **Cause:** Chrome rounds a non-zero border or outline width under 1 CSS px up to 1 CSS px, at any device pixel ratio (computed border-top-width reads 1px for 0.5px and for calc(var(--wb-pt) * 0.3)). A box under 1 px high used as a bar (height: max(calc(var(--wb-pt) * 0.3), 0.5px)) is painted 1 CSS px too.
- **Fix:** To get a line under 1 CSS px (for example 0.5 px): (a) an SVG stroke, stroke-width="0.5" (or the measured pt in a pt viewBox): right for frames, curves and lines that scale with the sheet; (b) a 1 px bar scaled down: height 1px; background currentColor; scale: 1 0.5; transform-origin: top (vertical line: width 1px; scale: 0.5 1), in Tailwind `h-px scale-y-50 origin-top`. Never border/outline 0.5px (painted 1px), never a box under 1px, a half-filled gradient or a 0.5px box-shadow (lost or unstable), and never round a measured thin line up to 1px.
- **Check:** zoom part with method `line` (thickness within 0.1 pt of the PDF); in a screenshot at DPR 2 a 0.5 px line is exactly one device pixel row; look at the pair tiles (>= 6 px/pt).
- **Detector:** ERROR in `*.css`: border/outline width that scales with --wb-pt or is under 1 px is painted at least 1 px: draw the hairline as an SVG stroke or a background bar (KH-001); ERROR in `*.tsx`: sub-pixel border utility is painted 1 px: draw the hairline as an SVG stroke or a background bar (KH-001); WARNING in `*.css`: a box under 1 px is painted 1 CSS px: a hairline drawn as a thin box is too thick; use an SVG stroke (KH-001); WARNING in `books/*.css`: a printed line drawn with the default 1px: take its width from the measured tokens; under 1 px draw it as an SVG stroke or a 1px bar with scale (KH-001); WARNING in `books/*.tsx`: Tailwind `border` is 1px: a printed line takes its width from the tokens; under 1 px use an SVG stroke or `h-px scale-y-50 origin-top` (KH-001)
- **Corrected 2026-11-24:** Measured in Chromium (Playwright), DPR 1 and 2: border 0.5px, border calc(var(--wb-pt)*0.3) and a max(...,0.5px) background bar all paint 1.00 CSS px of ink; an SVG stroke of 0.204 paints 0.20 px.
- **Corrected 2026-11-24:** Measured in Chromium at DPR 1, 2 and 3: border 0.5px and border 1px paint the same 1.00 CSS px; SVG stroke-width 0.5 and a 1px bar with scale 1 0.5 (also scaleY and Tailwind scale-y-50) paint 0.50 px at every DPR (one crisp device row at DPR 2), scale 1 0.3 paints 0.30; a half-filled 1px gradient paints 0 / 0.5 / 0.33 px and a 0.5px box-shadow nothing.

## KH-002 · em letter or word spacing declared on an ancestor

- **Symptom:** Letter pitch or word gaps stay wrong whatever value is set; the typography or zoom pitch check keeps failing by a constant amount.
- **Cause:** letter-spacing and word-spacing in em are computed with the font size of the element that declares them and inherited as a fixed length; declared on the sheet (16 px) they barely affect 10 pt body text.
- **Fix:** Declare em spacing in the same rule as the font-size it scales with (.wb-body, .wb-instruction…), never on the sheet or a wrapper.
- **Check:** typography --url (family and spacing scores) and zoom method `pitch` on a body line.

## KH-003 · SVG stroke is centred on its path

- **Symptom:** A frame, card or bubble drawn in SVG is larger than the PDF by half its stroke on every side; geometry checks of the outer edge fail by stroke/2.
- **Cause:** An SVG stroke is painted half inside and half outside the path; the PDF's numbers are the outer edge of the ink.
- **Fix:** Inset the path by half the stroke width (x + w/2, width - w) so the outer edge lands on the measured box; keep vector-effect off so the stroke scales with the sheet.
- **Check:** geometry check of the part's outer box within 0.1-0.3 pt; zoom method `extent`.

## KH-004 · Inline geometry blocks the reading view

- **Symptom:** The reading view cannot move or resize a block: Tailwind reading: classes have no effect on the sheet's positions and widths.
- **Cause:** Inline style beats every class; geometry written as style={{ left, width }} cannot be overridden by the reading view or another book.
- **Fix:** Inline style sets only CSS custom properties (style={{ '--card-left': pt(x) }}); the part's CSS under [data-book=<id>][data-view=sheet] reads them.
- **Check:** pdfmeasure structure (rule L4); reflow at 320-768 px.

## KH-005 · Tailwind variant named print clashes with @media print

- **Symptom:** Styles meant for the print sheet appear only when the page is printed, or the reading view breaks when printing.
- **Cause:** Tailwind already defines the print: variant as @media print; a custom variant with the same name shadows or conflicts with it.
- **Fix:** Name the view variants sheet: and reading: (@custom-variant sheet (&:where([data-view=sheet], [data-view=sheet] *))).
- **Check:** compile the classes with the project's Tailwind and read the generated selectors.
- **Detector:** ERROR in `*.css`: custom variant `print` clashes with Tailwind's @media print variant: name it `sheet` (KH-005)

## KH-006 · Answer input under 16 px makes the phone zoom on focus

- **Symptom:** On a phone, tapping an answer field zooms the page in and the reader has to zoom back out.
- **Cause:** Mobile Safari zooms into any focused input whose text is smaller than 16 px.
- **Fix:** Inputs in the reading view render text at 16 px or more (keep the shadcn Input size; do not add text-xs or text-sm to it).
- **Check:** reflow (body text >= 16 px) and a manual focus on a phone-sized viewport.
- **Detector:** WARNING in `*.tsx`: input text under 16 px makes phones zoom on focus (KH-006)

## KH-007 · Pattern bitmap box is larger than its visible band

- **Symptom:** A hatch or texture band is too tall or starts too high; its stripes have the wrong phase.
- **Cause:** The PDF places a larger bitmap and clips it with a vector rectangle; the bitmap's box is not what shows.
- **Fix:** Measure the clipping vector rectangle for the band, the period and angle from a high-zoom crop, and the phase per page side; draw it with repeating-linear-gradient.
- **Check:** zoom part over the band with method `align` and `ink`.

## KH-008 · Small parts lost at low zoom

- **Symptom:** Numbered stroke-order circles, arrowheads, dotted guides or thin tails are missing or wrong in the rebuild and nobody noticed.
- **Cause:** A whole page viewed at 1.4-3 px/pt (and scaled down again when shown) hides parts a few points large; enlarged crops add no detail.
- **Fix:** Inventory and QA on `tiles` at >= 6 px/pt (pdf mode for the inventory, pair mode after each scan); list small parts as their own inventory rows.
- **Check:** state view with one observation per tile (the harness requires it).

## KH-009 · Fixed pixel font size in the sheet

- **Symptom:** Sheet text is right at one width and wrong at every other: it does not scale with the page.
- **Cause:** A font-size in px inside the sheet CSS ignores --wb-pt, while every other length scales with the sheet width.
- **Fix:** Sheet sizes are calc(var(--wb-pt) * <pt>) from the typography spec; px sizes belong to the reading view's Tailwind scale only.
- **Check:** typography --url at two sheet widths gives the same scores.
- **Detector:** WARNING in `books/*.css`: px font size in a book's sheet CSS does not scale with the page: use calc(var(--wb-pt) * pt) (KH-009)

## KH-010 · Printed text is outlined: no font name or size in the PDF

- **Symptom:** pdfplumber finds no characters; the font family and size have to be guessed and the rebuilt text looks off.
- **Cause:** Print PDFs often convert text to outlines: only the ink shapes remain.
- **Fix:** Run typography --spec-only (core height, stroke, contrast), render candidate faces (project faces first, then open-licensed ones) and keep the best typography --url scores; scale the CSS size by the core-height ratio.
- **Check:** typography --url: every style PASS (>= 95 %) or a reported WARNING with its cause.

## KH-011 · One pattern built by several components drifts between pages

- **Symptom:** The same element looks different from page to page: the example label's text sits lower on one page, the lead arrow rides on the answer rule on one page and sits above it on another, a table header pill is smaller.
- **Cause:** Each page or block drew the pattern itself (its own pill, its own arrow and rule) instead of using one shared component, so spacing and alignment were tuned separately and drifted.
- **Fix:** Every repeated pattern is one kit primitive (core/kit/contract.ts), implemented once per book in books/<id>/kit/<primitive>/ and used by every block; blocks never draw labels, lines, arrows or frames themselves (structure rules L16-L18).
- **Check:** `consistency --url <lab>`: every instance of a primitive has the same height, text centre and part positions within 1 px; `structure` passes.
- **Detector:** ERROR in `core/blocks/*.tsx`: a block draws a pattern itself: use the kit primitive (KH-011); ERROR in `books/*/parts/*.tsx`: a book part draws a pattern itself: use the kit primitive (KH-011)
- **Seen:** sejong-4a vs example-4a rebuild (2026-11-24)
