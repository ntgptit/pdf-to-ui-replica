"""The prompt handed to the drawing agent, in the brief's language (vi, en). Set-level rules are written once; the table holds only what differs per
object; reused pictures are listed, not drawn twice; every person gets a row of their own."""
from __future__ import annotations

import json

from .artwork import DELIVERY_ROOT, expected_files

T = {
    "vi": {
        "title": "# Yêu cầu vẽ artwork gốc: bộ `{set}` ({drawn} hình cần vẽ, {reused} chỗ dùng lại)",
        "intro": "Bạn là agent vẽ minh hoạ. Hãy **vẽ mới, nguyên bản** từng hình theo bảng dưới. Không có ảnh gốc đi kèm; không tìm, sao chép, đồ lại hay bắt chước nét vẽ của bất kỳ sách nào. Chỉ dựa vào mô tả, kích thước và bảng màu.",
        "common": "## Bối cảnh chung",
        "style": "## Phong cách",
        "style_people": "- Người: {text}",
        "style_objects": "- Đồ vật, cảnh: {text} Không thêm mặt hay biểu cảm cho đồ vật trừ khi bảng ghi rõ.",
        "rules": "## Quy định kỹ thuật",
        "r_format": "- Định dạng theo cột Định dạng, mặc định **WebP có kênh alpha** (lossless hoặc quality ≥ 90); SVG được nhận (viewBox đúng tỉ lệ, không `<script>`, không link ngoài). Ảnh raster ít nhất bằng cột Ảnh tối thiểu, đúng tỉ lệ (sai lệch ≤ 3 %).",
        "r_background": "- Nền trong suốt. Hình nằm gọn trong khung, không cắt mép, chừa lề khoảng 2 % mỗi cạnh.",
        "r_colour": "- Màu: dùng các mã hex ở cột Bảng màu (đo từ trang in, đã bỏ màu giấy) theo thứ tự tỉ trọng; được thêm sắc độ trung gian, không đổi tông chủ đạo.",
        "r_states": "- Mỗi trạng thái và mỗi lớp hiệu ứng là một file riêng, **cùng khung hình, cùng điểm neo**, để thay nhau hoặc chồng lên nhau không bị nhảy.",
        "r_night": "- Bản tối (file `-night`): {text}",
        "r_layers": "- Lớp hiệu ứng (nếu có): file trong suốt chỉ chứa phần chuyển động (lấp lánh, hơi nước, quầng sáng…), để app tạo chuyển động.",
        "r_text": "- Chữ trong hình: chỉ vẽ đúng các ký tự ở cột Chữ trong hình; `none` = không có chữ, không có số. Vùng mà sách có chữ cho người học đọc (bảng, biển…) để trống: app sẽ đặt chữ thật lên.",
        "r_names": "- Tên file: `<ID>--<trạng thái>.webp`, bản tối `<ID>--<trạng thái>-night.webp`, lớp hiệu ứng `<ID>--layer-<tên>.webp` (đuôi theo cột Định dạng). Danh sách đủ ở cột File cần giao.",
        "avoid": "- Không được: {text}",
        "table": "## Hình cần vẽ",
        "head": ["ID", "Trang", "Loại", "Tên", "Khung (pt)", "Tỉ lệ", "Ảnh tối thiểu (px)", "Định dạng", "Bảng màu (hex, tỉ trọng)", "Chữ trong hình", "Bối cảnh riêng", "Đặc điểm nhận dạng", "Hành động", "Trạng thái", "Lớp hiệu ứng", "Bản tối riêng", "File cần giao"],
        "reused": "## Dùng lại (không vẽ)",
        "reused_line": "- {id} (trang {page}, {name}) dùng lại hình của {source}: không vẽ, không giao file.",
        "people": "## Người trong hình: quốc tịch, màu da (bắt buộc giữ đúng)",
        "people_intro": "Sách ngoại ngữ cố ý thể hiện nhiều quốc gia, dân tộc; người học thấy mình trong sách nên thiện cảm hơn. Vẽ đúng nguồn gốc và màu da của từng người, tôn trọng, không khuôn mẫu, không biếm hoạ đặc điểm dân tộc. Cùng tên = cùng một người ở mọi hình và mọi trạng thái. Bản `-night` chỉ đổi ánh sáng, không đổi màu da hay nét mặt.",
        "people_head": ["ID", "Người", "Vai trong hình", "Quốc tịch / văn hoá", "Màu da", "Mã màu da", "Dấu hiệu văn hoá"],
        "delivery": "## Bàn giao (bắt buộc)",
        "d1": "1. Tạo một **branch mới, tách biệt** với branch đang làm việc, từ branch mặc định của repo, tên gợi ý: `{branch}`. Không làm trên branch hiện tại, không merge, không mở PR.",
        "d2": "2. Chỉ thêm file vào thư mục `{folder}/`, không sửa file nào khác của repo.",
        "d3": "3. Thêm `{folder}/manifest.json` (mỗi hình: danh sách file đã giao; file chưa vẽ được thì bỏ ra và ghi lý do vào `notes`):",
        "d4": "4. Commit, push branch đó lên remote.",
        "d5": "5. Trả lời bằng: tên branch, danh sách file đã giao, file chưa giao và lý do.",
        "none": "-",
    },
    "en": {
        "title": "# Original artwork request: set `{set}` ({drawn} pictures to draw, {reused} reused)",
        "intro": "You are an illustration agent. **Draw new, original** pictures from the table below. No source image is provided; do not look for, copy, trace or imitate the drawing of any book. Work only from the descriptions, sizes and palettes.",
        "common": "## Shared context",
        "style": "## Style",
        "style_people": "- People: {text}",
        "style_objects": "- Objects and scenery: {text} No faces or expressions on objects unless the table says so.",
        "rules": "## Technical rules",
        "r_format": "- Format per the Format column, by default **WebP with alpha** (lossless or quality ≥ 90); SVG is accepted (viewBox at the right aspect, no `<script>`, no external links). Rasters at least the Minimum size column, at the right aspect (within 3 %).",
        "r_background": "- Transparent background. The picture fits its frame, nothing cut off, about 2 % margin on each side.",
        "r_colour": "- Colours: use the hex values of the Palette column (measured on the printed page, paper removed) in order of share; in-between shades are fine, the main tones stay.",
        "r_states": "- Every state and every effect layer is a separate file on the **same canvas and anchor**, so they swap or stack without jumping.",
        "r_night": "- Night version (`-night` file): {text}",
        "r_layers": "- Effect layers (if any): transparent files holding only what moves (sparkle, steam, glow…), animated by the app.",
        "r_text": "- Text in the picture: draw exactly the characters of the Text column; `none` = no letters, no numerals. Where the book shows text for the learner to read (a board, a sign), leave it blank: the app sets real text there.",
        "r_names": "- File names: `<ID>--<state>.webp`, night `<ID>--<state>-night.webp`, effect layer `<ID>--layer-<name>.webp` (extension per the Format column). The full list is in the Files column.",
        "avoid": "- Do not: {text}",
        "table": "## Pictures to draw",
        "head": ["ID", "Page", "Kind", "Name", "Box (pt)", "Aspect", "Minimum size (px)", "Format", "Palette (hex, share)", "Text in picture", "Own context", "Identity", "Action", "States", "Effect layers", "Own night note", "Files to deliver"],
        "reused": "## Reused (not drawn)",
        "reused_line": "- {id} (page {page}, {name}) reuses the picture of {source}: not drawn, no files.",
        "people": "## People in the pictures: origin and skin tone (keep exactly)",
        "people_intro": "Foreign-language books show many nationalities and ethnicities on purpose: learners who see themselves in the book like it more. Draw each person's origin and skin tone as listed, respectfully, without stereotypes or caricature. One name = one person in every picture and state. The `-night` file changes the light only, never skin tone or features.",
        "people_head": ["ID", "Person", "Role in the picture", "Origin / culture", "Skin tone", "Skin hex", "Cultural markers"],
        "delivery": "## Delivery (required)",
        "d1": "1. Create a **new branch, separate** from the working branch, from the repository's default branch, suggested name: `{branch}`. Do not work on the current branch, do not merge, do not open a PR.",
        "d2": "2. Add files only under `{folder}/`; change no other file of the repository.",
        "d3": "3. Add `{folder}/manifest.json` (per picture: the files delivered; leave out what you could not draw and say why in `notes`):",
        "d4": "4. Commit and push that branch.",
        "d5": "5. Reply with: the branch name, the files delivered, the files not delivered and why.",
        "none": "-",
    },
}


