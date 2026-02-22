from __future__ import annotations

import io
import json
import textwrap
from io import BytesIO
from typing import Dict, Any

from PIL import Image, ImageDraw, ImageFont

from AI.journal_assistant.pipeline.generator import generate_text, generate_image
from AI.journal_assistant.pipeline.templates.journal_template.character_analysis import build_character_analysis_prompt
from AI.journal_assistant.pipeline.templates.journal_template.character_copy import build_character_copy_prompt
from AI.journal_assistant.pipeline.templates.journal_template.character_image_prompt import build_character_image_prompt


def _fallback_base_png_bytes(nickname: str) -> bytes:
    """
    외부 이미지 생성이 빈 bytes(None)로 떨어질 때, 파이프라인이 500으로 죽지 않도록
    '메모리에서' 기본 베이스 PNG를 생성해 bytes로 반환한다.
    (디스크 저장 없음. 이후 흐름은 동일하게 S3 업로드 → DB 저장)
    """
    w, h = 1024, 1024
    img = Image.new("RGBA", (w, h), (245, 245, 245, 255))
    draw = ImageDraw.Draw(img)

    # header bar
    draw.rectangle((0, 0, w, 120), fill=(46, 125, 50, 255))
    font = ImageFont.load_default()
    draw.text((36, 42), f"{nickname}'s Food Journal", fill=(255, 255, 255, 255), font=font)

    # placeholder character area
    draw.rectangle((80, 160, w - 80, h - 240), outline=(200, 200, 200, 255), width=4)
    draw.text((120, 200), "AI image generation failed.\nUsing fallback base.", fill=(60, 60, 60, 255), font=font)

    # bottom blank area (text box)
    draw.rectangle((0, h - 240, w, h), fill=(255, 255, 255, 230))

    out = BytesIO()
    img.save(out, format="PNG")
    return out.getvalue()


def _safe_json_load(s: str) -> Dict[str, Any]:
    s = (s or "").strip()
    try:
        return json.loads(s)
    except Exception:
        a = s.find("{")
        b = s.rfind("}")
        if a != -1 and b != -1 and b > a:
            return json.loads(s[a:b + 1])
        return {}


def _compose_final(base_png: bytes, paragraph: str) -> bytes:
    """
    base_png 위에 하단 텍스트 박스 + 문단을 그려서 최종 PNG 반환
    """
    base = Image.open(BytesIO(base_png)).convert("RGBA")

    W, H = base.size
    bottom_h = int(H * 0.26)
    pad = 36

    draw = ImageDraw.Draw(base)

    # bottom background (white-ish)
    y0 = H - bottom_h
    draw.rectangle((0, y0, W, H), fill=(255, 255, 255, 230))

    # title line
    draw.line((pad, y0 + 16, W - pad, y0 + 16), fill=(46, 125, 50, 255), width=3)

    # paragraph
    font = ImageFont.load_default()
    wrapped = textwrap.fill(paragraph or "", width=54)
    draw.text((pad, y0 + 34), wrapped, fill=(30, 30, 30, 255), font=font)

    out = BytesIO()
    base.save(out, format="PNG")
    return out.getvalue()


def run_journal_template(payload: Dict[str, Any]) -> bytes:
    """
    payload expected:
    - member: { nickname, ... }
    - reviews, allergy_tags, ...
    """
    member = payload.get("member") or {}
    nickname = member.get("nickname") or "User"

    # 1) character spec from analysis
    analysis_prompt = build_character_analysis_prompt(payload)
    analysis_raw = generate_text(analysis_prompt)
    character_spec = _safe_json_load(analysis_raw)

    # 2) copy paragraph
    # ✅ FIX: build_character_copy_prompt는 키워드 전용 인자(*, ...)라 positional 호출하면 TypeError 발생
    # ✅ character_spec(dict)를 JSON 문자열로 변환해서 넘김
    character_json = character_spec if isinstance(character_spec, str) else json.dumps(character_spec, ensure_ascii=False)
    copy_prompt = build_character_copy_prompt(character_json=character_json, nickname=nickname)
    paragraph = generate_text(copy_prompt).strip()

    if not paragraph:
        paragraph = f"{nickname} accidentally discovered a mukbang powered by today’s meals."

    # 3) Image: character with blank bottom area
    img_prompt = build_character_image_prompt(character_spec)
    base_png = generate_image(img_prompt)
    if not base_png:
        # 외부 생성 실패(빈 bytes) -> 메모리 fallback 베이스로 진행
        print("[run_journal_template] base image empty -> fallback base used")
        base_png = _fallback_base_png_bytes(nickname)

    # 4) Compose final
    return _compose_final(base_png, paragraph)

