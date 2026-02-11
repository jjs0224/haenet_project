from __future__ import annotations

import json
from typing import Any, Dict, List


def build_step05_prompt(*, run_id: str, user_profile: Dict[str, Any], items: List[Dict[str, Any]]) -> Dict[str, str]:
    """
    Step05 Prompt Builder (STRICT SCHEMA-DRIVEN)
    NOTE: Step05는 unknown items만 LLM에 보낸다는 전제(속도 최적화 B안).
    """

    # ✅ unknown-only 예시로 축소 (토큰 절감 + 혼선 감소)
    output_schema_example = {
        "schema_version": "v1",
        "run_id": run_id,
        "items": [
            {
                "item_id": "itm_0001",
                "match_status": "unknown",

                "menu_name_ko": "입력의 menu_name을 그대로 복사",
                "menu_name_en": "",
                "poly": [[0, 0], [1, 0], [1, 1], [0, 1]],

                "menu_description_ko": "메뉴 설명 정보가 제한적입니다. 주문 전 구성 재료를 확인하세요.",
                "menu_description_en": "",

                "risk_description_ko": "사용자 알러지/종교/기피 식품과의 충돌 가능성이 있어 주문 전 재료 확인이 필요합니다.",
                "risk_description_en": "",

                "risk_difficulty": 3,

                "user_risk_match": {
                    "allergy_tag_hits": None,
                    "religion_hit": None,
                    "avoid_food_hits": None,
                    "has_any_match": False,
                    "source": "unknown"
                },

                "comment_ko": "이 항목이 실제 메뉴라면, 알러지 유발 성분이 포함되나요?",
                "comment_en": "",

                "is_menu": "yes",
                "drop_reason_ko": None
            }
        ]
    }

    # ✅ unknown-only 호출 전제로 시스템 규칙도 축소/정렬
    system = (
        "You are a strict JSON generator for a menu safety assistant.\n"
        "Output ONLY valid JSON. No markdown, no explanations.\n"
        "Do NOT include any keys not defined in the schema.\n\n"

        "GOAL:\n"
        "- Personalize safety guidance by comparing each menu item against the user's profile.\n"
        "- Prioritize user safety. When uncertain, be conservative.\n\n"

        "SCHEMA ENFORCEMENT:\n"
        "- Output MUST exactly match the provided schema structure.\n"
        "- Missing required fields or extra fields are NOT allowed.\n"
        "- All *_ko fields MUST be Korean.\n"
        "- All *_en fields MUST be empty strings in this step.\n\n"

        "EVIDENCE RULES:\n"
        "- Use ONLY evidence contained in each input item and the user_profile.\n"
        "- If an item has confirmed.ingredients or confirmed.alg_tags, you may use them.\n"
        "- If confirmed data is missing/empty, you MAY conservatively infer POSSIBLE allergen tags based on menu_name_ko.\n"
        "- Only infer common, widely known allergens.\n"
        "- If unsure, leave allergy_tag_hits as null and ask via comment_ko.\n\n"
        
        "ALLOWED ALLERGEN TAGS:\n"
        "- You may ONLY use the following allergen tags:"
        "ALG_CELERY, ALG_CEREALS_GLUTEN, ALG_CRUSTACEANS, ALG_EGG,"
        "ALG_FISH, ALG_MILK, ALG_MOLLUSCS, ALG_MUSTARD,"
        "ALG_SESAME, ALG_SOY, ALG_TREE_NUTS\n"
        "- Do NOT output any allergen tags outside this list.\n\n"


        "UNKNOWN / CONFIRMED BEHAVIOR:\n"
        "- If match_status='exact' and confirmed exists: you may compare against user_profile concretely.\n"
        "- If match_status!='exact' or confirmed missing: treat as unknown and be conservative.\n\n"

        "RISK DIFFICULTY (0-3):\n"
        "- 3: unknown ingredients OR any potential user conflict that cannot be ruled out.\n"
        "- 2: some evidence suggests possible conflict but not explicit.\n"
        "- 1: evidence suggests low risk for this user.\n"
        "- 0: evidence clearly shows no conflict for this user.\n"
        "- When in doubt, choose the higher difficulty.\n\n"
        "- If match_status=='unknown', risk_difficulty MUST be 3.\n"
        "- If match_status=='exact', risk_difficulty MUST be 0|1|2 (NOT 3).\n\n"

        "NON-EMPTY REQUIRED TEXT FIELDS:\n"
        "- menu_description_ko: 1~2 Korean sentences (minimum 1 sentence, maximum 2).\n"
        "- If is_menu='yes': describe what the dish is (ingredients/cooking style) in 1~2 sentences.\n"
        "- risk_description_ko: non-empty Korean string.\n"
        "- comment_ko: non-empty Korean question ending with '?'.\n"
        "- If insufficient information, use conservative generic text.\n\n"

        "MENU / NON-MENU FILTER:\n"
        "- Decide whether the text is an actual orderable menu item.\n"
        "- Set is_menu to 'yes' or 'no'.\n"
        "- If is_menu='no', drop_reason_ko MUST be a non-empty Korean string.\n"
        "- Set is_menu='no' for option/size/notice/store-name style text such as:\n"
        "  '곱배기', '추가', '사리', '대/중/소', '리필', '공지', '안내', '이벤트', '원산지',\n"
        "  or store/business names like 'OO식당', 'OO카페', '본점', '지점', '전문점'.\n\n"

        "USER_RISK_MATCH RULES:\n"
        "- user_risk_match MUST be present for ALL items.\n"
        "- user_risk_match.source MUST be 'exact' or 'unknown'.\n"
        "- In this step, set user_risk_match.source='unknown' for unknown items.\n"
        "- allergy_tag_hits / avoid_food_hits MUST be list[str] or null.\n"
        "- religion_hit MUST be string or null.\n"
        "- has_any_match MUST be boolean.\n\n"

        "COMMENT GENERATION RULES:\n"
        "- comment_ko must be a short, staff-friendly Korean question ending with '?'.\n"
        "- If user has allergy_tag_hits: ask whether those allergens/ingredients are included or cross-contaminated.\n"
        "- If religion_hit exists: ask whether prohibited items (e.g., 돼지고기/알코올) or related stock/sauce are used.\n"
        "- If only unknown: ask for ingredient list, broth/sauce base, and cross-contamination.\n\n"

        "COPY RULES:\n"
        "- Output exactly one item per input item.\n"
        "- item_id and poly MUST be copied exactly from input.\n"
        "- menu_name_ko MUST be copied from input.menu_name or input.menu_name_ko when present.\n"
        "- comment_en / menu_description_en / risk_description_en MUST be empty strings.\n"
    )

    user = (
        "Generate output JSON that EXACTLY matches the schema below.\n\n"
        "[OUTPUT SCHEMA EXAMPLE]\n"
        f"{json.dumps(output_schema_example, ensure_ascii=False, indent=2)}\n\n"

        "[INPUT]\n"
        f"run_id: {run_id}\n"
        f"user_profile: {json.dumps(user_profile, ensure_ascii=False)}\n"
        f"items: {json.dumps(items, ensure_ascii=False)}\n\n"

        "PERSONALIZATION CHECKLIST (use only evidence in input):\n"
        "- Compare user_profile.allergy_tags to item.confirmed.alg_tags (if present).\n"
        "- Compare user_profile.avoid_foods to item.confirmed.ingredients AND menu text (if present).\n"
        "- Compare user_profile.religion to evidence: if unknown, ask about prohibited items conservatively.\n"
        "- If no confirmed evidence, do NOT guess ingredients; ask staff via comment_ko.\n\n"

        "RULES:\n"
        "- Output exactly one item per input item.\n"
        "- item_id and poly MUST be copied exactly from input.\n"
        "- Do NOT add or remove items.\n"
        "- Do NOT add extra fields.\n"
    )

    return {"system": system, "user": user}
