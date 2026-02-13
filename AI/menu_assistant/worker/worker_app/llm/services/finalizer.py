from __future__ import annotations

from typing import Any, Dict, List

from menu_assistant.worker.worker_app.llm.services.schema import FinalItemV1, FinalOutputV1


def _first_str(*vals: Any) -> str:
    for v in vals:
        if isinstance(v, str) and v.strip():
            return v.strip()
    return ""


def _join_comment_ko(x: Any) -> str:
    # DecisionRules는 list[str]로 내려줄 수 있음 -> final은 str
    if isinstance(x, str) and x.strip():
        return x.strip()
    if isinstance(x, list):
        parts = [s.strip() for s in x if isinstance(s, str) and s.strip()]
        if parts:
            return "\n".join(parts)
    return ""



def _safe_int_choice(x: Any, *, default: int) -> int:
    """Parse an int safely with allowed range (0..3)."""
    try:
        v = int(x)
    except Exception:
        return default
    if v not in (0, 1, 2, 3):
        return default
    return v

def _risk_desc_from_user_risk_match(urm: Any) -> str:
    # 보수적으로만: 확정 재료가 아니라면 단정 금지
    if not isinstance(urm, dict):
        return "사용자 알러지/기피/종교 정보와의 충돌 가능성이 있어 주문 전 재료 확인이 필요합니다."
    if bool(urm.get("has_any_risk")) or bool(urm.get("has_any_match")):
        return "사용자 알러지/기피/종교 정보와 충돌 가능성이 있습니다. 직원에게 재료(소스/육수/토핑 포함)를 확인하세요."
    return "현재 확인된 정보만으로는 사용자 알러지/기피/종교 조건과의 명확한 충돌 신호가 적습니다. 단, 소스/육수/토핑은 추가 확인을 권장합니다."


def _ensure_poly(poly: Any) -> List[List[float]]:
    # poly는 UI overlay에 쓰이므로, None/비정상일 때는 빈 리스트로 안전하게 반환
    if not isinstance(poly, list):
        return []
    out: List[List[float]] = []
    for pt in poly:
        if isinstance(pt, (list, tuple)) and len(pt) >= 2:
            try:
                x = float(pt[0])
                y = float(pt[1])
                out.append([x, y])
            except Exception:
                continue
    return out


