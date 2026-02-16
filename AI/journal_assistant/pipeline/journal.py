# ai/journal/food_journal_prompt.py
import json
from io import BytesIO
from PIL import Image
from typing import Any, Dict, List
from google import genai
from google.genai import types
import os
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.getenv("GEMINI_API_KEY")

client = genai.Client(
    api_key=API_KEY
)
def journal_prompt(payload: Dict[str, Any]) -> str:
    member = payload["member"]
    reviews: List[Dict[str, Any]] = payload["reviews"]

    review = reviews[0]

    return f"""
You are creating a SINGLE food journal page
in a FUNNY “mock academic paper / newspaper” style,
like a parody research poster (e.g. “Journal of Daily Studies”).

CORE KOREAN CULTURAL ISSUE:
“MUKBANG CULTURE” — extreme eating as entertainment in Korea.

IMPORTANT:
- Do NOT name real mukbang creators or real IPs.
- Treat “mukbang star” as a cultural archetype.
- This must clearly feel like a phenomenon unique to Korea.

FOCUS:
- ONE Korean dish only
- A foreign traveler accidentally becomes a “mukbang subject”
- Academic tone + visual absurdity

USER CONTEXT (do NOT invent facts):
- nickname: {member.get("nickname")}
- gender: {member.get("gender")}
- country: {member.get("country")}
- dietary rules / allergies: {member.get("item_ids")}

FOOD UNDER INVESTIGATION:
Title: {review["review_title"]}
Description: {review["review_content"]}

CONCEPT:
This page documents how a traveler in Korea
unknowingly participates in Korea’s mukbang culture
by consuming an extreme or visually satisfying Korean meal.

The subject is framed as:
- A temporary mukbang performer
- A field researcher AND the experiment itself
- Overwhelmed by portion size, rice refills, and side dishes

ACADEMIC STRUCTURE (visible text):
1) MAIN TITLE (large, dramatic):
   Example style:
   “A FIELD STUDY ON ACCIDENTAL PARTICIPATION
    IN KOREAN MUKBANG CULTURE”

2) Subtitle:
   “Observations of Excess Consumption by a Foreign Subject”

3) Author line:
   “By Visiting Researcher, Temporarily Assigned to Mukbang”

4) Sections:
   - Abstract
   - 1. Introduction: Encounter with Mukbang Culture
   - 2. Escalation of Consumption
   - 3. Physical and Psychological Aftereffects
   - only use image to explain 
   

IMAGE REQUIREMENTS (VERY IMPORTANT):
- Use REAL-LIFE PHOTOGRAPHY for food
- create 6 total images (2 for each abstract)

HUMOR VISUAL:
- ONE exaggerated but symbolic image:

CAPTIONS (deadpan, academic, 5–8 words):
Examples:


VISUAL STYLE:
- Landscape (16:9 or 3:2)
- One complete page
- Newspaper / academic journal layout
- Cream / hanji paper texture
- Serif typography
- Thin divider lines
- Looks like a printed journal page

TOP HEADER:
- Masthead: “Journal of SafeEat”
- Metadata: “Korea Field Edition • Mukbang Culture Report”
- Classic newspaper divider lines

DO NOT:
- Name real mukbang creators
- Mention social media platforms explicitly
- Mention ratings or restaurants
- Invent dates or places
- Sound promotional

FINAL FEEL:
“I came to Korea as a traveler.
I am becoming like Korean local 
I left the restaurant as a mukbang participant.”

# OUTPUT:
# - Generate ONE complete image
"""


def culture_journal(payload: Dict[str, Any]) -> str:
    template = payload.get("template", {})
    member = payload.get("member", {})
    reviews = payload.get("reviews", [])

    # Foods you specified (do not invent other menus)
    foods = ["육전", "떡볶이", "볶음밥"]

    # Allergy tags: use member.item_ids if present, otherwise fallback if you pass tags separately
    allergy_info = member.get("item_ids")

    return f"""
ADD REAL-LIFE HUMAN MOMENT (FUNNY BUT TASTELESS-FREE):

Include REAL-LIFE PHOTOGRAPHY style images showing
a traveler actively EATING the featured Korean foods.

IMPORTANT SAFETY & STYLE RULES:
- The eater must be anonymous:
  - face partially cropped, hidden, or turned away
  - or shown only as hands, mouth, torso, or silhouette
- Do NOT invent a specific person identity
- The eater represents “the user” symbolically

HUMAN EATING SHOTS (add 3 images total, integrated into collage):
1) 육전 eating moment:
   - chopsticks lifting meat
   - mid-bite moment
   - caption suggests seriousness vs reality

2) 떡볶이 eating moment:
   - messy sauce, stretching rice cake
   - hand hesitating, spice implied
   - funny contrast with academic tone

3) 볶음밥 eating moment:
   - spoon digging into bowl
   - visibly satisfied posture
   - emptying plate implied

COMEDY STYLE (VERY IMPORTANT):
- Humor comes from:
  - overly academic captions describing very human behavior
  - serious tone applied to silly moments
- NO cartoon slapstick
- NO exaggerated faces
- NO pigs, no mukbang imagery

EXAMPLE CAPTIONS (pick 3–4, 5–8 words each):
- “Subject initiates direct manual engagement”
- “Sauce contamination exceeds predicted levels”
- “Chopstick precision degrades over time”
- “Unexpected emotional attachment observed”
- “Subject ignores prior fullness indicators”
- “Final bites executed without hesitation”

LAYOUT INSTRUCTION:
- Interleave food plates and eating moments:
  - Food photo → eating photo → heritage image
- Eating photos should feel like candid travel snapshots
- Slightly tilted like scrapbook photos
- Tape corners / postcard pins / handwritten-style labels encouraged

FINAL COMEDY GOAL:
Viewer reaction should be:
“Why does this look like a museum exhibit
about me eating Korean food… and why is it accurate?”

"""