def _cell(text) -> str:
    return " ".join(str(text or "").split()).replace("|", "/")


def _row(cells: list[str]) -> str:
    return "| " + " | ".join(cells) + " |"


def render(briefs: dict, branch_hint: str) -> str:
    t = T[briefs.get("lang", "vi")]
    common = briefs.get("common") or {}
    objects = briefs["objects"]
    drawn = [obj for obj in objects if not obj.get("reuse_of")]
    reused = [obj for obj in objects if obj.get("reuse_of")]
    folder = f"{DELIVERY_ROOT}/{briefs['set']}"
    lines = [t["title"].format(set=briefs["set"], drawn=len(drawn), reused=len(reused)), "", t["intro"], "", t["common"], "", _cell(common.get("context")), "", t["style"]]
    if common.get("style_people"):
        lines.append(t["style_people"].format(text=_cell(common["style_people"])))
    if common.get("style_objects"):
        lines.append(t["style_objects"].format(text=_cell(common["style_objects"])))
    lines += ["", t["rules"], t["r_format"], t["r_background"], t["r_colour"], t["r_states"]]
    if common.get("night"):
        lines.append(t["r_night"].format(text=_cell(common["night"])))
    if any(obj.get("layers") for obj in drawn):
        lines.append(t["r_layers"])
    lines += [t["r_text"], t["r_names"]]
    if common.get("avoid"):
        lines.append(t["avoid"].format(text=_cell(common["avoid"])))
    lines += ["", t["table"], "", _row(t["head"]), _row(["---"] * len(t["head"]))]
    for obj in drawn:
        box = obj["box_pt"]
        size = obj.get("min_px") or obj.get("min_png_px")
        colours = ", ".join(f"{c['hex']} {c['share']:.0%}" for c in obj["palette"]) or t["none"]
        states = "; ".join(f"**{s['name']}**: {_cell(s['description'])}" for s in obj["states"])
        layers = "; ".join(f"**{layer['name']}**: {_cell(layer['description'])}" for layer in obj.get("layers") or []) or t["none"]
        files = ", ".join(f"`{name}`" for _, name in expected_files(obj))
        lines.append(_row([obj["id"], str(obj["page"]), obj["kind"], _cell(obj["name"]), f"{box[2]:g} × {box[3]:g}", str(obj["aspect"]), f"{size[0]} × {size[1]}", obj.get("format", "webp"), colours,
                           _cell(obj.get("text_in_art")), _cell(obj.get("context")) or t["none"], _cell(obj.get("identity")), _cell(obj.get("action")), states, layers,
                           _cell(obj.get("night")) or t["none"], files]))
    if reused:
        lines += ["", t["reused"]] + [t["reused_line"].format(id=obj["id"], page=obj["page"], name=_cell(obj["name"]), source=obj["reuse_of"]) for obj in reused]
    people = [(obj, person) for obj in drawn for person in obj.get("people") or []]
    if people:
        lines += ["", t["people"], "", t["people_intro"], "", _row(t["people_head"]), _row(["---"] * len(t["people_head"]))]
        for obj, person in people:
            lines.append(_row([obj["id"], _cell(person.get("name")) or t["none"], _cell(person.get("role")) or t["none"], _cell(person.get("origin")), _cell(person.get("skin_tone")),
                               str(person.get("skin_hex", "")), _cell(person.get("markers")) or t["none"]]))
    manifest = {"set": briefs["set"], "objects": {obj["id"]: [name for _, name in expected_files(obj)] for obj in drawn}, "notes": ""}
    lines += ["", t["delivery"], t["d1"].format(branch=branch_hint), t["d2"].format(folder=folder), t["d3"].format(folder=folder),
              "```json", json.dumps(manifest, ensure_ascii=False, indent=2), "```", t["d4"], t["d5"], ""]
    return "\n".join(lines)