def merge_llm_output_to_final(
    *,
    run_id: str,
    user_profile: Dict[str, Any],
    llm_input_items: List[Dict[str, Any]],
    llm_output_items: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """
    FINAL.JSON (STRICT FLAT SCHEMA, OPTION B: no 'ui')

    - exact: DecisionRules.confirmed + DecisionRules.user_risk_match/comment_ko 를 우선 사용
    - unknown: LLM 결과를 우선 사용 (단, schema 강제/기본값은 여기서 보정)
    - unknown is_menu == "no" 인 항목은 dropped_items 로 이동
    """

    out_by_id: Dict[str, Dict[str, Any]] = {}
    for it in llm_output_items:
        if isinstance(it, dict):
            iid = it.get("item_id")
            if isinstance(iid, str) and iid.strip():
                out_by_id[iid.strip()] = it

    items: List[FinalItemV1] = []
    dropped_items: List[Dict[str, Any]] = []

    for src in llm_input_items:
        if not isinstance(src, dict):
            continue
        item_id = _first_str(src.get("item_id"))
        if not item_id:
            continue

        status = _first_str(src.get("match_status"), src.get("status"), "unknown").lower()
        poly = _ensure_poly(src.get("poly"))

        confirmed = src.get("confirmed") if isinstance(src.get("confirmed"), dict) else None
        src_menu_name = _first_str(src.get("menu_name"), src.get("menu_norm"), src.get("raw_menu"), src.get("menu"))

        out = out_by_id.get(item_id, {})
        out_match_status = _first_str(out.get("match_status"), status).lower()

        # -------------------------
        # unknown drop handling
        # -------------------------
        is_menu = out.get("is_menu")
        if isinstance(is_menu, str):
            is_menu = is_menu.strip().lower()
        else:
            is_menu = None

        if out_match_status == "unknown" and is_menu == "no":
            dropped_items.append(
                {
                    "item_id": item_id,
                    "text": src_menu_name,
                    "poly": poly,
                    "reason_ko": _first_str(out.get("drop_reason_ko"), "메뉴 항목이 아닌 것으로 판단됨"),
                }
            )
            continue

        # -------------------------
        # exact (no LLM required)
        # -------------------------
        if status == "exact" and isinstance(confirmed, dict):
            menu_name_ko = _first_str(confirmed.get("menu"), src_menu_name)
            menu_desc_ko = _first_str(
                confirmed.get("menu_description_ko"),
                src.get("menu_description_ko"),
                "",
            )

            user_risk_match = src.get("user_risk_match") if isinstance(src.get("user_risk_match"), dict) else {}
            risk_desc_ko = _first_str(
                src.get("risk_description_ko"),
                _risk_desc_from_user_risk_match(user_risk_match),
            )

            comment_ko = _join_comment_ko(src.get("comment_ko"))
            # Step6에서 번역되므로 Step5에서는 빈 값 유지
            item_dict = {
                "item_id": item_id,
                "match_status": "exact",
                "menu_name_ko": menu_name_ko,
                "menu_name_en": _first_str(src.get("menu_name_en"), ""),  # step6 fills
                "poly": poly,
                "menu_description_ko": menu_desc_ko,
                "menu_description_en": "",
                "risk_description_ko": risk_desc_ko,
                "risk_description_en": "",
                "risk_difficulty": _safe_int_choice(src.get("risk_difficulty"), default=0),
                "user_risk_match": user_risk_match,
                "comment_ko": comment_ko,
                "comment_en": "",
            }
            items.append(FinalItemV1.from_dict(item_dict))
            continue

        # -------------------------
        # unknown (LLM-driven)
        # -------------------------
        menu_name_ko = _first_str(out.get("menu_name_ko"), src_menu_name)
        menu_desc_ko = _first_str(out.get("menu_description_ko"), "")
        risk_desc_ko = _first_str(out.get("risk_description_ko"), "")
        comment_ko = _join_comment_ko(out.get("comment_ko"))

        # if LLM did not output, fallbacks (conservative)
        if not menu_desc_ko:
            menu_desc_ko = "메뉴 설명 정보가 부족합니다. 직원에게 재료/조리방식(소스/육수 포함)을 확인하세요."
        if not risk_desc_ko:
            urm = out.get("user_risk_match") if isinstance(out.get("user_risk_match"), dict) else {}
            risk_desc_ko = _risk_desc_from_user_risk_match(urm)
        if not comment_ko:
            comment_ko = "이 메뉴(또는 소스/육수)에 알러지 유발 재료나 기피/종교 제한 성분이 들어가나요? (Yes/No)"

        rd_int = _safe_int_choice(out.get("risk_difficulty"), default=3)

        item_dict = {
            "item_id": item_id,
            "match_status": "unknown",
            "menu_name_ko": menu_name_ko,
            "menu_name_en": _first_str(out.get("menu_name_en"), ""),  # step6 fills
            "poly": poly,
            "menu_description_ko": menu_desc_ko,
            "menu_description_en": "",
            "risk_description_ko": risk_desc_ko,
            "risk_description_en": "",
            "risk_difficulty": rd_int,  # unknown default 3
            "user_risk_match": out.get("user_risk_match") if isinstance(out.get("user_risk_match"), dict) else {},
            "comment_ko": comment_ko,
            "comment_en": "",
            "is_menu": is_menu or "yes",
            "drop_reason_ko": _first_str(out.get("drop_reason_ko")) or None,
        }
        items.append(FinalItemV1.from_dict(item_dict))

    final = FinalOutputV1(
        schema_version="v1",
        run_id=run_id,
        user_profile=user_profile if isinstance(user_profile, dict) else {},
        items=items,
        dropped_items=dropped_items,
    )
    return final.to_dict()
