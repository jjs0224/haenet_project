from __future__ import annotations

def build_character_copy_prompt(*, character_json: str, nickname: str) -> str:
    nickname = nickname or "The Traveler"
    return f"""
You are Agent 2: Character Name Creator.

Input (JSON):
{character_json}

Goal: Create a character name that matches the generated character image vibe and the food personality.

Rules:
- Output ONLY the character name (no quotes, no extra text).
- 2–5 words max.
- English only.
- Confident, slightly playful, MBTI personality card vibe.
- Must include or clearly reflect nickname: {nickname}
- Must reflect dominant food pattern (spicy/sweet/meat/etc.) from the JSON
- Include ONE natural food reference (e.g., Jinro, pork ribs)

Do NOT:
- Explain anything
- Add emojis
- Output more than 5 words
""".strip()



# def build_character_copy_prompt(*, character_json: str, nickname: str) -> str:
#     nickname = nickname or "The Traveler"
#     return f"""
# You are Agent 2: Character Copywriter.
#
# Write 2–3 short sentences (max 60 words).
#
# Tone:
# - Confident
# - Slightly playful
# - MBTI personality card style
#
# Mention:
# - Nickname
# - Dominant food pattern (spicy, sweet, meat, etc.)
# - One food reference naturally (e.g., Jinro, pork ribs)
#
# Do NOT:
# - Overexplain
# - Be dramatic
# - Write more than 60 words
# - Use emojis
#
# """.strip()

# from __future__ import annotations
#
# def build_character_copy_prompt(*, character_json: str, nickname: str) -> str:
#     nickname = nickname or "The Traveler"
#     return f"""
# You are Agent 2: Character Name Creator.
#
# Input (JSON):
# {character_json}
#
# Goal: Create a character name that matches the generated character image vibe and the food personality.
#
# Rules:
# - Output ONLY the character name (no quotes, no extra text).
# - 2–5 words max.
# - English only.
# - Confident, slightly playful, MBTI personality card vibe.
# - Must include or clearly reflect nickname: {nickname}
# - Must reflect dominant food pattern (spicy/sweet/meat/etc.) from the JSON
# - Include ONE natural food reference (e.g., Jinro, pork ribs)
#
# Do NOT:
# - Explain anything
# - Add emojis
# - Output more than 5 words
# """.strip()
#
#
#
# # def build_character_copy_prompt(*, character_json: str, nickname: str) -> str:
# #     nickname = nickname or "The Traveler"
# #     return f"""
# # You are Agent 2: Character Copywriter.
# #
# # Write 2–3 short sentences (max 60 words).
# #
# # Tone:
# # - Confident
# # - Slightly playful
# # - MBTI personality card style
# #
# # Mention:
# # - Nickname
# # - Dominant food pattern (spicy, sweet, meat, etc.)
# # - One food reference naturally (e.g., Jinro, pork ribs)
# #
# # Do NOT:
# # - Overexplain
# # - Be dramatic
# # - Write more than 60 words
# # - Use emojis
# #
# # """.strip()
