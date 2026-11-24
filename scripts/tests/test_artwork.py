"""Artwork handoff. The fixtures reproduce the defects found in a real prompt review: cream paper counted as a colour, numerals under a "no text"
rule, people in a scene left out, guessed skin colours, the same picture briefed twice, swapped labels, "keep it as printed"."""
import io
import json
import subprocess
import sys
from pathlib import Path

import pytest
from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pdfmeasure import artwork, artwork_prompt  # noqa: E402

ZOOM = 4
PAPER = (246, 238, 225)  # cream paper of a printed book
LIME, GREEN, SKIN, HAIR, SHIRT = (143, 193, 28), (0, 155, 66), (210, 160, 125), (80, 55, 40), (40, 120, 200)


def page_image():
    image = Image.new("RGB", (300 * ZOOM, 300 * ZOOM), PAPER)
    draw = ImageDraw.Draw(image)
    box = lambda x, y, w, h, colour: draw.rectangle([x * ZOOM, y * ZOOM, (x + w) * ZOOM, (y + h) * ZOOM], fill=colour)  # noqa: E731
    box(20, 20, 30, 50, LIME)  # OBJ-001 number five
    box(70, 20, 50, 46, GREEN)  # OBJ-002 cucumber
    box(140, 20, 30, 50, LIME)  # OBJ-003 the number five again (another page in the book)
    box(20, 100, 40, 20, SHIRT); box(30, 80, 20, 20, SKIN); box(30, 78, 20, 6, HAIR)  # OBJ-004 a child  # noqa: E702
    box(100, 100, 120, 60, (120, 150, 90)); box(110, 110, 12, 12, SKIN); box(150, 110, 12, 12, (120, 80, 55))  # OBJ-005 classroom, two faces  # noqa: E702
    return image


ROWS = [
    {"id": "OBJ-001", "page": "9", "object": "number five", "region": "20, 20, 30, 50", "approach": "artwork", "status": "TODO"},
    {"id": "OBJ-002", "page": "9", "object": "cucumber", "region": "70, 20, 50, 46", "approach": "artwork", "status": "TODO"},
    {"id": "OBJ-003", "page": "9", "object": "match picture: number five", "region": "140, 20, 30, 50", "approach": "artwork", "status": "TODO"},
    {"id": "OBJ-004", "page": "9", "object": "child", "region": "20, 76, 40, 46", "approach": "artwork", "status": "TODO"},
    {"id": "OBJ-005", "page": "9", "object": "classroom", "region": "100, 100, 120, 60", "approach": "artwork", "status": "TODO"},
]


def briefs(lang="vi"):
    return artwork.make_briefs(ROWS, {9: page_image()}, ZOOM, "set-1", lang)


def complete(b):
    """A brief as a careful agent fills it."""
    b["common"].update(context="Korean course for Vietnamese learners, lesson 1-1: first vowels; pictures illustrate vocabulary words",
                       style_people="Flat children's-book style, medium warm outline, round eyes, simple mouth",
                       style_objects="Flat shapes, medium warm outline, one soft shadow, bright colours",
                       night="Softer, cooler light with a thin rim light; colours one step deeper; never inverted, no background",
                       avoid="No tracing or imitation of the book; no logos")
    o = {obj["id"]: obj for obj in b["objects"]}
    o["OBJ-001"].update(kind="object", identity="A big rounded numeral five with a leafy pattern", action="none", text_in_art="glyphs: 5",
                        states=[{"name": "default", "description": "still, upright"}])
    o["OBJ-002"].update(kind="object", identity="Two crossed cucumbers with small stems and a highlight", action="none", text_in_art="none",
                        states=[{"name": "default", "description": "still, crossed"}])
    o["OBJ-003"].update(reuse_of="OBJ-001")
    o["OBJ-004"].update(kind="character", identity="A child standing, hands down, smiling", action="Standing", text_in_art="none",
                        states=[{"name": "default", "description": "standing, smiling"}],
                        people=[{"name": "Mina", "role": "child", "origin": "Korea (name Mina in the dialogue)", "skin_tone": "medium, warm", "skin_hex": "#d2a07d", "markers": "school clothes"}])
    o["OBJ-005"].update(kind="scene", identity="A teacher at a blank board, two students at desks", action="The teacher points at the board", text_in_art="none",
                        states=[{"name": "default", "description": "lesson in progress"}],
                        people=[{"name": "teacher", "role": "teacher at the board", "origin": "Korea (lesson setting)", "skin_tone": "medium, warm", "skin_hex": "#d2a07d", "markers": "-"},
                                {"name": "Lan", "role": "student on the right", "origin": "Vietnam (name Lan on the cast page)", "skin_tone": "tan, warm", "skin_hex": "#785037", "markers": "-"}])
    return b


def problems_of(b):
    return artwork.brief_problems(b)


