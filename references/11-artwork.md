# Artwork handoff: characters, objects, scenes

The book's drawings (characters, animals, objects, scenes, stickers) are **never traced, copied or cut out**, and they are not left as gaps either. They are described from the page, drawn as original artwork by another agent the user runs, delivered on a **separate branch**, then checked and fitted into the rebuilt pages. This file is project-neutral: it names no framework, CSS library or folder; use the project's own conventions where it says "the app".

## 0. Inventory: mark the artwork
In `object-inventory.md` give every drawing the Approach `artwork` (frames, bubbles, rules and icons built with SVG/CSS keep their own approach). One row per placed drawing, with its region in pt from the tiles. When the book prints the same picture twice (a vocabulary picture repeated in an exercise), keep both rows: the brief links them with `reuse_of`.

## 1. Brief (measured)
```
PYTHONPATH=. python3 -m pdfmeasure artwork brief --output O --pdf X.pdf --inventory object-inventory.md --set <set-id> [--lang vi|en]
```
Writes `<output>/artwork/briefs.json`. Measured per object: page, box (pt), aspect, **minimum raster size** (4 px/pt of the print box, and the long side at least 1024 px: screens show pictures larger than print), **palette** (sRGB hex with share; the page's paper colour is measured on the margins and removed, anti-aliasing shades merged), a wider palette and **skin-colour candidates** (hints only). Defaults: `format: webp`, `themes: ["light", "night"]`, transparent background. `--lang` sets the language of the prompt: the user's language.

## 2. Describe (you, from the high-zoom tiles)
Look at every drawing on its `tiles --mode pdf` pictures, then fill `briefs.json`.

**Once per set, `common`:**
| Field | What to write |
|---|---|
| `context` | the book, the audience, the lesson: shared by every picture (an object's own `context` holds only what differs) |
| `style_people` | how people are drawn (line, shading, faces) so all of them look like one family |
| `style_objects` | how objects and scenery are drawn; kept apart from people, so no face ends up on a cucumber |
| `night` | the rule for every `-night` file (light direction, softer or deeper colours, rim light; never an inversion, never a background) |
| `avoid` | what must not appear anywhere (logos, background, …) |

**Per object:**
| Field | What to write |
|---|---|
| `kind` | `character`, `object`, `scene` or `decoration` |
| `identity` | what it is and what makes it recognisable for its **meaning**: role, action, proportions, the colours by part. Not the book's costume design detail by detail: the other agent designs the look |
| `action` | what it does; `none` for a still object |
| `text_in_art` | **decide it**: `none` (no letters, no numerals) or `glyphs: <exact characters>` when they are the subject (a numeral picture). Text a learner must read (a board, a sign) is left blank in the drawing and set by the app as real text. The prompt is refused when the description names characters of a non-Latin script or a numeral while this says `none` |
| `states` | every state the page or an interaction needs, first `default`, each with a description |
| `layers` | optional effect layers, each `{name, description}`: transparent files on the same canvas, animated by the app |
| `night` | only what differs from `common.night` for this picture |
| `people` | **every person in the picture**, for characters and for scenes: `{name, role, origin, skin_tone, skin_hex, markers}`. A scene without people says why in `people_none` |
| `reuse_of` / `distinct_from` | `reuse_of: OBJ-x` when this is the same picture as a drawn one (it is drawn once and placed twice; same aspect within 3 %); `distinct_from: [OBJ-y]` when the tool flags two pictures as alike but they are different |

**People: origin and skin.** Foreign-language books show many nationalities and ethnicities on purpose; learners who see themselves in the book like it more, so keep the book's mix exactly.
- `origin`: the country or culture the book shows the person as, with the clue in brackets, strongest first: the book's cast page, the name in the dialogue or caption, the lesson's setting, clothes, flags, food. `unknown: <why>` only when the page gives no clue.
- `skin_tone`: light / medium / olive / tan / brown / dark, with a warm, neutral or cool undertone.
- `skin_hex`: measured on the face. It must be near a colour measured in the area (`skin_candidates`, `palette_wide`); a guessed value is refused.
- The same `name` in several objects must keep the same origin and skin colour.
- Describe respectfully; never through a stereotype.

**Refused wording:** phrases that ask for a copy of the printed drawing ("as printed", "like the book", "như hình in", …): the other agent has no image and must not copy.

## 3. Prompt
```
PYTHONPATH=. python3 -m pdfmeasure artwork prompt --output O [--branch artwork/<set-id>-<yyyymmdd>]
```
Refuses an incomplete or contradictory brief and lists every problem. Checks across objects: the same picture briefed twice (alike box and colours) must use `reuse_of`; the same description with very different colours means a swapped label; people's looks must be consistent. Writes `<output>/artwork/prompt.md` in the brief's language: shared context, style and rules **once**; a table of the pictures to draw (box, aspect, minimum size, format, palette, text in picture, own context, identity, action, states, layers, own night note, files to deliver); the reused pictures (not drawn); a table with **one row per person** (origin, skin tone, skin hex, cultural markers); the delivery contract: a **new branch separate from the current one**, files only under `artwork-delivery/<set-id>/`, a `manifest.json` listing every drawn picture, push, no merge, no PR, reply with the branch name.

Before handing it over, read the prompt once as the drawing agent would: is every picture understandable without the book? Are the people and their origins all there?

## 4. Hand over in the chat
Send the prompt in the chat (paste it, and attach `prompt.md` when the client can show files), then tell the user, in their language:

> **Artwork: your next step**
> 1. Open your drawing agent (another session) and paste the whole prompt above.
> 2. It draws N pictures (M files with states, night versions and layers) and pushes them to a **separate** branch, for example `artwork/<set-id>-<date>`. Do not merge that branch.
> 3. When it is done, send me the **branch name** here. I will check every file and fit it into the pages that are missing pictures.
> Meanwhile the pages with artwork wait; I continue with the rest.

While waiting, pages with artwork cannot become VERIFIED (the harness names the missing files). Continue the other pages; when nothing else is left, `state block --reason "waiting for the artwork branch from the user"` and end the turn with the message above.

## 5. Import (after the user gives the branch)
```
PYTHONPATH=. python3 -m pdfmeasure artwork import --output O --branch <branch> --dest <asset folder of the rebuild> --root <repo>
```
Fetches the branch and reads it **without checking it out**; the work branch never changes. Every expected file (each state and layer, in each theme) is looked up by name; another accepted format of the same name is taken too. Checks: format (WebP, SVG, PNG), aspect within 3 %, raster size at least the minimum, transparent corners, SVG without script, event handlers, foreignObject, DOCTYPE/ENTITY or external links. Good files go to `--dest` (one asset folder per book, e.g. `<static>/<book-id>/artwork/`); `artwork-map.json` maps object → `<state or layer-name>/<light|night>` → file with the box in pt (a reused picture points at the drawn one's files, in its own box); `import-report.md` lists accepted, rejected with the reason, missing, and files the other agent changed outside its folder (not imported).

## 6. Fit into the rebuild
Replace each placeholder with the delivered file from `artwork-map.json`, at the box in pt, keeping the aspect (contain, or an SVG viewBox). States become the variants the page or an interaction switches between. Themes: show the light file in light mode and the `-night` file in dark mode (Tailwind: `dark:hidden` / `hidden dark:block`). Effect layers sit on top in the same box and are animated by the app, stopped for readers who prefer less motion (`motion-safe:` / `motion-reduce:hidden`). Code: `13-react-shadcn-tailwind.md` §7. Then the usual page checks: `visual-compare`, `tiles --mode pair` (look at every drawing in place), `typography`, `state view`; tick the inventory rows (an artwork row is VERIFIED when the delivered drawing fits its box and matches the brief, not when it looks like the book).

## 7. Report in the chat (always)
End with a message to the user, never silently: what was imported, what was rejected or missing and why, the pages now complete, and the pictures to review (the pair tiles or triptych of the pages where art was fitted, and `import-report.md`). When files were rejected or missing, include a ready-to-paste follow-up prompt for the other agent that lists only those files and the reasons.
