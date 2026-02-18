from __future__ import annotations
import json
from io import BytesIO
from typing import Dict, Any

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


def _compose_final(base_png: bytes, paragraph: str) -> bytes:
    """
    base_png: Gemini가 만든 이미지 (하단 30% 비어있는 상태가 이상적)
    paragraph: 밑에 그릴 텍스트
    """
    base = Image.open(BytesIO(base_png)).convert("RGBA")
    w, h = base.size

    draw = ImageDraw.Draw(base)

    # 폰트 (윈도우면 arial.ttf 잘 잡힘 / 서버면 fallback)
    try:
        font = ImageFont.truetype("arial.ttf", 36)
    except Exception:
        font = ImageFont.load_default()

    # 하단 텍스트 영역
    left = int(w * 0.08)
    right = int(w * 0.92)
    top = int(h * 0.72)       # 하단 28% 정도
    max_width = right - left

    wrapped = _wrap_text(draw, paragraph.strip(), font, max_width)

    # 텍스트 배경 카드(가독성)
    pad = 18
    card = (left - pad, top - pad, right + pad, h - int(h * 0.06))
    draw.rounded_rectangle(card, radius=24, fill=(245, 245, 245, 235), outline=(220, 220, 220, 255), width=2)

    draw.multiline_text(
        (left, top),
        wrapped,
        fill=(20, 20, 20, 255),
        font=font,
        spacing=10,
        align="left",
    )

    out = BytesIO()
    base.save(out, format="PNG")
    return out.getvalue()


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
