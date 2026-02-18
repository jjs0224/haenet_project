from __future__ import annotations


def build_character_copy_prompt(*, character_json: str, nickname: str) -> str:
    nickname = nickname or "The Traveler"
    return f"""
You are Agent 2: Character Copywriter.

Write 2–3 short sentences (max 60 words).

Tone:
- Confident
- Slightly playful
- MBTI personality card style

Mention:
- Nickname
- Dominant food pattern (spicy, sweet, meat, etc.)
- One food reference naturally (e.g., Jinro, pork ribs)

Do NOT:
- Overexplain
- Be dramatic
- Write more than 60 words
- Use emojis

""".strip()
