"""Folder architecture of the ebook module (core kit + blocks, books with their kits): a clean module passes; each rule catches its own breach."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from module_fixture import make_module  # noqa: E402
from pdfmeasure import structure  # noqa: E402

BOOK = "books/vitamin-1"


@pytest.fixture
def module(tmp_path):
    return make_module(tmp_path)


def codes(problems):
    return {p.split()[0] for p in problems}


def edit(path: Path, old: str, new: str):
    text = path.read_text()
    assert old in text
    path.write_text(text.replace(old, new))


def test_a_clean_module_with_two_books_passes(module):
    assert structure.check(module) == []
    assert structure.kit_primitives(module / "core") == ["example-label", "answer-line"]


def test_missing_entry_files(module):
    (module / "core/kit/contract.ts").unlink()
    (module / BOOK / "styles/sheet.css").unlink()
    (module / "books/registry.ts").unlink()
    found = structure.check(module)
    for text in ("core/kit/contract.ts is missing", "vitamin-1/styles/sheet.css is missing", "registry.ts is missing"):
        assert any(text in p for p in found), text


def test_models_are_pure_typescript(module):
    (module / BOOK / "model/x.tsx").write_text("export const x = <b />\n")
    (module / "core/model/ids.ts").write_text("import { useState } from 'react'\n")
    assert codes(structure.check(module)) == {"L2"}


def test_blocks_and_parts_draw_nothing_themselves(module):
    block = module / "core/blocks/example-box/example-box.tsx"
    edit(block, "<AnswerLine lead=\"arrow\" />", "<span>→</span><svg><line x1=\"0\" /></svg>")
    found = structure.check(module)
    assert any(p.startswith("L16") and "example-box.tsx" in p for p in found)


def test_every_book_implements_the_whole_kit_and_nothing_else(module):
    import shutil

    shutil.rmtree(module / BOOK / "kit/answer-line")
    (module / BOOK / "kit/arrow-line").mkdir()
    (module / BOOK / "kit/arrow-line/arrow-line.tsx").write_text("export const A = () => <span data-kit=\"arrow-line\">→</span>\n")
    (module / BOOK / "kit/arrow-line/arrow-line.css").write_text("[data-book=vitamin-1][data-view=sheet] .a { top: 0; }\n")
    found = structure.check(module)
    assert any(p.startswith("L17") and "vitamin-1/kit/answer-line is missing" in p for p in found)
    assert any(p.startswith("L17") and "arrow-line is not in core/kit/contract.ts" in p for p in found)
    shutil.rmtree(module / "core/kit/reading/example-label")
    assert any("core/kit/reading/example-label is missing" in p for p in structure.check(module))


def test_kit_components_carry_data_kit_and_book_kits_have_css(module):
    edit(module / BOOK / "kit/example-label/example-label.tsx", 'data-kit="example-label" ', "")
    (module / BOOK / "kit/answer-line/answer-line.css").unlink()
    found = structure.check(module)
    assert any(p.startswith("L5") and 'data-kit="example-label"' in p for p in found)
    assert any(p.startswith("L3") and "answer-line.css is missing" in p for p in found)


def test_a_book_part_is_the_exception_and_says_why(module):
    part = module / BOOK / "parts/dialogue"
    part.mkdir(parents=True)
    (part / "dialogue.css").write_text("[data-book=vitamin-1][data-view=sheet] .wb-d { top: 0; }\n")
    (part / "dialogue.tsx").write_text("export const D = ({ id }: { id: string }) => <ol data-block={id} />\n")
    assert any(p.startswith("L18") for p in structure.check(module))
    (part / "dialogue.tsx").write_text("// unique-structure: speech bubbles with tails exist only in this book\nexport const D = ({ id }: { id: string }) => <ol data-block={id} />\n")
    assert structure.check(module) == []


def test_inline_geometry_is_refused(module):
    edit(module / BOOK / "kit/example-label/example-label.tsx", "style={{ '--label-h'", "style={{ height")
    assert any(p.startswith("L4") and "sets height" in p for p in structure.check(module))


def test_book_css_is_scoped_to_its_book_and_the_sheet(module):
    css = module / BOOK / "kit/example-label/example-label.css"
    edit(css, "[data-book=vitamin-1][data-view=sheet] .wb-label", "[data-view=sheet] .wb-label")
    assert any(p.startswith("L6") and "not scoped to [data-book=vitamin-1]" in p for p in structure.check(module))
    edit(css, "[data-view=sheet] .wb-label", "[data-book=vitamin-1] .wb-label")
    assert any(p.startswith("L6") and "[data-view=sheet]" in p for p in structure.check(module))


def test_core_knows_no_book_and_books_know_no_other_book(module):
    edit(module / "core/views/page-view.tsx", "import { ExampleBox }", "import style from '../../books/vitamin-1'\nimport { ExampleBox }")
    edit(module / BOOK / "kit/example-label/example-label.tsx", "import { LABEL }", "import { LABEL as OTHER } from '../../../sejong-4a/model/tokens'\nimport { LABEL }")
    found = structure.check(module)
    assert any(p.startswith("L13") for p in found) and any(p.startswith("L14") and "imports book 'sejong-4a'" in p for p in found)


def test_every_book_is_loaded_lazily(module):
    (module / "books/registry.ts").write_text("import vitamin from './vitamin-1'\nexport const BOOKS = { 'vitamin-1': vitamin, 'sejong-4a': () => import('./sejong-4a') }\n")
    found = structure.check(module)
    assert any(p.startswith("L15") and "'vitamin-1' lazily" in p for p in found) and any(p.startswith("L15") and "statically" in p for p in found)


def test_public_api_fixtures_text_size_and_palette(module):
    (module / "index.ts").write_text("export { LABEL } from './books/vitamin-1/model/tokens'\nexport { ExampleLabel } from './books/vitamin-1/kit/example-label/example-label'\n")
    (module / "core/blocks/example-box/example-box.tsx").write_text("import { FIXTURE } from '../../../books/vitamin-1/fixtures/pages'\nexport const B = ({ id }: { id: string }) => <p data-block={id} aria-label=\"Example\" />\n" + "\n".join(f"export const v{i} = {i}" for i in range(40)))
    (module / "books/sejong-4a/styles/palette.css").write_text("[data-book=sejong-4a] { --wb-green: #8fc11c; }\n")
    found = structure.check(module, max_lines=30)
    for code in ("L7", "L8", "L10", "L11", "L12", "L13"):
        assert any(p.startswith(code) for p in found), code


def test_a_host_maps_the_top_folders(tmp_path):
    module = make_module(tmp_path)
    (module / "books").rename(module / "editions")
    for path in module.rglob("*.ts*"):
        path.write_text(path.read_text().replace("./books/", "./editions/").replace("../../books/", "../../editions/"))
    assert any("registry.ts is missing" in p for p in structure.check(module))
    assert structure.check(module, {"books": "editions"}) == []


def test_every_book_definition_is_checked_at_compile_time(module):
    edit(module / BOOK / "index.ts", "} satisfies BookStyle", "}")
    assert any(p.startswith("L20") and "vitamin-1/index.ts" in p for p in structure.check(module))
    edit(module / BOOK / "index.ts", "const style = {", "const style = defineBook({")
    assert not any(p.startswith("L20") for p in structure.check(module))


def add_book(module: Path, book: str):
    """A third book of the fixture, built like the other two."""
    from module_fixture import book_files

    for relative, text in book_files(book, "#3a9b5c").items():
        path = module / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    edit(module / "books/registry.ts", "'sejong-4a': () => import('./sejong-4a') }", f"'sejong-4a': () => import('./sejong-4a'), '{book}': () => import('./{book}') }}")


def use_series(module: Path, book: str):
    """The book takes its example label from the series kit and drops its own copy."""
    import shutil

    shutil.rmtree(module / f"books/{book}/kit/example-label")
    edit(module / f"books/{book}/index.ts", "import { ExampleLabel } from './kit/example-label/example-label'", "import { ExampleLabel } from '../_series/sejong/kit/example-label/example-label'")


def make_series(module: Path):
    folder = module / "books/_series/sejong/kit/example-label"
    folder.mkdir(parents=True)
    (folder / "example-label.tsx").write_text("export function ExampleLabel({ children }: { children: React.ReactNode }) { return <span data-kit=\"example-label\" className=\"wb-label\">{children}</span> }\n")
    (folder / "example-label.css").write_text("[data-series=sejong][data-view=sheet] .wb-label { display: inline-flex; }\n")


def test_a_series_kit_is_premature_under_three_books(module):
    make_series(module)
    use_series(module, "vitamin-1")
    use_series(module, "sejong-4a")
    found = structure.check(module)
    assert any(p.startswith("L19") and "used by 2 book(s)" in p for p in found)
    assert not any(p.startswith("L17") for p in found)  # the books' kits are complete with the series kit
    add_book(module, "sejong-4b")
    use_series(module, "sejong-4b")
    assert structure.check(module) == []


def test_a_series_kit_is_scoped_and_knows_no_book(module):
    make_series(module)
    for book in ("vitamin-1", "sejong-4a"):
        use_series(module, book)
    add_book(module, "sejong-4b")
    use_series(module, "sejong-4b")
    css = module / "books/_series/sejong/kit/example-label/example-label.css"
    css.write_text("[data-view=sheet] .wb-label { display: inline-flex; }\n")
    tsx = module / "books/_series/sejong/kit/example-label/example-label.tsx"
    tsx.write_text("import { LABEL } from '../../../../vitamin-1/model/tokens'\n" + tsx.read_text())
    found = structure.check(module)
    assert any(p.startswith("L6") and "[data-series=sejong][data-view=sheet]" in p for p in found)
    assert any(p.startswith("L14") and "a series kit knows no book" in p for p in found)