def test_paper_is_measured_and_left_out_of_the_palette():
    b = briefs()
    assert b["paper"]["9"] == "#f6eee1"
    for obj in b["objects"]:
        assert all(artwork._distance(c["hex"], "#f6eee1") > artwork.PAPER_DISTANCE for c in obj["palette"]), obj["id"]
    assert b["objects"][0]["palette"][0]["hex"] == "#8fc11c" and b["objects"][0]["palette"][0]["share"] > 0.9


def test_minimum_size_follows_the_screen_not_the_print():
    size = briefs()["objects"][0]["min_px"]
    assert max(size) >= artwork.DISPLAY_LONG_PX and abs(size[0] / size[1] - 30 / 50) < 0.01


def test_skin_candidates_come_from_the_measured_colours():
    child = briefs()["objects"][3]
    assert "#d2a07d" in child["skin_candidates"] and "#2878c8" not in child["skin_candidates"]


def test_a_complete_brief_passes():
    assert problems_of(complete(briefs())) == []


def test_set_level_fields_are_required_once():
    b = complete(briefs())
    b["common"]["style_objects"] = ""
    assert any("common.style_objects" in p for p in problems_of(b))


def test_text_in_art_must_be_decided_and_must_match_the_description():
    b = complete(briefs())
    b["objects"][1]["text_in_art"] = ""
    assert any("OBJ-002" in p and "not decided" in p for p in problems_of(b))
    b = complete(briefs())
    b["objects"][0]["text_in_art"] = "none"
    b["objects"][0]["identity"] = "A big rounded number 5 with a leafy pattern"
    assert any("OBJ-001" in p and "numeral" in p for p in problems_of(b))
    b = complete(briefs())
    b["objects"][4]["identity"] = "A teacher at a board showing ㅏ ㅓ ㅗ, two students"
    assert any("OBJ-005" in p and "ㅏ" in p for p in problems_of(b))


def test_every_person_in_a_scene_is_described_with_a_measured_skin_colour():
    b = complete(briefs())
    b["objects"][4]["people"] = []
    assert any("OBJ-005" in p and "scene must list its `people`" in p for p in problems_of(b))
    b = complete(briefs())
    b["objects"][4]["people"][1]["skin_hex"] = "#f6e1b6"  # a guess: no such colour in the area
    assert any("person 2 (Lan)" in p and "not near any colour measured" in p for p in problems_of(b))
    b = complete(briefs())
    b["objects"][4]["people"][1]["origin"] = ""
    assert any("person 2 (Lan)" in p and "origin is required" in p for p in problems_of(b))
    b = complete(briefs())
    b["objects"][4]["people"][0]["name"] = "Mina"  # Mina is in OBJ-004 with the same look: fine
    assert problems_of(b) == []
    b["objects"][4]["people"][0]["skin_hex"] = "#785037"
    assert any("'Mina' is also in OBJ-004" in p for p in problems_of(b))


def test_the_same_picture_twice_must_be_reused_and_swapped_labels_are_caught():
    b = complete(briefs())
    o = b["objects"][2]
    o.update(reuse_of="", kind="object", identity=b["objects"][0]["identity"], action="none", text_in_art="glyphs: 5", states=[{"name": "default", "description": "still"}])
    assert any("OBJ-001 and OBJ-003 are the same picture" in p and "reuse_of" in p for p in problems_of(b))
    o["identity"] = b["objects"][1]["identity"]  # labelled cucumber, but measured like the numeral five
    found = problems_of(b)
    assert any("OBJ-001 and OBJ-003 look alike" in p for p in found)
    assert any("OBJ-002 and OBJ-003 have the same description but very different colours" in p for p in found)


def test_reuse_needs_a_drawn_source_with_the_same_aspect():
    b = complete(briefs())
    b["objects"][2]["reuse_of"] = "OBJ-002"
    assert any("OBJ-003" in p and "aspect" in p for p in problems_of(b))
    b["objects"][2]["reuse_of"] = "OBJ-999"
    assert any("OBJ-003" in p and "must name an object that is drawn" in p for p in problems_of(b))


def test_copy_instructions_are_refused():
    b = complete(briefs())
    b["objects"][3]["people"][0]["markers"] = "giữ ngoại hình như hình in"
    assert any("OBJ-004" in p and "như hình in" in p for p in problems_of(b))


@pytest.mark.parametrize("lang, people_title, reuse_word", [("vi", "## Người trong hình", "dùng lại hình của OBJ-001"), ("en", "## People in the pictures", "reuses the picture of OBJ-001")])
def test_prompt_writes_shared_rules_once_lists_reuse_and_one_row_per_person(lang, people_title, reuse_word):
    text = artwork_prompt.render(complete(briefs(lang)), "artwork/set-1-20261124")
    assert text.count("Softer, cooler light") == 1 and text.count("Flat shapes, medium warm outline") == 1
    assert reuse_word in text and "`OBJ-003--default" not in text
    assert people_title in text and "| OBJ-005 | Lan | student on the right | Vietnam (name Lan on the cast page) | tan, warm | #785037 |" in text
    assert "| OBJ-001 | 9 | object | number five |" in text and "| glyphs: 5 |" in text
    manifest = json.loads(text.split("```json\n")[1].split("\n```")[0])
    assert sorted(manifest["objects"]) == ["OBJ-001", "OBJ-002", "OBJ-004", "OBJ-005"]  # every drawn picture, no reused one
    assert "![" not in text and "data:image" not in text


