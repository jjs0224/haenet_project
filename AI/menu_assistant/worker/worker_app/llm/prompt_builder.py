from __future__ import annotations

import json
from typing import Any, Dict, List


def build_step05_prompt(*, run_id: str, user_profile: Dict[str, Any], items: List[Dict[str, Any]]) -> Dict[str, str]:
    """
    Step05 Prompt Builder (PATCH-OUTPUT MINIMAL)

    ✅ 목표: Step05 LLM 출력 토큰을 극단적으로 줄이기
    - unknown items만 입력으로 들어온다는 전제(B안 유지)
    - LLM은 "판별 + ko 텍스트 + user_risk_match"만 생성
    - 나머지 필드(menu_name_en, *_en 등)는 finalizer/dataclass가 채우거나 Step06이 채움
    """

    # ✅ 최소 출력 스키마 (필수 키만)
    output_schema_example = {
        "schema_version": "v1",
        "run_id": run_id,
        "items": [
            {
                "item_id": "itm_0001",
                "match_status": "unknown",
                "is_menu": "yes",
                "drop_reason_ko": None,
                # menu_name_ko는 "선택" (없으면 finalizer가 입력값 사용)
                "menu_name_ko": "입력 텍스트(선택)",
                "menu_description_ko": "1~2문장 한국어 설명",
                "risk_description_ko": "사용자 조건 관점의 보수적 위험 설명(한국어)",
                "comment_ko": "직원에게 확인할 질문? (Yes/No)",
                "user_risk_match": {
                    "allergy_tag_hits": None,
                    "religion_hit": None,
                    "avoid_food_hits": None,
                    "has_any_match": False,
                    "source": "unknown",
                },
            }
        ],
    }

    system = (
        "You are a strict JSON generator for a menu safety assistant.\n"
        "Output ONLY valid JSON (no markdown, no extra text).\n"
        "Do NOT add keys beyond the schema example.\n\n"
        "HARD RULES:\n"
        "- One output item per input item (1:1).\n"
        "- Copy item_id exactly.\n"
        "- match_status MUST be 'unknown'.\n"
        "- is_menu MUST be 'yes' or 'no'.\n"
        "- If is_menu='no', drop_reason_ko MUST be non-empty Korean string.\n"
        "- menu_description_ko: 1~2 Korean sentences.\n"
        "- risk_description_ko: non-empty Korean string.\n"
        "- comment_ko: Korean question ending with '?' and preferably includes '(Yes/No)'.\n\n"
        "MENU vs NON-MENU:\n"
        "- is_menu='no' for option/size/add-on/notice/store-name only text.\n"
        "  Examples: 곱배기, 추가, 사리, 대/중/소, 리필, 공지, 안내, 이벤트, 원산지, 본점, 지점, 전문점.\n\n"
        "USER_RISK_MATCH:\n"
        "- Use ONLY user_profile fields (do NOT invent allergens).\n"
        "- allergy_tag_hits: list of tags from user_profile.allergy_tags if clearly implied; else null.\n"
        "- avoid_food_hits: list of strings from user_profile.avoid_foods if clearly implied; else null.\n"
        "- religion_hit: set only if user_profile.religion implies a direct check (islam_halal => 돼지고기/라드/알코올).\n"
        "- has_any_match: true if any hit exists.\n"
        "- source MUST be 'unknown'.\n\n"
        "OPTIONAL:\n"
        "- menu_name_ko: if input text is noisy, you MAY output a corrected/normalized Korean menu name. If unsure, omit.\n"
        "- If uncertain about ingredients/allergens, do NOT guess: ask via comment_ko and keep hits null.\n"
    )

    user = (
        "Return JSON that EXACTLY matches this schema shape.\n\n"
        "[SCHEMA EXAMPLE]\n"
        f"{json.dumps(output_schema_example, ensure_ascii=False)}\n\n"
        "[INPUT]\n"
        f"run_id: {run_id}\n"
        f"user_profile: {json.dumps(user_profile, ensure_ascii=False)}\n"
        f"items: {json.dumps(items, ensure_ascii=False)}\n"
    )

    return {"system": system, "user": user}