# from __future__ import annotations
#
# import io
# import json
# import textwrap
# from io import BytesIO
# from typing import Dict, Any
#
# from PIL import Image, ImageDraw, ImageFont
#
# from AI.journal_assistant.pipeline.generator import generate_text, generate_image
# from AI.journal_assistant.pipeline.templates.journal_template.character_analysis import build_character_analysis_prompt
# from AI.journal_assistant.pipeline.templates.journal_template.character_copy import build_character_copy_prompt
# from AI.journal_assistant.pipeline.templates.journal_template.character_image_prompt import build_character_image_prompt
#
#
# def _fallback_base_png_bytes(nickname: str) -> bytes:
#     """
#     외부 이미지 생성이 빈 bytes(None)로 떨어질 때, 파이프라인이 500으로 죽지 않도록
#     '메모리에서' 기본 베이스 PNG를 생성해 bytes로 반환한다.
#     (디스크 저장 없음. 이후 흐름은 동일하게 S3 업로드 → DB 저장)
#     """
#     w, h = 1024, 1024
#     img = Image.new("RGBA", (w, h), (245, 245, 245, 255))
#     draw = ImageDraw.Draw(img)
#
#     # header bar
#     draw.rectangle((0, 0, w, 120), fill=(46, 125, 50, 255))
#     font = ImageFont.load_default()
#     title = "Food Ray Journal"
#     sub = f"by {nickname or 'User'}"
#     draw.text((24, 30), title, font=font, fill=(255, 255, 255, 255))
#     draw.text((24, 65), sub, font=font, fill=(230, 230, 230, 255))
#
#     # main placeholder box
#     draw.rounded_rectangle((40, 160, w - 40, 720), radius=16, outline=(210, 210, 210, 255), width=2)
#     draw.text((60, 180), "Image generation temporarily unavailable.", font=font, fill=(120, 120, 120, 255))
#
#     # bottom blank area for paragraph
#     draw.rounded_rectangle((40, 760, w - 40, 980), radius=16, outline=(210, 210, 210, 255), width=2)
#
#     buf = BytesIO()
#     img.save(buf, format="PNG")
#     return buf.getvalue()
#
#
# def _safe_json_load(s: str) -> Dict[str, Any]:
#     s = (s or "").strip()
#     try:
#         return json.loads(s)
#     except Exception:
#         a = s.find("{")
#         b = s.rfind("}")
#         if 0 <= a < b:
#             try:
#                 return json.loads(s[a : b + 1])
#             except Exception:
#                 pass
#         return {}
#
#
# def _compose_final(base_png: bytes, paragraph: str) -> bytes:
#     """
#     base_png 위에 하단 텍스트 박스 + 문단을 그려서 최종 PNG 반환
#     """
#     base = Image.open(BytesIO(base_png)).convert("RGBA")
#
#     W, H = base.size
#     bottom_h = int(H * 0.26)
#     pad = 36
#
#     draw = ImageDraw.Draw(base)
#
#     # bottom background (white-ish)
#     y0 = H - bottom_h
#     draw.rectangle((0, y0, W, H), fill=(255, 255, 255, 230))
#
#     # title line
#     draw.line((pad, y0 + 16, W - pad, y0 + 16), fill=(46, 125, 50, 255), width=3)
#
#     # paragraph
#     font = ImageFont.load_default()
#     wrapped = textwrap.fill(paragraph or "", width=54)
#     draw.text((pad, y0 + 34), wrapped, fill=(30, 30, 30, 255), font=font)
#
#     out = BytesIO()
#     base.save(out, format="PNG")
#     return out.getvalue()
#
#
# def run_journal_template(payload: Dict[str, Any]) -> bytes:
#     """
#     payload expected:
#     - member: { nickname, ... }
#     - reviews, allergy_tags, ...
#     """
#     member = payload.get("member") or {}
#     nickname = member.get("nickname") or "User"
#
#     # 1) character spec from analysis
#     analysis_prompt = build_character_analysis_prompt(payload)
#     analysis_raw = generate_text(analysis_prompt)
#     character_spec = _safe_json_load(analysis_raw)
#
#     # 2) copy paragraph
#     copy_prompt = build_character_copy_prompt(payload, character_spec)
#     paragraph = generate_text(copy_prompt).strip()
#
#     if not paragraph:
#         paragraph = f"{nickname} accidentally discovered a mukbang powered by today’s meals."
#
#     # 3) Image: character with blank bottom area
#     img_prompt = build_character_image_prompt(character_spec)
#     base_png = generate_image(img_prompt)
#     if not base_png:
#         # 외부 생성 실패(빈 bytes) -> 메모리 fallback 베이스로 진행
#         print("[run_journal_template] base image empty -> fallback base used")
#         base_png = _fallback_base_png_bytes(nickname)
#
#     # 4) Compose final
#     return _compose_final(base_png, paragraph)
#
# # from __future__ import annotations
# #
# # import io
# # import json
# # import textwrap
# # from io import BytesIO
# # from typing import Dict, Any
# #
# # from PIL import Image, ImageDraw, ImageFont
# #
# # from AI.journal_assistant.pipeline.generator import generate_text, generate_image
# # from AI.journal_assistant.pipeline.templates.journal_template.character_analysis import build_character_analysis_prompt
# # from AI.journal_assistant.pipeline.templates.journal_template.character_copy import build_character_copy_prompt
# # from AI.journal_assistant.pipeline.templates.journal_template.character_image_prompt import build_character_image_prompt
# #
# #
# # def _safe_json_load(s: str) -> Dict[str, Any]:
# #     s = (s or "").strip()
# #     try:
# #         return json.loads(s)
# #     except Exception:
# #         a = s.find("{")
# #         b = s.rfind("}")
# #         if a != -1 and b != -1 and b > a:
# #             return json.loads(s[a:b + 1])
# #         raise
# #
# #
# # def _wrap_text(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont, max_width: int) -> str:
# #     words = (text or "").split()
# #     lines = []
# #     cur = []
# #     for w in words:
# #         test = " ".join(cur + [w])
# #         if draw.textlength(test, font=font) <= max_width:
# #             cur.append(w)
# #         else:
# #             if cur:
# #                 lines.append(" ".join(cur))
# #             cur = [w]
# #     if cur:
# #         lines.append(" ".join(cur))
# #     return "\n".join(lines)
# #
# #
# # def _to_pil_rgba(base_png: object) -> Image.Image:
# #     """
# #     base_png가 어떤 형태로 오더라도(PNG bytes / bytearray / memoryview / BytesIO / PIL.Image)
# #     안전하게 PIL.Image(RGBA)로 변환한다.
# #     """
# #     # PIL.Image면 그대로
# #     if isinstance(base_png, Image.Image):
# #         return base_png.convert("RGBA")
# #
# #     # memoryview 지원(운영에서 간혹 이런 타입으로 올 수 있음)
# #     if isinstance(base_png, memoryview):
# #         base_png = base_png.tobytes()
# #
# #     # bytes/bytearray면 BytesIO로 열기
# #     if isinstance(base_png, (bytes, bytearray)):
# #         try:
# #             return Image.open(BytesIO(base_png)).convert("RGBA")
# #         except Exception as e:
# #             # PNG bytes가 깨졌거나, bytes가 이미지가 아닌 경우
# #             raise RuntimeError(f"Invalid image bytes for PIL open: {type(e).__name__}: {e}")
# #
# #     # BytesIO 같은 file-like 객체도 지원
# #     if hasattr(base_png, "read"):
# #         try:
# #             data = base_png.read()
# #             return Image.open(BytesIO(data)).convert("RGBA")
# #         except Exception as e:
# #             raise RuntimeError(f"Invalid file-like image input: {type(e).__name__}: {e}")
# #
# #     raise TypeError(f"base_png must be bytes/bytearray/memoryview/file-like or PIL.Image, got: {type(base_png)!r}")
# #
# #
# # def _compose_final(base_png, paragraph: str) -> bytes:
# #     # 1) bytes -> PIL Image (bytes.convert 에러 방지)
# #     if isinstance(base_png, memoryview):
# #         base_png = base_png.tobytes()
# #
# #     if isinstance(base_png, (bytes, bytearray)):
# #         img = Image.open(io.BytesIO(base_png)).convert("RGBA")
# #     elif isinstance(base_png, Image.Image):
# #         img = base_png.convert("RGBA")
# #     else:
# #         # file-like 지원
# #         if hasattr(base_png, "read"):
# #             data = base_png.read()
# #             img = Image.open(io.BytesIO(data)).convert("RGBA")
# #         else:
# #             raise TypeError(f"base_png type not supported: {type(base_png)}")
# #
# #     w, h = img.size
# #     draw = ImageDraw.Draw(img)
# #
# #     # 2) 폰트는 무조건 기본 폰트만 (truetype 전부 제거)
# #     font = ImageFont.load_default()
# #
# #     # 박스/레이아웃
# #     side_margin = int(w * 0.07)
# #     bottom_margin = int(h * 0.06)
# #     padding_x = 20
# #     padding_y = 14
# #     radius = 18
# #     spacing = 6
# #
# #     text_raw = (paragraph or "").strip()
# #     if not text_raw:
# #         text_raw = " "
# #
# #     # 3) 간단 wrap (기본 폰트는 측정이 애매해서 폭 기준으로 단순화)
# #     #    너무 길면 자동 줄바꿈되게만 처리
# #     max_text_width = w - (side_margin * 2) - (padding_x * 2)
# #
# #     words = text_raw.split()
# #     lines = []
# #     cur = ""
# #     for word in words:
# #         test = (cur + " " + word).strip()
# #         try:
# #             tw = draw.textlength(test, font=font)
# #         except Exception:
# #             # textlength가 없는 PIL 버전 대비
# #             tw = draw.textbbox((0, 0), test, font=font)[2]
# #
# #         if tw <= max_text_width or not cur:
# #             cur = test
# #         else:
# #             lines.append(cur)
# #             cur = word
# #     if cur:
# #         lines.append(cur)
# #
# #     text = "\n".join(lines)
# #
# #     # 4) 텍스트 bbox 계산 -> 텍스트 크기만큼 박스 생성
# #     bbox = draw.multiline_textbbox((0, 0), text, font=font, spacing=spacing, align="left")
# #     text_w = bbox[2] - bbox[0]
# #     text_h = bbox[3] - bbox[1]
# #
# #     box_w = min(w - side_margin * 2, text_w + padding_x * 2)
# #     box_h = text_h + padding_y * 2
# #
# #     box_x1 = (w - box_w) // 2
# #     box_y2 = h - bottom_margin
# #     box_y1 = box_y2 - box_h
# #     box_x2 = box_x1 + box_w
# #
# #     # 5) 박스 + 텍스트 렌더
# #     draw.rounded_rectangle(
# #         (box_x1, box_y1, box_x2, box_y2),
# #         radius=radius,
# #         fill=(255, 255, 255, 235),
# #     )
# #
# #     draw.multiline_text(
# #         (box_x1 + padding_x, box_y1 + padding_y),
# #         text,
# #         font=font,
# #         fill=(20, 20, 20, 255),
# #         spacing=spacing,
# #         align="left",
# #     )
# #
# #     # 6) PNG bytes로 반환
# #     out = io.BytesIO()
# #     img.save(out, format="PNG")
# #     return out.getvalue()
# #
# #
# # def run_journal_template(payload: Dict[str, Any]) -> bytes:
# #     member = payload.get("member") or {}
# #     nickname = member.get("nickname") or "The Traveler"
# #
# #     # Agent1: character spec JSON
# #     p1 = build_character_analysis_prompt(payload)
# #     character_json_text = generate_text(p1)
# #     if not character_json_text:
# #         raise RuntimeError("Agent1 returned empty text")
# #
# #     character_spec = _safe_json_load(character_json_text)
# #
# #     # Agent2: paragraph (또는 캐릭터 이름을 만들고 싶으면 여기 프롬프트를 이름 생성용으로 바꾸면 됨)
# #     p2 = build_character_copy_prompt(
# #         character_json=json.dumps(character_spec, ensure_ascii=False),
# #         nickname=nickname,
# #     )
# #     paragraph = generate_text(p2)
# #     if not paragraph:
# #         paragraph = f"{nickname} accidentally discovered a mukbang powered by today’s meals."
# #
# #     # Image: character with blank bottom area
# #     img_prompt = build_character_image_prompt(character_spec)
# #     base_png = generate_image(img_prompt)
# #     if not base_png:
# #         raise RuntimeError("Journal base image generation failed (empty bytes).")
# #
# #     # Compose final (여기서 bytes.convert 에러 방지 완료)
# #     return _compose_final(base_png, paragraph)
