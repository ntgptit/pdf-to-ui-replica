# Building the views in React + shadcn/ui + Tailwind CSS v4

The supported stack. `gate scope` refuses a build elsewhere (other stacks come later). It finds the app by its `components.json` next to a `package.json` with `react` and `tailwindcss` ≥ 4; use that app's aliases (`components.json` → `aliases`) and its CSS entry (`tailwind.css`) wherever this file says `@/…` or `app.css`. Read the project's own rules first (token guards, folder rules, its list of controls with 44 px targets): they win over the defaults here.

Folder layout: [14-module-layout.md](14-module-layout.md) (`core/` shared by every book, one style pack per book in `books/<id>/`).

## 1. Shared components first, many books, two views
- **Every repeated pattern is one kit primitive** (`core/kit/contract.ts`): the example label, an answer line with its lead arrow or speaker, a rule, a frame, an item number, a table header… Blocks compose primitives and never draw them. This is mandatory: two copies of a pattern drift between pages (`14-module-layout.md`, knowhow KH-011).
- **Blocks are written once** in `core/blocks/<kind>/`; the same block renders the sheet and the reading view, because the kit it receives changes with the view.
- **Each book implements the whole kit** in its style (`books/<id>/kit/<primitive>/`, measured tokens, generated palette); the reading kit (`core/kit/reading/`) is the app's design and serves every book.
- A **view** is chosen at run time: `sheet` (the print page of one book) or `reading` (the phone reading view, `12-reflow.md`).

## 2. Contract, kit, registry, root
```ts
// core/kit/contract.ts: the patterns, their props and variants
export const KIT = ['example-label', 'answer-line', 'rule', 'frame', 'item-number', 'table-header'] as const
export interface Kit {
  ExampleLabel: ComponentType<{ children: ReactNode }>
  AnswerLine: ComponentType<{ lead?: 'arrow' | 'speaker'; speaker?: string; end?: string }>   // one line, every lead
  Rule: ComponentType<{ weightPt?: number }>
  Frame: ComponentType<{ label?: ReactNode; children: ReactNode }>
  ItemNumber: ComponentType<{ n: number }>
  TableHeader: ComponentType<{ children: ReactNode }>
}
// core/contracts.ts
export interface BookStyle { id: string; series?: string; page: { widthPt: number; bodyPt: number }; kit: Kit; parts?: Partial<Record<BlockKind, ComponentType<BlockProps>>> }
export const defineBook = <const T extends BookStyle>(style: T): T => style   // same check as `satisfies BookStyle`
```
```ts
// books/registry.ts: each book is its own chunk; the id type comes from the registry
export const BOOKS = { 'vitamin-1': () => import('./vitamin-1'), 'sejong-4a': () => import('./sejong-4a') } as const
export type BookId = keyof typeof BOOKS                     // EbookPage({ book: BookId }): a wrong id fails at compile time
// books/vitamin-1/index.ts: checked at compile time (rule L20): a missing primitive or a wrong variant prop fails in the editor
import './styles/palette.css'
import './styles/sheet.css'
const style = {
  id: 'vitamin-1',                                            // stays the literal type 'vitamin-1' with `as const` or defineBook
  page: { widthPt: PAGE.width, bodyPt: TYPE.body },
  kit: { ExampleLabel, AnswerLine, Rule, Frame, ItemNumber, TableHeader },
} as const satisfies BookStyle                              // or: export default defineBook({ … })
export default style
```
Checked with the repository's TypeScript (7.0): `as const satisfies BookStyle` and `defineBook` (a `const` type parameter) both fail on a missing primitive or a wrong variant prop and keep the id literal (`'vitamin-1'`); plain `satisfies BookStyle` also checks the kit but widens the id to `string`; an annotation (`const style: BookStyle`) widens it too; a cast (`as BookStyle`) hides a missing primitive: never cast.
```tsx
// core/views/book-page.tsx: the view picks the kit
export function BookPage({ style, page }: { style: BookStyle; page: Page }) {
  const ref = useRef<HTMLDivElement>(null)
  const width = useContainerWidth(ref)                      // ResizeObserver; 0 before the first measure
  const choice = useReaderChoice()                          // 'auto' | 'sheet' | 'reading', stored with the project's preferences
  const sheetBodyPx = width ? style.page.bodyPt * (width / style.page.widthPt) : 0
  const view: ReaderView = choice !== 'auto' ? choice : sheetBodyPx >= 12 ? 'sheet' : 'reading'
  return (
    <ReaderViewContext.Provider value={view}>
      <KitContext.Provider value={view === 'sheet' ? style.kit : READING_KIT}>
        <div ref={ref} data-book={style.id} data-series={style.series} data-view={view} className="@container/book">
          <ViewSwitch value={choice} />{/* shadcn ToggleGroup: Auto · Page · Reading */}
          <PageView style={style} page={page} />
        </div>
      </KitContext.Provider>
    </ReaderViewContext.Provider>
  )
}
// core/views/page-view.tsx: content order; a book part only where its structure is unique
export function PageView({ style, page }: { style: BookStyle; page: Page }) {
  const view = useReaderViewValue()
  return page.blocks.map((block) => {
    const Block = (view === 'sheet' && style.parts?.[block.kind]) || BLOCKS[block.kind]
    return <Block key={block.id} block={block} />
  })
}
```
- `bodyPt` comes from the book's typography spec; 12 px is the threshold `reflow` reports as `phone_default`. Decide by the **container** width; before the first measure render `reading`. Switching keeps the reader's place (scroll back to the `data-block` in view).

