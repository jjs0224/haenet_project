# menu_assistant/worker/worker_app/llm/services/schema.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple


# -----------------------------
# Output schema (LLM -> JSON)
# -----------------------------

@dataclass
class LLMItemOutputV1:
    # ✅ required
    item_id: str
    match_status: str            # "exact" | "unknown"
    menu_name_ko: str
    menu_name_en: str  # ✅ NEW (Step5에서 생성, Step6에서 재번역 가능)
    poly: List[List[float]]

    menu_description_ko: str
    menu_description_en: str     # step6 fills; step5 can be ""

    risk_description_ko: str
    risk_description_en: str     # step6 fills; step5 can be ""

    risk_difficulty: int         # 0|1|2

    user_risk_match: Dict[str, Any]  # structured match info

    comment_ko: str
    comment_en: str              # step6 fills; step5 can be ""

    # ✅ optional but schema-controlled
    is_menu: Optional[str] = None            # "yes"|"no" (required when match_status=="unknown")
    drop_reason_ko: Optional[str] = None     # required when is_menu=="no" and match_status=="unknown"


@dataclass
class LLMOutputV1:
    schema_version: str
    run_id: str
    items: List[LLMItemOutputV1]


# -----------------------------
# Validators
# -----------------------------

def _is_non_empty_str(x: Any) -> bool:
    return isinstance(x, str) and x.strip() != ""


def _is_str(x: Any) -> bool:
    return isinstance(x, str)


def _is_bool(x: Any) -> bool:
    return isinstance(x, bool)


def _is_int(x: Any) -> bool:
    return isinstance(x, int) and not isinstance(x, bool)


def _is_poly(x: Any) -> bool:
    # poly: [[x,y], ...] 최소 4개 점 권장
    if not isinstance(x, list) or len(x) < 4:
        return False
    for p in x:
        if not isinstance(p, list) or len(p) != 2:
            return False
        if not (isinstance(p[0], (int, float)) and isinstance(p[1], (int, float))):
            return False
    return True


def _nullable_list_of_str(x: Any) -> bool:
    if x is None:
        return True
    if not isinstance(x, list):
        return False
    for v in x:
        if not isinstance(v, str) or not v.strip():
            return False
    return True


