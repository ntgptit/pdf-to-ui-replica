# Phases 4–6 — Models, apply, re-architect

## Phase 4 — models (no markup)
- `tokens.ts`: every measured number, in **points**, named by role, with source page in a comment. Example: `card = { x: 48.52, top: 128.27, width: 427.1, height: 527.09, radius: 13.5, stroke: 1.2 }`.
- `content.ts`: a schema (Zod) for what a page contains: sections, items by type (question, dialogue, word bank, table, match pairs…), variants, optional `layout` hints for hand-spaced pages.
- `fixtures.ts`: original sample pages that exercise every variant. Never use the book's text or characters.
- A unit test on tokens (key numbers present, positive) and on the schema (fixtures parse).

## Phase 5 — apply measurements (how to render faithfully)
Before building a part, read the knowhow entries of its tags (`knowhow list --tag lines --tag css`…): they are the defects earlier builds hit.
- **Scale**: the sheet is `container-type: inline-size` and defines `--wb-pt: calc(100cqw / PAGE_WIDTH_PT)`. All lengths are `calc(N * var(--wb-pt))`, so the page scales continuously and 1 CSS unit = 1 point at any width.
- **Strokes and outlines**: draw frames, rounded cards, bubbles, folds as inline SVG with a viewBox in points. A stroke is *centred* on the path: the outer box grows by half the stroke width, so inset the path by half a stroke to land the outer edge on the PDF's number. A line thinner than 1 CSS px drawn as a border, an outline or a thin box is painted 1 CSS px by Chrome at any pixel ratio (measured): draw hairlines as SVG strokes, or straight ones as a 1 px bar with `scale: 1 0.5` (knowhow KH-001); never round a measured thin line up to 1px.
- **Colours**: only from the generated palette css (custom properties). If the repo forbids hex outside a token file, add that one generated file to the guard's exemption.
- **Text**: use the closest available font (a font match is a stated limitation). Fix size in pt units and set `letter-spacing`/`word-spacing` in `em` **on the same element that declares font-size** (an em on an ancestor is computed there and does not inherit as em). Tune pitch with the phase 8 `pitch` method, not by eye.
- **Hatch patterns**: repeating-linear-gradient at the measured angle, period, and band; offset the phase per side.
- **Measuring hooks**: put `data-wb="<id>"` on every element you will verify (sheet, tab, card, bubble…). For a stroke drawn in an `<svg><rect>` the measuring script records it as `frame`; for a rule drawn as `::before`, add `data-measure-before`.
- **Artwork**: redraw original characters/icons as SVG; do not trace the book's.

Stack recipe (React + shadcn/ui + Tailwind v4): the sheet geometry above lives in part stylesheets scoped to `[data-view=sheet]`; the same parts also render the phone reading view (`12-reflow.md`, `13-react-shadcn-tailwind.md`).

## Phase 6 — architecture for reuse
The module layout is fixed, shared components first and built for many books: [14-module-layout.md](14-module-layout.md) (every repeated pattern is a kit primitive: contract in `core/kit/`, a reading kit, one kit per book in `books/<id>/kit/`; block renderers written once in `core/blocks/` composing primitives; per book tokens, generated palette and sheet CSS; a lazy `books/registry.ts`; one public `index.ts`), checked by `pdfmeasure structure` and by gates `pilot` and `book`. Rules: a pattern that appears twice is a kit primitive (never two components for it; `consistency` checks it renders the same on every page); a primitive reads tokens, never literals; geometry goes to the part's CSS through custom properties (never inline `left`/`top`/`width`); a repeated shape becomes one part with a variant prop; a "special" page element that appears twice becomes a part; the lab route renders every fixture page in both views (dev only; not a product screen).
