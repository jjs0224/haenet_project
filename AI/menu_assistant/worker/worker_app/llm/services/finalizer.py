from __future__ import annotations

from typing import Any, Dict, List


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

    Output item schema (must match prompt_builder.py example):
      - item_id (str)
      - match_status ("exact" | "unknown")
      - menu_name_ko (str)
      - poly (list[list[float]])
      - menu_description_ko (str)
      - menu_description_en (str)   # step6 fills; step5 can be ""
      - risk_description_ko (str)
      - risk_description_en (str)   # step6 fills; step5 can be ""
      - risk_difficulty (int)       # exact: 0|1|2 / unknown: MUST be 3
      - user_risk_match (dict|None) # pass-through from decision_rules if exists
      - comment_ko (str)
      - comment_en (str)            # step6 fills; step5 can be ""
      - is_menu (str|None)          # only meaningful when src status unknown
      - drop_reason_ko (str|None)   # only when dropped/filtered

    Notes:
    - UI fields (tier/color/badge...) are intentionally NOT included (Option B).
    - Any extra keys are intentionally NOT produced (STRICT).
    """

    # Build maps
    in_map: Dict[str, Dict[str, Any]] = {
        it["item_id"]: it for it in llm_input_items if isinstance(it, dict) and it.get("item_id")
    }
    out_map: Dict[str, Dict[str, Any]] = {
        it["item_id"]: it for it in llm_output_items if isinstance(it, dict) and it.get("item_id")
    }

    final_items: List[Dict[str, Any]] = []
    dropped_items: List[Dict[str, Any]] = []

    for item_id in sorted(in_map.keys()):
        src = in_map[item_id]
        llm = out_map.get(item_id, {}) if isinstance(out_map.get(item_id, {}), dict) else {}

        # ----------------------------
        # 1) drop unknown non-menu
        # ----------------------------
        src_status = (src.get("status") or src.get("match_status") or "").lower().strip()
        is_menu = (llm.get("is_menu") or "").lower().strip()
        if src_status == "unknown" and is_menu in ("no", "false", "0"):
            dropped_items.append(
                {
                    "item_id": item_id,
                    "drop_reason_ko": llm.get("drop_reason_ko") or "",
                }
            )
            continue

        # ----------------------------
        # 2) match_status -> strict ("exact" | "unknown")
        # ----------------------------
        # src가 exact/close면 exact 유지
        if src_status in ("exact", "close"):
            match_status = "exact"
        else:
            # llm이 match_status를 줘도 strict schema는 exact/unknown만 허용
            llm_status = (llm.get("match_status") or "").lower().strip()
            match_status = "exact" if llm_status in ("exact", "llm_match") else "unknown"

        # ----------------------------
        # 3) core fields
        # ----------------------------
        menu_name_ko = (
            llm.get("menu_name_ko")
            or llm.get("menu_name")      # 혹시 LLM이 menu_name으로 준 경우
            or src.get("menu_name_ko")
            or src.get("menu_name")
            or ""
        )
        if not isinstance(menu_name_ko, str):
            menu_name_ko = str(menu_name_ko or "")
        menu_name_ko = menu_name_ko.strip()
        menu_name_en = llm.get("menu_name_en")
        if not isinstance(menu_name_en, str):
            menu_name_en = ""

        # 안전장치: 비어있으면 ko로라도 채워 스키마를 깨지 않게
        if not menu_name_en.strip():
            menu_name_en = ""

        poly = _ensure_poly(src.get("poly") or (src.get("match", {}) if isinstance(src.get("match"), dict) else {}).get("poly"))

        # descriptions: step5는 ko 채우고 en은 빈 값 유지(번역은 step6)
        confirmed = src.get("confirmed") if isinstance(src.get("confirmed"), dict) else {}
        evidence = src.get("evidence") if isinstance(src.get("evidence"), dict) else {}

        # ✅ B안: exact는 LLM 없이도 DB/confirmed 설명(있으면) 사용, 없으면 fallback
        menu_description_ko = _first_str(
            llm.get("menu_description_ko"),
            src.get("menu_description_ko"),
            confirmed.get("menu_description_ko"),
            confirmed.get("menu_description"),
            evidence.get("menu_description_ko"),
        )
        if not menu_description_ko:
            menu_description_ko = "메뉴 설명 정보가 제한적입니다. 주문 전 구성 재료를 확인하세요."

        risk_description_ko = _first_str(
            llm.get("risk_description_ko"),
            src.get("risk_description_ko"),
        )
        if not risk_description_ko:
            risk_description_ko = _risk_desc_from_user_risk_match(src.get("user_risk_match"))

        menu_description_en = (llm.get("menu_description_en") or "").strip()
        risk_description_en = (llm.get("risk_description_en") or "").strip()

        comment_ko = _first_str(
            llm.get("comment_ko"),
            _join_comment_ko(src.get("comment_ko")),
            _join_comment_ko(confirmed.get("comment_ko")),
        )
        if not comment_ko:
            comment_ko = "이 메뉴에 알러지 유발 성분이나 기피 식품이 포함되나요?"

        comment_en = (llm.get("comment_en") or "").strip()

        # ----------------------------
        # 4) risk_difficulty (strict rule)
        # ----------------------------
        # unknown이면 무조건 3, exact면 0|1|2 권장. 없으면 기본값 부여.
        rd = llm.get("risk_difficulty")
        if rd is None:
            rd = src.get("risk_difficulty")
        if match_status == "unknown":
            risk_difficulty = 3
        else:
            # exact인데 모델이 안 주면 0으로 보수적 기본
            try:
                risk_difficulty = int(rd) if rd is not None else 0
            except Exception:
                risk_difficulty = 0
            # exact는 0~2로 clamp
            if risk_difficulty < 0:
                risk_difficulty = 0
            if risk_difficulty > 2:
                risk_difficulty = 2

        # ----------------------------
        # 5) user_risk_match (pass-through 우선)
        # ----------------------------
        user_risk_match = src.get("user_risk_match")
        if user_risk_match is None:
            user_risk_match = llm.get("user_risk_match")

        # ----------------------------
        # 6) finalize strict item
        # ----------------------------
        final_items.append(
            {
                "item_id": item_id,
                "match_status": match_status,
                "menu_name_ko": menu_name_ko,
                "menu_name_en": menu_name_en,
                "poly": poly,

                "menu_description_ko": menu_description_ko,
                "menu_description_en": menu_description_en,

                "risk_description_ko": risk_description_ko,
                "risk_description_en": risk_description_en,

                "risk_difficulty": risk_difficulty,
                "user_risk_match": user_risk_match,

                "comment_ko": comment_ko,
                "comment_en": comment_en,

                # unknown에서만 의미 있는 필드(그 외엔 None 유지)
                "is_menu": llm.get("is_menu") if src_status == "unknown" else None,
                "drop_reason_ko": llm.get("drop_reason_ko") if src_status == "unknown" else None,
            }
        )

    return {
        "schema_version": "v1",
        "run_id": run_id,
        "user_profile": user_profile,
        "items": final_items,
        "dropped_items": dropped_items,
    }
