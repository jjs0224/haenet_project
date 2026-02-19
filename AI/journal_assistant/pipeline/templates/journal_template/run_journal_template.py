from __future__ import annotations
import json
from io import BytesIO
from typing import Dict, Any
import textwrap
from PIL import Image, ImageDraw, ImageFont

from AI.journal_assistant.pipeline.generator import generate_text, generate_image
from AI.journal_assistant.pipeline.templates.journal_template.character_analysis import build_character_analysis_prompt
from AI.journal_assistant.pipeline.templates.journal_template.character_copy import build_character_copy_prompt
from AI.journal_assistant.pipeline.templates.journal_template.character_image_prompt import build_character_image_prompt


def _safe_json_load(s: str) -> Dict[str, Any]:
    s = (s or "").strip()
    try:
        return json.loads(s)
    except Exception:
        a = s.find("{")
        b = s.rfind("}")
        if a != -1 and b != -1 and b > a:
            return json.loads(s[a:b+1])
        raise


def _wrap_text(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont, max_width: int) -> str:
    words = (text or "").split()
    lines = []
    cur = []
    for w in words:
        test = " ".join(cur + [w])
        if draw.textlength(test, font=font) <= max_width:
            cur.append(w)
        else:
            if cur:
                lines.append(" ".join(cur))
            cur = [w]
    if cur:
        lines.append(" ".join(cur))
    return "\n".join(lines)


def _compose_final(base_png: Image.Image, paragraph: str) -> Image.Image:
    img = base_png.convert("RGBA")
    w, h = img.size
    draw = ImageDraw.Draw(img)

    # --- settings (원래 쓰던 값 있으면 그걸로 교체) ---
    font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 32)
    side_margin = int(w * 0.07)
    bottom_margin = int(h * 0.06)
    padding_x = 32
    padding_y = 22
    radius = 22

    # 1) wrap: 박스 폭 안에 들어갈 줄바꿈 만들기
    max_text_width = w - (side_margin * 2) - (padding_x * 2)

    # 대충 문자 개수로 자르는 게 아니라, textbbox 기반으로 줄바꿈하는 게 베스트지만
    # 최소 수정이면 textwrap + bbox로 후검증 방식이 현실적.
    # (네 코드가 이미 wrap을 하고 있으면 그 로직 유지)
    lines = textwrap.wrap(paragraph.strip(), width=28)  # <= 너비 값은 폰트/이미지에 맞게 조절
    text = "\n".join(lines) if lines else paragraph.strip()

    # 2) 텍스트 bbox 계산 (높이/폭 정확히 구하기)
    # PIL 버전 따라 multiline_textbbox가 없을 수 있어 textbbox로 대체 가능
    bbox = draw.multiline_textbbox((0, 0), text, font=font, spacing=8, align="left")
    text_w = bbox[2] - bbox[0]
    text_h = bbox[3] - bbox[1]

    # 3) 박스 크기 = 텍스트 크기 + padding
    box_w = min(w - side_margin * 2, text_w + padding_x * 2)
    box_h = text_h + padding_y * 2

    # 4) 박스 위치: 하단에 딱 붙이되 마진 유지
    box_x1 = (w - box_w) // 2
    box_y2 = h - bottom_margin
    box_y1 = box_y2 - box_h
    box_x2 = box_x1 + box_w

    # 5) 박스 그리기 (rounded)
    draw.rounded_rectangle(
        (box_x1, box_y1, box_x2, box_y2),
        radius=radius,
        fill=(255, 255, 255, 235),
    )

    # 6) 텍스트 그리기
    text_x = box_x1 + padding_x
    text_y = box_y1 + padding_y
    draw.multiline_text(
        (text_x, text_y),
        text,
        font=font,
        fill=(20, 20, 20, 255),
        spacing=8,
        align="left",
    )

    return img


# def _compose_final(base_png: bytes, paragraph: str) -> bytes:
#     """
#     base_png: Gemini가 만든 이미지 (하단 30% 비어있는 상태가 이상적)
#     paragraph: 밑에 그릴 텍스트
#     """
#     base = Image.open(BytesIO(base_png)).convert("RGBA")
#     w, h = base.size
#
#     draw = ImageDraw.Draw(base)
#
#     # 폰트 (윈도우면 arial.ttf 잘 잡힘 / 서버면 fallback)
#     try:
#         font = ImageFont.truetype("arial.ttf", 36)
#     except Exception:
#         font = ImageFont.load_default()
#
#     # 하단 텍스트 영역
#     left = int(w * 0.08)
#     right = int(w * 0.92)
#     top = int(h * 0.72)       # 하단 28% 정도
#     max_width = right - left
#
#     wrapped = _wrap_text(draw, paragraph.strip(), font, max_width)
#
#     # 텍스트 배경 카드(가독성)
#     pad = 18
#     card = (left - pad, top - pad, right + pad, h - int(h * 0.06))
#     draw.rounded_rectangle(card, radius=24, fill=(245, 245, 245, 235), outline=(220, 220, 220, 255), width=2)
#
#     draw.multiline_text(
#         (left, top),
#         wrapped,
#         fill=(20, 20, 20, 255),
#         font=font,
#         spacing=10,
#         align="left",
#     )
#
#     out = BytesIO()
#     base.save(out, format="PNG")
#     return out.getvalue()


def run_journal_template(payload: Dict[str, Any]) -> bytes:
    member = payload.get("member") or {}
    nickname = member.get("nickname") or "The Traveler"

    # Agent1: character spec JSON
    p1 = build_character_analysis_prompt(payload)
    character_json_text = generate_text(p1)
    if not character_json_text:
        raise RuntimeError("Agent1 returned empty text")

    character_spec = _safe_json_load(character_json_text)

    # Agent2: paragraph
    p2 = build_character_copy_prompt(
        character_json=json.dumps(character_spec, ensure_ascii=False),
        nickname=nickname,
    )
    paragraph = generate_text(p2)
    if not paragraph:
        paragraph = f"{nickname} accidentally discovered a mukbang monster powered by today’s meals."

    # Image: character with blank bottom area
    img_prompt = build_character_image_prompt(character_spec)
    base_png = generate_image(img_prompt)
    if not base_png:
        raise RuntimeError("Journal base image generation failed (empty bytes).")

    # Compose final
    return _compose_final(base_png, paragraph)