def svg(width=30, height=50, extra=""):
    return f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}">{extra}<circle cx="5" cy="5" r="3"/></svg>'.encode()


def raster(size, opaque=False, kind="WEBP"):
    image = Image.new("RGBA", size, (255, 255, 255, 255 if opaque else 0))
    ImageDraw.Draw(image).ellipse([20, 20, 100, 100], fill=(143, 193, 28, 255))
    buffer = io.BytesIO()
    image.save(buffer, kind, **({"lossless": True} if kind == "WEBP" else {}))
    return buffer.getvalue()


def test_delivered_files_are_validated():
    obj = complete(briefs())["objects"][0]
    need = tuple(obj["min_px"])
    assert artwork.validate_file("OBJ-001--default.webp", raster(need), obj) == []
    assert artwork.validate_file("OBJ-001--default.svg", svg(), obj) == []
    assert "unsafe SVG" in artwork.validate_file("a.svg", svg(extra="<script>alert(1)</script>"), obj)[0]
    assert "unsafe SVG" in artwork.validate_file("a.svg", svg(extra='<image href="https://x.test/a.png"/>'), obj)[0]
    assert "aspect" in artwork.validate_file("a.svg", svg(50, 50), obj)[0]
    assert any("under the minimum" in p for p in artwork.validate_file("a.webp", raster((120, 200)), obj))
    assert any("not transparent" in p for p in artwork.validate_file("a.png", raster(need, opaque=True, kind="PNG"), obj))
    assert "not accepted" in artwork.validate_file("a.gif", b"GIF89a", obj)[0]


def git(cwd, *args):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


def test_import_reads_the_separate_branch_and_maps_reused_pictures(tmp_path):
    remote, work, deliver = tmp_path / "remote.git", tmp_path / "work", tmp_path / "deliver"
    subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(remote)], check=True)
    for repo in (work, deliver):
        subprocess.run(["git", "clone", "-q", str(remote), str(repo)], check=True, capture_output=True)
        git(repo, "config", "user.email", "t@t")
        git(repo, "config", "user.name", "t")
    (work / "README.md").write_text("x")
    git(work, "checkout", "-q", "-b", "main")
    git(work, "add", ".")
    git(work, "commit", "-q", "-m", "init")
    git(work, "push", "-q", "origin", "main")
    git(deliver, "fetch", "-q", "origin")
    git(deliver, "checkout", "-q", "-b", "artwork/set-1-20261124", "origin/main")
    b = complete(briefs())
    by_id = {obj["id"]: obj for obj in b["objects"]}
    folder = deliver / "artwork-delivery" / "set-1"
    folder.mkdir(parents=True)
    names = []
    for obj_id in ("OBJ-001",):
        for _, name in artwork.expected_files(by_id[obj_id]):
            (folder / name).write_bytes(raster(tuple(by_id[obj_id]["min_px"])))
            names.append(name)
    (folder / "OBJ-002--default.webp").write_bytes(raster(tuple(by_id["OBJ-002"]["min_px"]), opaque=True))  # rejected
    (folder / "manifest.json").write_text(json.dumps({"set": "set-1", "objects": {"OBJ-001": names}}))
    (deliver / "README.md").write_text("changed by the other agent")
    git(deliver, "add", ".")
    git(deliver, "commit", "-q", "-m", "art")
    git(deliver, "push", "-q", "origin", "artwork/set-1-20261124")

    output = tmp_path / "out"
    artwork.folder(output).mkdir(parents=True)
    (artwork.folder(output) / artwork.BRIEFS).write_text(json.dumps(b))
    report = artwork.import_delivery(work, output, "artwork/set-1-20261124", tmp_path / "assets")
    assert sorted(report["accepted"]) == sorted(names) and report["stray_files"] == ["README.md"]
    assert any("OBJ-002--default.webp" in p and "not transparent" in p for p in report["rejected"])
    mapping = json.loads((artwork.folder(output) / artwork.MAP).read_text())["objects"]
    assert mapping["OBJ-003"]["reuse_of"] == "OBJ-001" and mapping["OBJ-003"]["files"] == mapping["OBJ-001"]["files"]
    assert mapping["OBJ-003"]["box_pt"] == [140, 20, 30, 50]  # placed in its own box
    remaining = " ".join(artwork.page_problems(output, 9))
    assert "OBJ-003" not in remaining and "OBJ-002" in remaining and "OBJ-004" in remaining
    assert subprocess.run(["git", "branch", "--show-current"], cwd=work, capture_output=True, text=True).stdout.strip() == "main"
    with pytest.raises(artwork.ArtworkError, match="not accepted"):
        artwork.import_delivery(work, output, "--upload-pack=x", tmp_path / "assets")
