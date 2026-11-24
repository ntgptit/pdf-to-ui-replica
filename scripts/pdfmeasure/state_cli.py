"""Commands of the ebook harness: state (init | show | page | view | block | unblock) and gate."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import stack
from .ebook_state import GATES, OUTPUT_KINDS, EbookState, StateError, parse_pages


def command_state(args: argparse.Namespace) -> int:
    state = EbookState(args.output)
    try:
        if args.action == "init":
            if not args.pages:
                raise StateError("init needs --pages")
            state.init(kind=args.kind, pages=parse_pages(args.pages), pilot=parse_pages(args.pilot) if args.pilot else [], max_failed_rounds=args.max_failed_rounds)
            for problem in state.run_gate("scope", root=args.root):
                print(f"state init: scope problem: {problem}")
            found = state.scope.get("stack") or {}
            if found.get("supported"):
                print(f"state init: stack {stack.SUPPORTED} in {found['app']} (react {found['react']}, tailwindcss {found['tailwind']}, shadcn style {found['style'] or '-'})")
        elif args.action == "show":
            state.require()
            print("\n".join(state.coverage_lines()))
            if state.data.get("blocked"):
                print(f"\nBLOCKED: {state.data['blocked']['reason']}")
            return 0
        elif args.action == "page":
            if args.page is None or not args.status:
                raise StateError("page needs --page and --status")
            entry = state.set_page(args.page, args.status, note=args.note or "", reason=args.reason or "", inventory=args.inventory)
            print(f"page {args.page}: {entry['status']}")
        elif args.action == "view":
            if args.page is None:
                raise StateError("view needs --page")
            view_kind = args.view_kind or "qa"
            tile_notes = json.loads(Path(args.tiles_file).read_text(encoding="utf-8")) if args.tiles_file else None
            state.record_view(args.page, args.note or "", view_kind, tile_notes)
            print(f"page {args.page}: {view_kind} view recorded; it counts only for tiles and scans made before now")
        elif args.action == "module":
            if not args.path or not args.book:
                raise StateError("module needs --path (the ebook module folder, relative to the repository root) and --book (this book's id)")
            state.set_module(args.path, args.book or "", json.loads(args.map) if args.map else None)
            print(f"state: module {args.path}, book {args.book}" + (f", map {args.map}" if args.map else ""))
        elif args.action == "block":
            state.block(args.reason or "")
        elif args.action == "unblock":
            state.unblock()
    except StateError as error:
        print(f"state: {error}")
        return 2
    state.save()
    return 0


def command_gate(args: argparse.Namespace) -> int:
    state = EbookState(args.output)
    try:
        problems = state.run_gate(args.gate, inventory=args.inventory, root=args.root, build_cmd=args.build_cmd)
    except StateError as error:
        print(f"gate: {error}")
        return 2
    state.save()
    if problems:
        print(f"GATE {args.gate}: FAILED ({len(problems)})")
        print("\n".join(f"- {item}" for item in problems), file=sys.stdout)
        return 1
    print(f"GATE {args.gate}: PASSED")
    return 0


def register(add) -> None:
    state = add("state", command_state, "ebook harness state: init | show | page | view | block | unblock (status changes only through checks)")
    state.add_argument("action", choices=["init", "show", "page", "view", "module", "block", "unblock"])
    state.add_argument("--output", required=True)
    state.add_argument("--kind", choices=OUTPUT_KINDS, default="web-fixed", help="init: web-fixed by default (desktop print sheet and phone reading view, both required; decided without asking); analysis = phases 0-2A only")
    state.add_argument("--pages", help="init: pages in scope, e.g. 9-40")
    state.add_argument("--pilot", help="init: representative pages built and approved first, e.g. 9,12,20")
    state.add_argument("--root", default=".", help="init: repository root (the UI stack is detected under it)")
    state.add_argument("--path", help="module: the ebook module folder (references/14-module-layout.md)")
    state.add_argument("--book", help="module: this book's id (its folder under books/)")
    state.add_argument("--map", help='module: JSON mapping of the top folders to host names, e.g. {"core": "core", "books": "books"}')
    state.add_argument("--max-failed-rounds", type=int, default=3, help="init: fixes that did not hold before an issue leaves the agent's loop")
    state.add_argument("--page", type=int)
    state.add_argument("--status", help="page: NOT_STARTED -> IN_PROGRESS -> VERIFIED | ACCEPTED_LIMITATION | BLOCKED")
    state.add_argument("--view-kind", dest="view_kind", choices=["qa", "inventory"], help="view: inventory = after the PDF tiles (phase 2A), qa = after the scan and the pair tiles (phase 10; default)")
    state.add_argument("--tiles-file", help="view: JSON {tile id: what you saw on it}, one entry per non-blank tile of the manifest (ids are in tiles.json and in each picture's file name)")
    state.add_argument("--note", help="page/view: what changed, or what you looked at and saw")
    state.add_argument("--reason", help="page: required for ACCEPTED_LIMITATION and BLOCKED; block: why the whole build stops")
    state.add_argument("--inventory", help="page VERIFIED: object-inventory.md, rows of the page must be VERIFIED/EXCLUDED")

    gate = add("gate", command_gate, "evaluate a quality gate from the files (scope | inventory | pilot | book | delivery); exit 1 with the problems when it fails")
    gate.add_argument("gate", choices=GATES)
    gate.add_argument("--output", required=True)
    gate.add_argument("--inventory", help="object-inventory.md (gates inventory, pilot, book, delivery)")
    gate.add_argument("--root", default=".", help="repository root (delivery: temp folders, tracked files)")
    gate.add_argument("--build-cmd", help="delivery: the build command; it must exit 0")