def generate_journal(journal_prompt):

    response = client.models.generate_content(
        model="gemini-2.5-flash-image",
        contents=journal_prompt,
        config=types.GenerateContentConfig(
            response_modalities=["IMAGE"]
        )
    )

    # 1. 응답에 후보(candidates)가 있고, 내용(content)이 있는지 먼저 확인
    if not response.candidates or not response.candidates[0].content:
        # 안전 필터 등으로 인해 차단된 경우
        print("경고: 모델이 이미지를 생성하지 못했습니다. (안전 필터 혹은 정책 위반 가능성)")

        # 차단 이유 확인 (디버깅용)
        if response.candidates and response.candidates[0].finish_reason:
            print(f"중단 이유: {response.candidates[0].finish_reason}")

        return None  # 에러 대신 None을 반환하여 프로그램이 멈추지 않게 함

    # 2. 내용이 있을 때만 parts에 접근
    for part in response.candidates[0].content.parts:
        if part.inline_data:
            return part.inline_data.data


    return None

def korea_trip_map_journal(payload: Dict[str, Any]) -> str:
    template = payload.get("template", {})
    member = payload.get("member", {})
    reviews: List[Dict[str, Any]] = payload.get("reviews", [])

    # If you later want to derive cities/foods from reviews, you can parse here.
    # For now, user explicitly requested: Seoul -> Busan -> Seoul, foods: kimchi-jjigae, tteokbokki, gukbap
    route_cities = ["서울", "부산", "서울"]
    foods = ["김치찌개", "떡볶이", "국밥"]
    allergies = ["egg", "peanut"]

    language = template.get("language", "en")

    return f"""
Generate ONE complete LANDSCAPE image (16:9 or 3:2), high resolution.
Style: Traditional Korean travel scrapbook + clean infographic map poster.

GOAL:
Create a single-page “Korea trip map journal” showing where the user visited and what they ate:
Route: {route_cities[0]} → {route_cities[1]} → {route_cities[2]}
Foods: {foods[0]}, {foods[1]}, {foods[2]}
Allergy icons: {", ".join(allergies)}

USER (use but do not invent new facts):
- nickname: {member.get("nickname")}
- gender: {member.get("gender")}
- country: {member.get("country")}
- dislike_tags: {member.get("dislike_tags")}
- item_ids (diet rules): {member.get("item_ids")}

MAP REQUIREMENTS (visual-first):
1) A stylized map of South Korea as the base (not an accurate GIS map; a clean illustrated silhouette is OK).
2) Place 2 main city markers:
   - 서울 (top/central-north)
   - 부산 (southeast)
3) Draw a route line with arrows: 서울 → 부산 → 서울
4) For each city marker, include a small “photo cutout” of what the user ate there:
   - Near 서울 marker: 김치찌개 (steaming red stew, tofu, scallions)
   - Near 부산 marker: 국밥 (hot soup bowl, rice, green onion)
   - On the route (or a third mini panel): 떡볶이 (spicy red sauce, rice cakes, fish cake)
   Use realistic food photo-collage look (cutout + shadow), NOT cartoon-only.

ALERGY VISUALIZATION:
- Add a small “Allergy Alert” badge area with two simple icons:
  - egg icon (crossed out)
  - peanut icon (crossed out)
- Keep it friendly, like a travel safety sticker.

TRADITIONAL KOREAN THEME (important):
- Background looks like hanji paper texture.
- Decorative accents inspired by:
  - dancheong patterns (subtle borders)
  - minhwa-style motifs (e.g., tiger/magpie vibe) BUT generic, not copyrighted characters
  - red seal stamp 느낌 (ink stamp title or corner stamp)
- Palette should feel like traditional Korea (warm paper + muted ink + tasteful red/blue/green accents).
- include some korean tradition image that depicts where they went eg if busan, something that depicts busan.. 

LAYOUT:
- Looks like a magazine / travel journal poster:
  - Big title at top: “KOREA FOOD TRIP MAP” (or bilingual: “KOREA FOOD TRIP MAP / 한국 맛여행 지도”)
  - Short subheader line: “서울 → 부산 → 서울”
  - Map takes ~60% of the canvas (center)
  - 3 small caption blocks (1–2 lines each), very short and fun (not long paragraphs)
  - A small “sticker row” for allergies + tiny icons (e.g., chopsticks, subway card, hanbok ribbon) as decorative.

TEXT RULES:
- Keep text minimal and punchy. No long narration.
- KEEP EVERYTHING IN ENGLISH
- DO NOT USE KOREAN AT ANY TIMES
- Do NOT mention restaurant ratings.
- Do NOT quote review text.
- Do NOT invent exact restaurant names, districts, dates, or times.
- Avoid real IP names.

FINAL FEELING:
A keep-forever travel poster:
“I tracked my Korea trip as a map, and each stop became a food memory.”
"""

if __name__ == "__main__":
    with open("mock_request.json", "r", encoding="utf-8") as f:
        data = json.load(f)


    # prompt = journal_prompt(data)
    culture_prompt = culture_journal(data)
    # map_prompt = korea_trip_map_journal(data)
    image_bytes = generate_journal(culture_prompt)
    # image_bytes = generate_journal(map_prompt)
    if image_bytes is None:
        print("이미지 생성 실패")
        raise SystemExit(1)

    # ✅ PNG로 저장
    img = Image.open(BytesIO(image_bytes))
    out_path = "food_journal_cult_10.png"
    img.save(out_path)
    print(f"✅ saved: {out_path}")
