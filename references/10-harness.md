# Harness: state, gates, failed-round cap, Stop hook

The skill's phases say *what* to do. The harness makes the agent unable to say "done" while the files say otherwise. Everything here is a command that reads files; nothing is a self-report.

## Pick the output kind first (`state init`)
| Kind | Meaning | Gates that apply |
|---|---|---|
| `analysis` | phases 0-2A only (inspect, inventory) | scope, inventory |
| `replica-lab` | measured template pages in a dev lab | scope, inventory, pilot, book, delivery |
| `web-fixed` | web ebook: print view (page = PDF page) on wide screens and a reading view on phones | all, plus `reflow` per page |
| `web-reflowable` | web ebook: reading view everywhere; the print view stays as the measured reference | all, plus `reflow` per page |
| `epub-fixed` | EPUB fixed-layout export | all |

Decide it before building: it changes the architecture. Pilot pages are the representative ones (one per layout type and special object), chosen at init.

```
PYTHONPATH=. python3 -m pdfmeasure state init --output O --kind web-fixed --pages 9-40 --pilot 9,12,20 [--max-failed-rounds 3]
```
State file: `<O>/ebook-state.json` (git-ignored with the output folder). Never edit it by hand; `state init` refuses to run twice.

## Page statuses (only through `state page`)
`NOT_STARTED → IN_PROGRESS → VERIFIED | ACCEPTED_LIMITATION | BLOCKED`; `VERIFIED/ACCEPTED/BLOCKED → IN_PROGRESS` reopens.
- `NOT_STARTED → IN_PROGRESS` needs gate `inventory` passed; a non-pilot page also needs gate `pilot` passed.
- `→ VERIFIED` re-reads the evidence of the page and refuses unless all hold: a scan exists and is not `size_mismatch`; the latest `scan-*.md` ran verify (`every entry within tolerance`) with no failing geometry/zoom/text-layout entry; an overlay or heatmap image exists; no unresolved P0/P1 issue on the page; `tiles --mode pair` (≥ 6 px/pt) exists and is newer than that scan; a `state view` was recorded **after** both; with `--inventory`, every row of the page is `VERIFIED` or `EXCLUDED`.
- Typography: `NOT_STARTED → IN_PROGRESS` needs `typography --spec-only` for the page; `→ VERIFIED` needs a `typography --url` result at ≥ 8 px/pt, newer than the latest scan, that scored lines and has no ERROR (any style/attribute under 92 %). A WARNING (under 95 %) does not block but shows in `state show` and the report's coverage table.
- Module: `state module --path <module> --book <id>`; gates `pilot` and `book` run `structure` on the module (core + every book), check that this build's book has its folder, run the knowhow detectors (`knowhow scan`: an ERROR finding fails the gate), and need a passing `consistency` result newer than the latest scan (every kit primitive renders the same on every page of the lab).
- Desktop and mobile (kind `web-fixed`, the default): the `reflow` result must include the `--auto-url` check (reading view at 360 px, print sheet at 1280 and 1920 px).
- Reading view (kinds `web-fixed`, `web-reflowable`): `→ VERIFIED` needs a `reflow` result newer than the latest scan without ERROR (horizontal scroll, text under 16/14 px, targets under 24 px, zoom disabled, missing or reordered blocks). See `12-reflow.md`.
- Artwork: `→ VERIFIED` is refused while an object of the page in `artwork/briefs.json` has a state without an imported file (`artwork import`). Waiting for the user's branch is a normal stop: `state block --reason "waiting for the artwork branch"` and tell the user the next step in the chat.
- `ACCEPTED_LIMITATION` and `BLOCKED` need `--reason`; a limitation cannot cover an unresolved P0/P1.
- `state view --page N --note "what I looked at and saw"`: you record that you looked at the latest scan, its crops and **every tile of `tiles --mode pair`** (≥ 6 px/pt, made after the scan). Order: scan → `tiles --mode pair` → look → `state view`. A newer scan or newer tiles make the record stale.
- `state view --page N --view-kind inventory --note "…"`: the same for the inventory: after `tiles --mode pdf` of the page, naming the smallest parts you found.
- **One observation per tile:** both kinds need `--tiles-file notes.json` (`{"r0c0": "numbered markers 1 and 2, dotted arrow", "r0c1": "nothing small"}`) with an entry for every non-blank tile of the manifest; a missing, empty or invented tile id is refused. This does not prove you looked, but it makes skipping a tile a visible omission and leaves the observations in the state for review.

## Gates (`gate <name> --output O`; exit 1 + problem list on failure)
| Gate | Passes when |
|---|---|
| `scope` | kind chosen and pages listed; for any build, the supported UI stack found under `--root` (React + shadcn/ui + Tailwind CSS v4: `components.json` next to a `package.json` with react and tailwindcss ≥ 4). Run by `state init`; no page starts before it passes |
| `inventory` | `--inventory` file has `INVENTORY_COMPLETE`, OBJ rows, and a row for every page in scope (a page with nothing needs a row saying so); every page has `tiles --mode pdf` at ≥ 6 px/pt and a `state view --view-kind inventory` recorded after it |
| `pilot` | the module declared with `state module` follows the folder architecture (`pdfmeasure structure`, `14-module-layout.md`), and every pilot page is VERIFIED (re-checked now) or ACCEPTED_LIMITATION |
| `book` | the module still follows the folder architecture, every page in scope is VERIFIED (re-checked now: a later change that broke a page fails here) or ACCEPTED_LIMITATION, and no P0/P1 anywhere |
| `delivery` | gate `book` passes now; no run temp folder left (`qa-finish` was run); `report.md` exists and does not say NOT complete; no tracked PDF or tracked QA output; `--build-cmd` exits 0 |

Do not claim a gate you did not run. `qa-report` adds a "Page coverage" table from the state and says **Book NOT complete** while any page is unsettled.

## Failed-round cap (issues)
A fix that did not hold (`NEEDS_VERIFY` or `VERIFIED` back to `OPEN`/`FIXING`) counts as a failed round. At the cap (default 3, set at `state init`) the issue is forced out of your own loop: `CODEX_READY` when it has a `cause` (write the prompt with `codex-prompt`), else `BLOCKED` (write the cause first). It cannot return to `FIXING` unless you restart the count with a written reason: `issue status --id ISS-003 --status FIXING --note … --reset-rounds "why one more try is likely to work"`. Do not use it to dodge the cap.

## Stop hook
`hooks/ebook-gate-stop.py` (a Claude Code `Stop` hook; see the README for the `settings.json` entry) blocks ending the session while `<O>/ebook-state.json` shows a page IN_PROGRESS, a VERIFIED page that no longer passes, or an unresolved P0/P1. Default output folder `pdf-to-ui-output/` at the repo root, or `$PDF_TO_UI_OUTPUT`. It gives up after 4 reminders per session. A build that is really stuck: `state block --output O --reason "…"` (lets the session stop; say the blocker in the report); `state unblock` to resume.

## Text-layout check inside the scan
`visual-compare` with `--url` re-renders the text-layout check at 6 px/pt (the 0.3 pt pitch tolerance is under one pixel at 3 px/pt). With only `--react-image` it uses the given picture and never a tolerance finer than 1.5 px, and the scan says so in a WARNING; `verify` stays the exact check.

## What the harness does not decide
Whether a drawing looks right (you look; severity is your judgement), which layout is better (owner's choice), copyright and font licences (release phase).
