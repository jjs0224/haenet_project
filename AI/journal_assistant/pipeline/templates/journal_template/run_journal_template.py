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


def _safe_json_load(s: str) -> Dict[str, Any]:
    s = (s or "").strip()
    try:
        return json.loads(s)
    except Exception:
        a = s.find("{")
        b = s.rfind("}")
        if a != -1 and b != -1 and b > a:
            return json.loads(s[a:b + 1])
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


def _to_pil_rgba(base_png: object) -> Image.Image:
    """
    base_png가 어떤 형태로 오더라도(PNG bytes / bytearray / memoryview / BytesIO / PIL.Image)
    안전하게 PIL.Image(RGBA)로 변환한다.
    """
    # PIL.Image면 그대로
    if isinstance(base_png, Image.Image):
        return base_png.convert("RGBA")

    # memoryview 지원(운영에서 간혹 이런 타입으로 올 수 있음)
    if isinstance(base_png, memoryview):
        base_png = base_png.tobytes()

    # bytes/bytearray면 BytesIO로 열기
    if isinstance(base_png, (bytes, bytearray)):
        try:
            return Image.open(BytesIO(base_png)).convert("RGBA")
        except Exception as e:
            # PNG bytes가 깨졌거나, bytes가 이미지가 아닌 경우
            raise RuntimeError(f"Invalid image bytes for PIL open: {type(e).__name__}: {e}")

    # BytesIO 같은 file-like 객체도 지원
    if hasattr(base_png, "read"):
        try:
            data = base_png.read()
            return Image.open(BytesIO(data)).convert("RGBA")
        except Exception as e:
            raise RuntimeError(f"Invalid file-like image input: {type(e).__name__}: {e}")

    raise TypeError(f"base_png must be bytes/bytearray/memoryview/file-like or PIL.Image, got: {type(base_png)!r}")


def _compose_final(base_png: object, paragraph: str) -> bytes:
    """
    base_png: PNG bytes 또는 PIL.Image
    paragraph: 하단 텍스트
    return: 최종 PNG bytes
    """

    # ✅ 여기서 무조건 PIL로 변환(이걸로 bytes.convert 에러 100% 제거)
    img = _to_pil_rgba(base_png)

    w, h = img.size
    draw = ImageDraw.Draw(img)

    # --- settings ---
    font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 32)
    side_margin = int(w * 0.07)
    bottom_margin = int(h * 0.06)
    padding_x = 32
    padding_y = 22
    radius = 22

    # wrap
    lines = textwrap.wrap((paragraph or "").strip(), width=28)
    text = "\n".join(lines) if lines else (paragraph or "").strip()

    bbox = draw.multiline_textbbox((0, 0), text, font=font, spacing=8, align="left")
    text_w = bbox[2] - bbox[0]
    text_h = bbox[3] - bbox[1]

    box_w = min(w - side_margin * 2, text_w + padding_x * 2)
    box_h = text_h + padding_y * 2

    box_x1 = (w - box_w) // 2
    box_y2 = h - bottom_margin
    box_y1 = box_y2 - box_h
    box_x2 = box_x1 + box_w

    draw.rounded_rectangle(
        (box_x1, box_y1, box_x2, box_y2),
        radius=radius,
        fill=(255, 255, 255, 235),
    )

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

    out = BytesIO()
    img.save(out, format="PNG")
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

    # Agent2: paragraph (또는 캐릭터 이름을 만들고 싶으면 여기 프롬프트를 이름 생성용으로 바꾸면 됨)
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

    # Compose final (여기서 bytes.convert 에러 방지 완료)
    return _compose_final(base_png, paragraph)
