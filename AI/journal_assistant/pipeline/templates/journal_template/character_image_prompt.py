from __future__ import annotations
from typing import Dict, Any

def build_character_image_prompt(character_spec: Dict[str, Any]) -> str:
    foods = (character_spec.get("food_props") or character_spec.get("props") or [])
    foods = [f for f in foods if isinstance(f, str) and f.strip()]
    foods = foods[:25]
    food_list = ", ".join(foods) if foods else "Korean meals and drinks"

    animal_type = character_spec.get("animal_type", "cat")  # cat/dog/rabbit/pig only

    return f"""
SINGLE SUBJECT ONLY: a normal cute {animal_type} pet (REAL animal anatomy).

HARD ANATOMY LOCK (MOST IMPORTANT):a
- Must be a {animal_type} on FOUR LEGS (quadruped).
- Must have a normal {animal_type} head + snout + ears + tail.
- Must look like a PET animal photo, not a “character” body.
- 70%+ of the body must be visible FUR (not food texture).

ABSOLUTE BAN LIST (CRITICAL):
- NO human
- NO humanoid
- NO biped / standing upright
- NO muscular body, NO abs, NO chest, NO arms/hands
- NO monster, NO demon, NO scary face, NO sharp teeth grin
- NO “food person”, NO “food golem”, NO “food armor”, NO “made of food”
- NO replacing skin/fur with noodles/bread/meat textures

FOOD RULE (SECOND MOST IMPORTANT):
Food must be ONLY:
A) small accessories ON TOP of the animal (collar charm, tiny hat topper, ribbon, scarf pattern), AND/OR
B) food being eaten (one small bite near mouth), AND/OR
C) food arranged AROUND the animal on the ground.

Foods must NEVER become anatomy:
- not body, not limbs, not face, not skin, not muscles.

MUST INCLUDE ALL FOODS (do not omit any):
{food_list}

How to include ALL foods safely:
- 1 food = the bite near mouth
- 3–6 foods = tiny accessories (charms/pins/ribbon/hat topper)
- all remaining foods = neatly arranged around the animal on the ground (no floating)

STYLE:
- Cute high-quality 3D render of a real pet animal
- Soft studio lighting, clean gradient background
- Big eyes, adorable proportions
- Centered subject, full body visible

COMPOSITION FOR CAPTION:
- Leave bottom 25–30% EMPTY clean space (no objects, no text).

STRICT NEGATIVES (repeat):
no human, no humanoid, no biped, no muscles, no abs, no monster, no demon,
no scary grin, no sharp teeth, no food-bodied character, no food skin, no food armor,
no noodles-as-limbs, no bread torso, no meat muscles, no floating food, no text, no logos.

Return image only.
""".strip()

# from __future__ import annotations
# from typing import Dict, Any
#
# def build_character_image_prompt(character_spec: Dict[str, Any]) -> str:
#     gender = character_spec.get("gender_expression", "neutral")
#     core_vibe = character_spec.get("core_vibe", "food lover")
#     dominant_emotion = character_spec.get("dominant_emotion", "calm")
#     facial_expression = character_spec.get("facial_expression", "natural expression")
#     outfit_style = character_spec.get("outfit_style", "modern casual outfit")
#     palette = ", ".join((character_spec.get("color_palette") or [])[:6])
#
#     # IMPORTANT: use MANY foods, not 3~6
#     foods = (character_spec.get("food_props") or character_spec.get("props") or [])
#     foods = [f for f in foods if isinstance(f, str) and f.strip()]
#     foods = foods[:20]  # 안전 상한
#     food_list = ", ".join(foods) if foods else "Korean meals and drinks mentioned in menus"
#
#     # optional context
#     country = character_spec.get("country_vibe", "United States")
#
#     return f"""
# Create a highly detailed creature design.
#
# This is NOT a human.
# This is NOT a person wearing food.
# This is NOT a character holding dishes.
#
# This is ONE single unified food entity — a living character
# made entirely from the fusion of the foods it consumed.
#
# CONCEPT:
# If someone ate these foods, and the foods merged into one being,
# this is the result.
#
# The character must look like ONE character
# Not separate dishes.
# Not a collage.
# Not floating items.
# Everything must be physically merged.
#
# FOODS TO FUSE (must all influence the design):
# {food_list}
#
#
# The character should:
#
# - Have layered textures.
# - Have glossy + matte contrast.
# - Feel edible but alive.
# - just by looking at it, others should know what it ate
#
# STYLE:
# Hyper-detailed.
# Semi-realistic.
# Cinematic lighting.
# Dark studio background.
# High contrast.
# Not cartoon.
# Not cute mascot.
# Not Pixar.
# Not anime.
#
# MOOD:
# Strangely majestic.
# Slightly chaotic.
# Powerful but funny.
#
# ABSOLUTE NEGATIVES:
# - No humans.
# - No table.
# - No restaurant scene.
# - No floating separate dishes.
# - No brand logos.
# - No readable text.
#
# The viewer should immediately understand:
# “This creature is made from {food_list}
#
#
#
# FOOD INTEGRATION (MOST IMPORTANT):
# You MUST include ALL foods listed below, not just a few.
# Foods to include (do not omit any): {food_list}
#
#
# Return image only.
# """.strip()
