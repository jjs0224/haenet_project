from __future__ import annotations
from typing import Dict, Any, List


def _extract_menu_names(reviews: List[Dict[str, Any]]) -> List[str]:
    menus: List[str] = []
    for r in reviews:
        v = r.get("menu_name")
        if isinstance(v, str) and v.strip():
            menus.append(v.strip())
        elif isinstance(v, list):
            for it in v:
                if isinstance(it, str) and it.strip():
                    menus.append(it.strip())

    seen = set()
    uniq: List[str] = []
    for m in menus:
        m2 = m.strip()
        if not m2 or m2 in seen:
            continue
        seen.add(m2)
        uniq.append(m2)
    return uniq


def _build_review_blocks(reviews: List[Dict[str, Any]], *, max_reviews: int = 6) -> str:
    """
    리뷰 텍스트(제목/내용/평점)를 prompt에 넣기 위한 블록.
    - 너무 길어지지 않게 max_reviews만 사용
    - review_content는 너무 길면 컷
    """
    blocks: List[str] = []
    for i, r in enumerate(reviews[:max_reviews], start=1):
        rid = r.get("review_id") or r.get("id")
        title = (r.get("review_title") or r.get("title") or "").strip()
        content = (r.get("review_content") or r.get("content") or "").strip()
        rating = r.get("rating")

        # content 너무 길면 잘라주기 (LLM이 핵심 톤만 보게)
        if len(content) > 220:
            content = content[:220].rstrip() + "..."

        # 빈 값 방어
        if not title:
            title = "(no title)"
        if not content:
            content = "(no notes)"

        blocks.append(
            f"""REVIEW {i} (id={rid}, rating={rating}):
- Title: {title}
- Notes: {content}"""
        )

    return "\n\n".join(blocks) if blocks else "No review text available"


def build_character_analysis_prompt(payload: Dict[str, Any]) -> str:
    # ✅ DEBUG START
    print("\n[CHAR_AGENT1] payload keys:", list((payload or {}).keys()))
    member_dbg = (payload or {}).get("member")
    reviews_dbg = (payload or {}).get("reviews")
    prof_dbg = (payload or {}).get("allergy_tags")
    print("[CHAR_AGENT1] member keys:", list((member_dbg or {}).keys()) if isinstance(member_dbg, dict) else type(member_dbg))
    print("[CHAR_AGENT1] reviews type/len:", type(reviews_dbg), len(reviews_dbg) if isinstance(reviews_dbg, list) else None)
    print("[CHAR_AGENT1] allergy_tags type/keys:", type(prof_dbg), list((prof_dbg or {}).keys()) if isinstance(prof_dbg, dict) else None)
    # ✅ DEBUG END

    member = payload.get("member") or {}
    reviews: List[Dict[str, Any]] = payload.get("reviews") or []
    prof = payload.get("allergy_tags") or {}  # 너 로그 기준 dict

    nickname = member.get("nickname") or "The Traveler"
    country = member.get("country") or "Unknown country"
    gender = member.get("gender") or "Unknown"

    menus = _extract_menu_names(reviews)[:50]  # ✅ 메뉴 더 많이 쓰게
    review_text = _build_review_blocks(reviews, max_reviews=6)

    allergies = prof.get("allergy_tags") or []
    avoid_foods = prof.get("avoid_foods") or []
    religion = prof.get("religion") or []

    # ✅ DEBUG: extracted values
    print("[CHAR_AGENT1] nickname/country/gender:", nickname, "/", country, "/", gender)
    print("[CHAR_AGENT1] menus count:", len(menus))
    print("[CHAR_AGENT1] menus sample:", menus[:12])
    print("[CHAR_AGENT1] allergies:", allergies)
    print("[CHAR_AGENT1] avoid_foods:", avoid_foods)
    print("[CHAR_AGENT1] religion:", religion)
    print("[CHAR_AGENT1] review_text preview:", (review_text[:300] + "...") if len(review_text) > 300 else review_text)

    return f"""
You are Agent 1: Human Mukbang Character Analyzer (NOT a monster).

Goal:
Create ONE HUMAN character concept based on:
- the user's gender, nickname, country vibe
- menus eaten (use MANY of them)
- review text tone (complaints, excitement, spice fear, cravings, etc.)
- restrictions (allergy/religion/avoid foods)
- contradictions (e.g., "can't eat spicy" but ate spicy) -> MUST turn into humor/personality

USER:
- Nickname: {nickname}
- Country vibe: {country}
- Gender: {gender}

REVIEW TEXT (MOST IMPORTANT for personality):
{review_text}

MENUS EATEN (use these to build props + outfit + comedic identity):
{", ".join(menus) if menus else "No menu data"}

RESTRICTIONS:
- Allergies: {", ".join(allergies) if allergies else "None"}
- Avoid foods (dislikes): {", ".join(avoid_foods) if avoid_foods else "None"}
- Religion diet: {", ".join(religion) if religion else "None"}

OUTPUT MUST BE VALID JSON ONLY.
No markdown, no code fences, no commentary.

JSON schema:
{{
  "display_name": "...",
  "gender_expression": "...",
  "core_vibe": "...",
  "dominant_emotion": "...",
  "energy_level": "...",
  "facial_expression": "...",
  "outfit_style": "...",
  "color_palette": ["..."],
  "food_influences": ["..."],   // summarize patterns (spicy / stew / bread / alcohol / dessert)
  "food_props": ["..."],        // USE MANY menus as wearable/held items (jinro bottle, skewers, stew bowl, bread bag)
  "pose_style": "..."
}}

RULES:
- MUST be fully human (no monsters, no hulk, no green skin).
- Must reflect review tone. If user complains about spicy, character must show spicy fear/struggle humor.
- Use menus as INTEGRATED design elements (belt accessory, pockets, badges, scarf pattern), NOT floating photos.
- Funny but safe. No profanity.
- Keep values short and image-usable (no long paragraphs).
""".strip()
