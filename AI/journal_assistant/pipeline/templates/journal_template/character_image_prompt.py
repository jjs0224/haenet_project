from __future__ import annotations
from typing import Dict, Any

def build_character_image_prompt(character_spec: Dict[str, Any]) -> str:
    gender = character_spec.get("gender_expression", "neutral")
    core_vibe = character_spec.get("core_vibe", "food lover")
    dominant_emotion = character_spec.get("dominant_emotion", "calm")
    facial_expression = character_spec.get("facial_expression", "natural expression")
    outfit_style = character_spec.get("outfit_style", "modern casual outfit")
    palette = ", ".join((character_spec.get("color_palette") or [])[:6])

    # IMPORTANT: use MANY foods, not 3~6
    foods = (character_spec.get("food_props") or character_spec.get("props") or [])
    foods = [f for f in foods if isinstance(f, str) and f.strip()]
    foods = foods[:20]  # 안전 상한
    food_list = ", ".join(foods) if foods else "Korean meals and drinks mentioned in menus"

    # optional context
    country = character_spec.get("country_vibe", "United States")

    return f"""
Create a highly detailed creature design.

This is NOT a human.
This is NOT a person wearing food.
This is NOT a character holding dishes.

This is ONE single unified food entity — a living character
made entirely from the fusion of the foods it consumed.

CONCEPT:
If someone ate these foods, and the foods merged into one being,
this is the result.

The character must look like ONE character
Not separate dishes.
Not a collage.
Not floating items.
Everything must be physically merged.

FOODS TO FUSE (must all influence the design):
{food_list}


The character should:

- Have layered textures.
- Have glossy + matte contrast.
- Feel edible but alive.
- just by looking at it, others should know what it ate

STYLE:
Hyper-detailed.
Semi-realistic.
Cinematic lighting.
Dark studio background.
High contrast.
Not cartoon.
Not cute mascot.
Not Pixar.
Not anime.

MOOD:
Strangely majestic.
Slightly chaotic.
Powerful but funny.

ABSOLUTE NEGATIVES:
- No humans.
- No table.
- No restaurant scene.
- No floating separate dishes.
- No brand logos.
- No readable text.

The viewer should immediately understand:
“This creature is made from {food_list}



FOOD INTEGRATION (MOST IMPORTANT):
You MUST include ALL foods listed below, not just a few.
Foods to include (do not omit any): {food_list}


Return image only.
""".strip()
