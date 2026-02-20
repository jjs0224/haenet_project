from __future__ import annotations
from typing import Any, Dict, List
import json

def extract_menu_names_from_reviews(reviews: List[Dict[str, Any]]) -> List[str]:
    out: List[str] = []

    for r in reviews:
        raw = r.get("menu_name")  # ex: ['["A","B"]'] OR [] OR ['Fig Sandwich']
        if not raw:
            continue

        # your shape: list[str]
        if isinstance(raw, list):
            for s in raw:
                if not isinstance(s, str):
                    continue
                s = s.strip()
                if not s:
                    continue

                # if JSON list string
                if s.startswith("["):
                    try:
                        parsed = json.loads(s)
                        if isinstance(parsed, list):
                            out.extend([str(x).strip() for x in parsed if str(x).strip()])
                            continue
                    except Exception:
                        pass

                # fallback plain string
                out.append(s)

        elif isinstance(raw, str):
            s = raw.strip()
            if s.startswith("["):
                try:
                    parsed = json.loads(s)
                    if isinstance(parsed, list):
                        out.extend([str(x).strip() for x in parsed if str(x).strip()])
                        continue
                except Exception:
                    pass
            if s:
                out.append(s)

    # de-dupe keep order
    seen = set()
    out = [x for x in out if not (x in seen or seen.add(x))]
    return out

def build_map_poster_prompt_with_ref(
    payload: Dict[str, Any],
    *,
    canvas_w: int,
    canvas_h: int,
    map_left: int,
    map_top: int,
    map_w: int,
    map_h: int,
) -> str:
    member = payload.get("member", {})
    reviews: List[Dict[str, Any]] = payload.get("reviews", [])

    nickname = member.get("nickname", "Traveler")
    country = member.get("country", "Unknown")
    allergies = payload.get("allergy_tags", {})
    # allergies = allergy_tags.get("item_ids", [])

    print("allergies :: ", allergies)

    allergy_text = ", ".join(allergies) if allergies else "none"

    # print("allergies :: ", allergies)

    menus = extract_menu_names_from_reviews(reviews)

    print("\n=== PAYLOAD DEBUG (MAP PROMPT) ===")
    print("reviews count:", len(reviews))
    print("first review keys:", list(reviews[0].keys()) if reviews else None)

    for i, r in enumerate(reviews[:5]):  # print only first 5
        print(f"\nreview[{i}].review_id:", r.get("review_id"))
        print(f"review[{i}].menu_name RAW:", r.get("menu_name"))
        print(f"review[{i}].review_items:", r.get("review_items"))

    print("\nmenus extracted:", menus)
    print("menus extracted count:", len(menus))
    print("==================================\n")

    menu_text = ", ".join(menus) if menus else "No menus recorded"

    map_box = f"x={map_left}..{map_left+map_w}, y={map_top}..{map_top+map_h}"

    #음식 이미지 사진 사이즈 고정시키기
    max_food_w = int(canvas_w * 0.06)   # 캔버스 가로의 12%
    max_food_h = int(canvas_h * 0.08)   # 캔버스 세로의 18% (원형/접시 고려)
    
    return f"""
CRITICAL:
You are EDITING the provided REFERENCE IMAGE.
The reference image already contains the map and location pins.

CANVAS:
- Output size MUST be exactly {canvas_w}x{canvas_h}.
- Do NOT crop, resize, or change aspect ratio.

LOCKED AREA (MAP AREA):
- The map rectangle is {map_box}.
- DO NOT modify ANY pixels inside the map rectangle.
- Do NOT add text, stickers, tape, shadows, texture, or food images inside that map rectangle.
- The map and pins must remain pixel-identical.
- DO NOT SHRINK MAP SIZE !!! 


ALLOWED AREA (OUTSIDE MAP ONLY):
- Add a big title centered at top: "K-FOOD roadmap with Food Ray"
- big title must be handwritten-style Korean text
- Subtitle: "By {nickname} from {country}"
- Add scrapbook accents around the outer background only (tape, stamps, doodles)

USER CONTEXT:
- The user ate these menu items (IMPORTANT: use THESE for food cutout images):
  {menu_text}
  
FOOD CUTOUTS (VERY IMPORTANT SIZE RULE):
- Food images must be SMALL sticker-like cutouts (secondary accents).
- Each food cutout must be no larger than {max_food_w}px wide AND {max_food_h}px tall.
- Each cutout should occupy at most 6% of the canvas width.
- Food cutouts must be clearly smaller than the map.
- If any food cutout looks big/dominant, the result is incorrect.
- Create food sticker cutout images that match the user's eaten menu items above.
- If there are many menu items, choose a RANDOM subset (no repeats).
- Do NOT invent foods that are not in the user's menu list.
- ONLY use menu image ONCE!!!!! 
- if similar menu name then only use one 
--> eg. dumpling, pork dumpling, cheese dumpling ==> use 1 image of dumpling!! 
- only use 1 image of alcohol type 
--> eg terra, cass, hite, ==> all beer so just 1 image of beer NOT 1 image of cass, 1 image of terra, etc


PLACEMENT:
- Place JUST food image of eaten food cutouts RANDOMLY (not straight line but spread them out quite evenly throughout out side of  map) OUTSIDE the map area
- Keep consistent spacing; do not overlap elements.
- DO NOT include name of food menu. JUST IMAGE


STYLE:
- Minimal clean poster + light hanji texture (ONLY outside map area)
- English only
- No restaurant names, addresses, dates, social handles


FOOD IMAGE SIZE (IMPORTANT):
- Each food cutout must be small and sticker-like.
- MAX 6 food image
- Max size per food image:
  - Width ≤ 6% of canvas width
  - Height ≤ 8% of canvas height
- Food images must NOT dominate the box.
- Text must remain clearly readable next to or below each image.


OUTPUT:
Return ONE edited image.
""".strip()