def validate_llm_output_v1(obj: Any) -> Tuple[bool, str]:
    """
    ✅ Strong validation:
    - en fields are REQUIRED keys but allow empty string in Step5
    - match_status is exact|unknown
    - unknown must include is_menu yes|no
    - if unknown & is_menu=no => drop_reason_ko required non-empty
    - risk_difficulty must be 0|1|2
    - user_risk_match must include required keys and types
    """
    if not isinstance(obj, dict):
        return False, "Root must be a JSON object"

    for k in ("schema_version", "run_id", "items"):
        if k not in obj:
            return False, f"Missing required root key: {k}"

    if not _is_non_empty_str(obj.get("schema_version")):
        return False, "schema_version must be non-empty string"

    if not _is_non_empty_str(obj.get("run_id")):
        return False, "run_id must be non-empty string"

    items = obj.get("items")
    if not isinstance(items, list):
        return False, "items must be a list"

    for i, it in enumerate(items):
        if not isinstance(it, dict):
            return False, f"items[{i}] must be an object"

        # ---- required keys (must exist) ----
        required_keys = [
            "item_id",
            "match_status",
            "menu_name_ko",
            "menu_name_en",
            "poly",
            "menu_description_ko",
            "menu_description_en",
            "risk_description_ko",
            "risk_description_en",
            "risk_difficulty",
            "user_risk_match",
            "comment_ko",
            "comment_en",
        ]
        for rk in required_keys:
            if rk not in it:
                return False, f"items[{i}] missing required key: {rk}"

        # ---- basic types ----
        if not _is_non_empty_str(it.get("item_id")):
            return False, f"items[{i}].item_id must be non-empty string"

        ms = it.get("match_status")
        if ms not in ("exact", "unknown"):
            return False, f"items[{i}].match_status must be 'exact' or 'unknown'"

        if not _is_non_empty_str(it.get("menu_name_ko")):
            return False, f"items[{i}].menu_name_ko must be non-empty string"

        # ✅ menu_name_en은 Step5에서 만들지만 실패 방지를 위해 string만 강제 (빈문자 허용)
        if not _is_str(it.get("menu_name_en")):
            return False, f"items[{i}].menu_name_en must be string"

        if not _is_poly(it.get("poly")):
            return False, f"items[{i}].poly must be polygon [[x,y],...] with >=4 points"

        # ko는 실제 내용 권장(빈문자 금지로 강제해도 되지만, 실패율이 올라가니 우선 non-empty로 유지)
        if not _is_non_empty_str(it.get("menu_description_ko")):
            return False, f"items[{i}].menu_description_ko must be non-empty string"

        if not _is_str(it.get("menu_description_en")):
            return False, f"items[{i}].menu_description_en must be string (can be empty in Step5)"

        if not _is_non_empty_str(it.get("risk_description_ko")):
            return False, f"items[{i}].risk_description_ko must be non-empty string"

        if not _is_str(it.get("risk_description_en")):
            return False, f"items[{i}].risk_description_en must be string (can be empty in Step5)"

        rd = it.get("risk_difficulty")
        if not _is_int(rd) or rd not in (0, 1, 2, 3):
            return False, f"items[{i}].risk_difficulty must be int 0|1|2|3"

        # ✅ 강제 규칙: unknown이면 3 고정
        if ms == "unknown" and rd != 3:
            return False, f"items[{i}].risk_difficulty must be 3 when match_status=='unknown'"

        # ✅ 강제 규칙: exact이면 0/1/2만 허용
        if ms == "exact" and rd == 3:
            return False, f"items[{i}].risk_difficulty must be 0|1|2 when match_status=='exact'"

        if not _is_non_empty_str(it.get("comment_ko")):
            return False, f"items[{i}].comment_ko must be non-empty string"

        if not _is_str(it.get("comment_en")):
            return False, f"items[{i}].comment_en must be string (can be empty in Step5)"

        # ---- user_risk_match structure ----
        urm = it.get("user_risk_match")
        if not isinstance(urm, dict):
            return False, f"items[{i}].user_risk_match must be object"

        for uk in ("allergy_tag_hits", "religion_hit", "avoid_food_hits", "has_any_match", "source"):
            if uk not in urm:
                return False, f"items[{i}].user_risk_match missing key: {uk}"

        if not _nullable_list_of_str(urm.get("allergy_tag_hits")):
            return False, f"items[{i}].user_risk_match.allergy_tag_hits must be list[str] or null"

        rh = urm.get("religion_hit")
        if rh is not None and not _is_non_empty_str(rh):
            return False, f"items[{i}].user_risk_match.religion_hit must be non-empty string or null"

        if not _nullable_list_of_str(urm.get("avoid_food_hits")):
            return False, f"items[{i}].user_risk_match.avoid_food_hits must be list[str] or null"

        if not _is_bool(urm.get("has_any_match")):
            return False, f"items[{i}].user_risk_match.has_any_match must be boolean"

        if urm.get("source") not in ("exact", "unknown"):
            return False, f"items[{i}].user_risk_match.source must be 'exact' or 'unknown'"

        # ---- unknown drop control ----
        if ms == "unknown":
            is_menu = it.get("is_menu")
            if is_menu not in ("yes", "no"):
                return False, f"items[{i}].is_menu required when match_status=='unknown' (yes|no)"

            if is_menu == "no":
                dr = it.get("drop_reason_ko")
                if not _is_non_empty_str(dr):
                    return False, f"items[{i}].drop_reason_ko required when is_menu=='no'"

        # exact이면 is_menu/drop_reason_ko는 없어도 됨(있으면 값만 타입 체크)
        if "is_menu" in it and it["is_menu"] is not None:
            if it["is_menu"] not in ("yes", "no"):
                return False, f"items[{i}].is_menu must be yes|no or null"

        if "drop_reason_ko" in it and it["drop_reason_ko"] is not None:
            if not _is_str(it["drop_reason_ko"]):
                return False, f"items[{i}].drop_reason_ko must be string or null"

    return True, "OK"


def validate_llm_output_against_input_ids(obj: Dict[str, Any], expected_ids: List[str]) -> Tuple[bool, str]:
    """
    Ensures output contains exactly the same set of item_ids as input.
    (Drop는 최종 finalizer에서 수행하고, LLM output은 id 1:1 유지)
    """
    if not isinstance(obj, dict) or "items" not in obj:
        return False, "Missing items in output"

    out_items = obj.get("items", [])
    if not isinstance(out_items, list):
        return False, "items must be list"

    out_ids = []
    for it in out_items:
        if isinstance(it, dict) and isinstance(it.get("item_id"), str):
            out_ids.append(it["item_id"])

    if sorted(out_ids) != sorted(expected_ids):
        return False, f"Output item_ids mismatch. expected={sorted(expected_ids)} got={sorted(out_ids)}"

    return True, "OK"