## 3. A block, written once
```tsx
// core/blocks/example-box/example-box.tsx: composes primitives, draws nothing
export function ExampleBox({ block }: BlockProps) {
  const { Frame, ExampleLabel, AnswerLine } = useKit()
  return (
    <Frame label={<ExampleLabel>{t('example')}</ExampleLabel>}>
      <div data-block={block.id} className="wb-example">
        {block.lines.map((line) => <AnswerLine key={line.id} lead={line.lead} speaker={line.speaker} end={line.end} />)}
      </div>
    </Frame>
  )
}
```

## 4. A primitive, once per book (and once for reading)
Every rule of a book is scoped to the book **and** the sheet (rule L6); the palette is generated under the book (`pdfmeasure palette … --selector '[data-book=vitamin-1]'`). Inline style sets only custom properties (rule L4). Mark the root with `data-kit` and the pieces that must line up with `data-kit-part`.
```tsx
// books/vitamin-1/kit/answer-line/answer-line.tsx
export function AnswerLine({ lead, speaker, end }: AnswerLineProps) {
  return (
    <span data-kit="answer-line" data-kit-variant={lead ?? 'none'} className="wb-answer"
          style={{ '--lead-gap': pt(LINE.leadGap), '--rule-lift': pt(LINE.ruleLift), '--rule-weight': pt(LINE.rulePt) } as CSSProperties}>
      {lead === 'arrow' ? <span data-kit-part="lead" className="wb-answer-lead" aria-hidden>→</span> : null}
      {lead === 'speaker' ? <span data-kit-part="lead" className="wb-answer-speaker">{speaker}:</span> : null}
      <svg data-kit-part="rule" aria-hidden className="wb-answer-rule" preserveAspectRatio="none" viewBox="0 0 100 1">
        <line x1="0" y1="0.5" x2="100" y2="0.5" />
      </svg>
      {end ? <span data-kit-part="end">{end}</span> : null}
    </span>
  )
}
```
```css
/* books/vitamin-1/kit/answer-line/answer-line.css: alignment of the arrow, the rule and the end mark lives here, once */
[data-book=vitamin-1][data-view=sheet] .wb-answer { display: flex; align-items: baseline; gap: var(--lead-gap); }
[data-book=vitamin-1][data-view=sheet] .wb-answer-rule { flex: 1; height: 1px; align-self: flex-end; margin-bottom: var(--rule-lift); }
/* the stroke keeps its measured weight at any width (stretched viewBox, non-scaling stroke): 0.3 pt stays 0.3 pt, never a 1 px border (KH-001) */
[data-book=vitamin-1][data-view=sheet] .wb-answer-rule line { stroke: currentColor; stroke-width: var(--rule-weight); vector-effect: non-scaling-stroke; }
```
The reading kit's `AnswerLine` in `core/kit/reading/answer-line/` is the same contract with Tailwind classes (`flex items-baseline gap-2`, the rule as `h-px scale-y-50 origin-bottom bg-current`).

### Thin lines (knowhow KH-001, measured)
A line of 0.5 px stays 0.5 px only as an SVG stroke or a scaled 1 px bar; `border: 0.5px` is painted exactly like `border: 1px`. Take the width from the tokens; never round it up to 1px.
```tsx
// a rule that scales with the sheet: stroke in points inside a pt viewBox
<svg aria-hidden viewBox={`0 0 ${w} 1`} className="wb-rule-svg"><line x1="0" y1="0.5" x2={w} y2="0.5" stroke="currentColor" strokeWidth={RULE.width} /></svg>
// a fixed 0.5 px line (straight): a 1 px bar scaled by half
<div aria-hidden className="h-px scale-y-50 origin-top bg-current" />
```

## 4b. A structure that differs between the views
When the sheet and the reading view need a different structure for the same pattern (speech bubbles on the sheet, stacked speaker lines on a phone), that difference lives **inside the primitive**: the book's `DialogueLine` draws a bubble, the reading kit's `DialogueLine` draws a row; the block stays one:
```tsx
// core/blocks/dialogue/dialogue.tsx
export function Dialogue({ block }: BlockProps) {
  const { DialogueLine } = useKit()
  const audio = useLineAudio(block.lines)                         // core/behaviours
  return <ol data-block={block.id}>{block.lines.map((line) => <DialogueLine key={line.id} speaker={line.speaker} onPlay={() => audio.play(line.id)}>{line.text}</DialogueLine>)}</ol>
}
```
Wide grids wrap in the reading kit (`grid grid-cols-4 @md/book:grid-cols-8 gap-2`), match-the-pairs become stacked pairs or selects; the reading page frame is `mx-auto max-w-prose px-4 space-y-6`.

## 5. Typography: from the spec to the Tailwind scale
Body in the reading view is `text-base` (16 px) or `text-lg`; every other style keeps its **ratio to body** from the typography spec (core heights), rounded to the nearest step of the default scale; never arbitrary sizes.
| Ratio to body | Class |
|---|---|
| ≤ 0.9 (captions, labels, ruby) | `text-sm` (14 px, the floor) |
| 0.9–1.1 | `text-base` |
| 1.1–1.3 | `text-lg` |
| 1.3–1.5 | `text-xl` |
| 1.5–1.85 | `text-2xl` |
| > 1.85 | `text-3xl` |
The reading view uses the app's font for every book; the sheet view uses the book's faces (in its `sheet.css`, under `[data-book=<id>]`). Font choice is decided without asking (SKILL.md, "Decide without asking"): faces the project ships first, then open-licensed ones, kept by their `typography` scores. Line height `leading-relaxed` for body. Inputs: shadcn `Input` keeps its size; it renders text ≥ 16 px in the reading view.

## 6. shadcn components in the reading view
Use the project's installed components (`aliases.ui`), never hand-made controls: `Button` (audio, reveal answer), `Input`/`Textarea` (answers), `ToggleGroup` (view switch), `Card` only when a block needs a surface, `Dialog`/`Sheet` for an enlarged diagram. Colours come from the theme tokens (`bg-background`, `text-foreground`, `text-muted-foreground`, `border`); a book's own colours stay in its sheet (palette CSS) and in content accents that carry meaning (a highlighted vowel), through its palette variables. Interactive targets: at least 24 px; 44 px where the project's rule asks for it (`reflow --config target_warn_px`).

## 7. Artwork
From the book's `artwork-map.json` (`11-artwork.md`); assets per book (`<static>/<book-id>/…`). Light and night files swap with Tailwind's dark variant; effect layers stack on the same box and stop when the reader prefers less motion. The aspect ratio is a custom property read by a utility (rule L4):
```tsx
<figure data-block={block.id} className="relative aspect-(--art-ratio)" style={{ '--art-ratio': `${box.w} / ${box.h}` } as CSSProperties}>
  <img src={files['default/light']} alt="" className="size-full object-contain dark:hidden" />
  <img src={files['default/night']} alt="" className="hidden size-full object-contain dark:block" />
  {layer && <img src={layer} alt="" aria-hidden className="pointer-events-none absolute inset-0 size-full motion-safe:animate-pulse motion-reduce:hidden" />}
</figure>
```
Sheet view: the figure sits at its measured box (the book's kit CSS for the figure primitive). Reading view: `w-full max-w-xs mx-auto` (content art) or smaller (decoration). `alt` comes from the content model when the picture carries meaning, empty when decorative.

## 8. Checklist
- [ ] Pattern: one kit primitive in `core/kit/contract.ts`, implemented in `core/kit/reading/` and in every book's `kit/`; blocks use it through `useKit()` and draw nothing themselves; differences are variant props.
- [ ] Block: schema, behaviour and renderer in `core/`; a book part only for a unique structure (`// unique-structure: …`).
- [ ] `data-block` on blocks, `data-kit` on primitives and `data-kit-part` on the pieces that must line up; `data-text-role` on non-body text; `data-wb` on measured sheet elements.
- [ ] Book CSS under `[data-book=<id>][data-view=sheet]`, palette under `[data-book=<id>]`; inline style sets custom properties only.
- [ ] Reading kit: Tailwind scale and theme tokens only; one column; body ≥ 16 px, small text ≥ 14 px; nothing wider than the container.
- [ ] Registry: the book loads lazily; core imports no book; a book imports no other book.
- [ ] Verified: `structure`; `consistency` on the lab (sheet and reading); geometry/zoom/typography on the sheet view; `reflow` (with `--auto-url`) on the reading view; screenshots looked at.
