# C:\Users\201\Desktop\PGHfolder\haenet\AI\menu_assistant\worker\worker_app\llm\services\decision_rules.py
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple
import re


# ------------------------------------------------------------
# Utility helpers
# ------------------------------------------------------------

# ------------------------------------------------------------
# Human-friendly label helpers (KO)
# ------------------------------------------------------------

ALG_TAG_KO_MAP = {
    # 주요 14대 알레르기 + 자주 쓰는 태그 기준(프로젝트 태그에 맞게 확장)
    "ALG_CEREALS_GLUTEN": "글루텐(밀/보리/호밀 등)",
    "ALG_CRUSTACEANS": "갑각류(새우/게 등)",
    "ALG_EGGS": "계란",
    "ALG_FISH": "생선",
    "ALG_PEANUT": "땅콩",
    "ALG_SOY": "대두(콩)",
    "ALG_MILK": "우유/유제품",
    "ALG_NUTS": "견과류",
    "ALG_CELERY": "셀러리",
    "ALG_MUSTARD": "겨자",
    "ALG_SESAME": "참깨",
    "ALG_SULPHITES": "아황산류",
    "ALG_LUPIN": "루핀",
    "ALG_MOLLUSCS": "연체류(조개/굴/전복 등)",
    # ✅ alias (user dataset 표기 호환)
    "ALG_EGG": "계란",
    "ALG_TREE_NUTS": "견과류",
}

# 사용자가 영어로 avoid를 넣는 경우를 위한 최소 사전(필요시 확장)
AVOID_WORD_KO_MAP = {
    "pork": "돼지고기",
    "beef": "소고기",
    "chicken": "닭고기",
    "lamb": "양고기",
    "milk": "우유",
    "cheese": "치즈",
    "butter": "버터",
    "cream": "크림",
    "egg": "계란",
    "shrimp": "새우",
    "crab": "게",
    "lobster": "랍스터",
    "fish": "생선",
    "shellfish": "해산물(조개/갑각류)",
    "peanut": "땅콩",
    "nuts": "견과류",
    "wheat": "밀",
    "gluten": "글루텐",
    "alcohol": "알코올",
}

def _alg_tag_to_ko(tag: Any) -> str:
    t = _safe_str(tag) or ""
    return ALG_TAG_KO_MAP.get(t, t)  # 모르면 원문 유지

def _avoid_word_to_ko_hint(word: Any) -> Optional[str]:
    w = _safe_str(word)
    if not w:
        return None
    lw = w.lower()
    # 완전 일치 우선
    if lw in AVOID_WORD_KO_MAP:
        return AVOID_WORD_KO_MAP[lw]
    # 부분 힌트(예: "pork broth" 같은 경우)
    for k, ko in AVOID_WORD_KO_MAP.items():
        if k in lw:
            return ko
    return None


def _safe_str(v: Any) -> Optional[str]:
    if v is None:
        return None
    s = str(v).strip()
    return s if s else None


def _lower(v: Any) -> str:
    return str(v).strip().lower() if v is not None else ""


def _as_list(v: Any) -> List[Any]:
    if v is None:
        return []
    if isinstance(v, list):
        return v
    return [v]


def _pick_text(rec: Dict[str, Any]) -> str:
    """
    Step4 결과 기준으로 메뉴 텍스트 후보를 안전하게 선택.
    - raw_menu / menu_norm 우선
    - (레거시 호환) menu_final/raw_menu_main 등도 fallback으로 유지
    """
    for k in ("raw_menu", "menu_norm", "menu_final", "raw_menu_main", "menu_name", "menu", "used_query", "query", "text"):
        v = rec.get(k)
        if isinstance(v, str) and v.strip():
            return v.strip()
    return ""


def _get_status(rec: Dict[str, Any]) -> str:
    """
    Step4: match_status = exact | unknown (우선)
    레거시: status / match.status 도 fallback으로 지원
    """
    raw = rec.get("match_status")
    if raw is None:
        raw = rec.get("status")
    if raw is None:
        m = rec.get("match")
        if isinstance(m, dict):
            raw = m.get("status")

    s = _lower(raw)

    if s == "exact" or "exact" in s:
        return "exact"
    if s == "unknown":
        return "unknown"

    # 레거시/확장 여지
    if s == "close" or "close" in s:
        return "close"
    if "ambiguous" in s:
        return "ambiguous"
    if "not_found" in s:
        return "not_found"

    # Step4 기준: 모르는 건 unknown 취급(LLM 판단 대상으로)
    return "unknown"


def _extract_confirmed(rec: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    c = rec.get("confirmed")
    if not isinstance(c, dict):
        return None

    menu_id = _safe_str(c.get("menu_id") or c.get("id"))
    menu = _safe_str(c.get("menu"))
    ingredients_ko = _as_list(c.get("ingredients"))
    alg_tags = _as_list(c.get("alg_tags"))
    menu_description_ko = _safe_str(c.get("menu_description_ko") or c.get("menu_description")) or ""

    if not menu:
        return None

    return {
        "menu_id": menu_id,
        "menu": menu,
        "ingredients": ingredients_ko,
        "alg_tags": alg_tags,
        # ✅ 핵심: step5/finalizer가 읽을 수 있게 유지
        "menu_description_ko": menu_description_ko,
    }



# ------------------------------------------------------------
# Risk-match + comment helpers (MVP)
# ------------------------------------------------------------

def _compute_user_risk_match(
    *,
    user_profile: Optional[Dict[str, Any]],
    confirmed: Dict[str, Any],
) -> Dict[str, Any]:
    if not isinstance(user_profile, dict):
        return {
            "allergy_tag_hits": None,
            "avoid_food_hits": None,
            "religion_hit": None,
            "has_any_match": False,
            "source": "exact",
        }

    user_allergy = set(str(x).strip() for x in _as_list(user_profile.get("allergy_tags")) if str(x).strip())
    user_avoid = [str(x).strip() for x in _as_list(user_profile.get("avoid_foods")) if str(x).strip()]
    religion = _safe_str(user_profile.get("religion"))

    conf_alg = set(str(x).strip() for x in _as_list(confirmed.get("alg_tags")) if str(x).strip())
    conf_ing = [str(x).strip() for x in _as_list(confirmed.get("ingredients")) if str(x).strip()]
    conf_menu = _safe_str(confirmed.get("menu")) or ""

    allergy_hits = sorted(list(user_allergy.intersection(conf_alg)))

    # ✅ avoid_food 매칭 정규화: 대소문자/공백/구두점 차이로 인한 누락 방지
    def _norm(s: str) -> str:
        s = (s or "").strip().casefold()
        # 공백/구두점 최소 정리 (비교용)
        return re.sub(r"[\s,./()\-+]+", "", s)

    ing_tokens = {_norm(x) for x in conf_ing if _norm(x)}
    menu_token = _norm(conf_menu)
    avoid_hits: List[str] = []
    for w in user_avoid:
        nw = _norm(w)
        if not nw:
            continue
        # 1) 토큰 단위 일치 우선
        if nw in ing_tokens:
            avoid_hits.append(w)
            continue
        # 2) substring fallback (기존 동작 유지 성격)
        if nw and (nw in menu_token or any(nw in t for t in ing_tokens)):
            avoid_hits.append(w)

    religion_flags: List[str] = []
    if religion == "islam_halal":
        blob = (conf_menu + " " + " ".join(conf_ing)).lower()
        if any(k in blob for k in ["술","소주","맥주","와인","럼","브랜디","청하","막걸리","alcohol","wine","beer","soju"]):
            religion_flags.append("ALCOHOL_SUSPECT")
        if any(k in blob for k in ["돼지","삼겹","족발","보쌈","pork"]):
            religion_flags.append("PORK_SUSPECT")
        if any(k in blob for k in ["라드","lard"]):
            religion_flags.append("LARD_SUSPECT")

    has_any = bool(allergy_hits or avoid_hits or religion_flags)

    return {
        "allergy_tag_hits": allergy_hits or None,
        "avoid_food_hits": avoid_hits or None,
        "religion_hit": ",".join(religion_flags) if religion_flags else None,
        "has_any_match": has_any,
        "source": "exact",
    }





def _compute_risk_difficulty_exact(*, risk_match: Dict[str, Any]) -> int:
    """Exact-only risk_difficulty (0/1/2)

    Rule (user request):
      - 2: allergy_tag_hits OR religion_hits has at least one element
      - 1: only avoid_food_hits has at least one element
      - 0: no hits
    """
    if not isinstance(risk_match, dict):
        return 0
    allergy_hits = risk_match.get("allergy_tag_hits") or []
    religion_hits = risk_match.get("religion_hits") or []
    avoid_hits = risk_match.get("avoid_food_hits") or []

    if allergy_hits or religion_hits:
        return 2
    if avoid_hits:
        return 1
    return 0

def _build_comment_exact(
    *,
    confirmed: Dict[str, Any],
    risk_match: Dict[str, Any],
    user_profile: Optional[Dict[str, Any]],
) -> List[str]:
    """
    직원에게 보여줄 Yes/No 질문(comment_ko) 생성 (exact용).
    - hit가 있으면 hit 기반으로 1~3개 질문
    - hit가 없으면 "알러지 유발 재료 포함 여부" 같은 보수적 질문 1개
    """
    out: List[str] = []

    allergy_hits = _as_list(risk_match.get("allergy_tag_hits"))
    avoid_hits = _as_list(risk_match.get("avoid_food_hits"))
    religion_hits = _as_list(risk_match.get("religion_hits"))

    # 1) allergy tag 기반 질문
    #    (태그->자연어 매핑은 추후 확장 가능. 지금은 태그 그대로 노출하되, 예시를 괄호로 붙이는 정도)
    # 1) allergy tag 기반 질문
    for t in allergy_hits[:2]:
        t_ko = _alg_tag_to_ko(t)
        # 한국 점원이 바로 이해하도록: 한글명 우선 + 태그코드는 괄호로 보조
        out.append(f"저는 ({t_ko})알러지가 있는데 이 메뉴 먹어도 되나요? (Yes/No)")

    # 2) avoid food 기반 질문
    for w in avoid_hits[:2]:
        ko_hint = _avoid_word_to_ko_hint(w)
        if ko_hint:
            out.append(f"저는 '{w}'({ko_hint})을/를 싫어하는데 빼고 주실수있나요? (Yes/No)")
        else:
            out.append(f"저는 '{w}'을/를 싫어하는데 빼고 주실수있나요? (Yes/No)")

    # 3) religion 기반 질문 (MVP: halal)
    if religion_hits:
        # 너무 길어지지 않게 1개로 묶어서 질문
        if "ALCOHOL_SUSPECT" in religion_hits:
            out.append("이 메뉴(또는 소스/육수)에 알코올이 들어가나요? (Yes/No)")
        if "PORK_SUSPECT" in religion_hits or "LARD_SUSPECT" in religion_hits:
            out.append("이 메뉴(또는 소스/육수)에 돼지고기/라드가 들어가나요? (Yes/No)")

    # 4) 아무것도 없으면 보수적 확인 질문 1개
    if not out:
        # user_profile이 있으면 그 중 대표 1개를 중심으로 보수적으로 질문
        if isinstance(user_profile, dict):
            at = _as_list(user_profile.get("allergy_tags"))
            af = _as_list(user_profile.get("avoid_foods"))
            rel = _safe_str(user_profile.get("religion"))

            # 우선순위: allergy_tags -> avoid_foods -> religion
            if at:
                # ALG_TAG → 한글명으로 변환
                t = at[0]
                t_ko = _alg_tag_to_ko(t)
                out.append(
                    f"저는 알레르기({t_ko})가 있는데 이 메뉴를 먹어도 되나요? "
                    f"(소스/육수/토핑 포함 여부 확인) (Yes/No)"
                )

            elif af:
                w = af[0]
                ko_hint = _avoid_word_to_ko_hint(w)
                if ko_hint:
                    out.append(
                        f"이 메뉴에 '{w}'({ko_hint})가 들어가나요? "
                        f"(소스/육수/토핑 포함) (Yes/No)"
                    )
                else:
                    out.append(
                        f"이 메뉴에 '{w}'가 들어가나요? "
                        f"(소스/육수/토핑 포함) (Yes/No)"
                    )

            elif rel == "islam_halal":
                out.append(
                    "이 메뉴(또는 소스/육수)에 돼지고기, 라드, 알코올이 들어가나요? (Yes/No)"
                )

            else:
                out.append(
                    "이 메뉴에 알레르기 유발 재료(견과류, 유제품, 계란, 밀, 해산물 등)가 "
                    "포함되나요? (소스/육수 포함) (Yes/No)"
                )
        else:
            out.append(
                "이 메뉴에 알레르기 유발 재료(견과류, 유제품, 계란, 밀, 해산물 등)가 "
                "포함되나요? (소스/육수 포함) (Yes/No)"
            )

    # 중복 제거(순서 유지)
    seen = set()
    uniq: List[str] = []
    for s in out:
        if s not in seen:
            uniq.append(s)
            seen.add(s)
    return uniq


# ------------------------------------------------------------
# DecisionRules
# ------------------------------------------------------------

class DecisionRules:
    """
    Step05용 LLM 입력 아이템 생성 규칙 클래스 (Step4 결과 스키마 대응)

    - match_status == "exact"  : confirmed 기반으로 LLM에 제공 + (가능하면) user_risk_match/comment_ko 생성
    - match_status == "unknown": item_id/poly/menu_norm 기반으로 LLM에 제공 (LLM이 메뉴여부/추정/드랍 판단)
    """

    def __init__(
        self,
        *,
        require_poly: bool = True,
        user_profile: Optional[Dict[str, Any]] = None,
    ) -> None:
        self.require_poly = require_poly
        self.user_profile = user_profile

    def build_llm_items(
        self,
        rag_match: Any,
    ) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:

        records = self._extract_records(rag_match)

        items: List[Dict[str, Any]] = []
        dropped = 0
        exact_out = 0
        unknown_out = 0

        seq = 0
        for rec in records:
            if not isinstance(rec, dict):
                dropped += 1
                continue

            status = _get_status(rec)

            # poly check
            poly = rec.get("poly")
            if poly is None:
                m = rec.get("match")
                if isinstance(m, dict):
                    poly = m.get("poly")

            if self.require_poly and poly is None:
                dropped += 1
                continue

            # ✅ item_id: Step4에서 들어온 값 우선 사용
            item_id = _safe_str(rec.get("item_id"))
            if not item_id:
                seq += 1
                item_id = f"itm_{seq:04d}"

            if status == "exact":
                out = self._build_exact(item_id, rec, poly)
                if out:
                    items.append(out)
                    exact_out += 1
                else:
                    dropped += 1
                continue

            if status == "unknown":
                out = self._build_unknown(item_id, rec, poly)
                if out:
                    items.append(out)
                    unknown_out += 1
                else:
                    dropped += 1
                continue

            # 레거시는 일단 drop (Step4 기준에 맞추는 초안)
            dropped += 1

        meta = {
            "total_in": len(records),
            "total_out": len(items),
            "exact_out": exact_out,
            "unknown_out": unknown_out,
            "dropped": dropped,
        }
        return items, meta

    # --------------------------------------------------------
    # Internal helpers
    # --------------------------------------------------------

    def _extract_records(self, rag_match: Any) -> List[Any]:
        if isinstance(rag_match, list):
            return rag_match
        if isinstance(rag_match, dict):
            if isinstance(rag_match.get("items"), list):
                return rag_match["items"]
            if "match_status" in rag_match or "status" in rag_match:
                return [rag_match]
        return []

    def _build_exact(
        self,
        item_id: str,
        rec: Dict[str, Any],
        poly: Any,
    ) -> Optional[Dict[str, Any]]:

        confirmed = _extract_confirmed(rec)
        if not confirmed:
            return None

        raw_menu = _safe_str(rec.get("raw_menu")) or _pick_text(rec)
        menu_norm = _safe_str(rec.get("menu_norm")) or _safe_str(rec.get("menu_name")) or raw_menu

        # user_risk_match + comment (프로필 없으면 기본값)
        risk_match = _compute_user_risk_match(user_profile=self.user_profile, confirmed=confirmed)
        comment_ko = _build_comment_exact(confirmed=confirmed, risk_match=risk_match, user_profile=self.user_profile)
        risk_difficulty = _compute_risk_difficulty_exact(risk_match=risk_match)

        # ✅ Step4 스키마 기반 필드 (네가 요청한 핵심)
        out: Dict[str, Any] = {
            "item_id": item_id,
            "raw_menu": raw_menu,
            "menu_norm": menu_norm,
            "poly": poly,
            "match_status": "exact",
            "confirmed": confirmed,

            # 프론트 표시용(추후 step05 finalizer/translate로 carry)
            "user_risk_match": risk_match,
            "comment_ko": comment_ko,
            "risk_difficulty": risk_difficulty,
        }

        # _build_exact 내부 out.update(...) 부분만 정리

        out.update(
            {
                "status": "exact",
                "menu_name": confirmed.get("menu"),
                "evidence": {
                    "menu_id": confirmed.get("menu_id"),
                    "ingredients": _as_list(confirmed.get("ingredients")),
                    "alg_tags": _as_list(confirmed.get("alg_tags")),
                    "menu_description_ko": confirmed.get("menu_description_ko") or "",
                },
                # trace(기존 step05 normalize에서 사용)
                "menu": confirmed.get("menu"),
                "menu_id": confirmed.get("menu_id"),
                "ingredients": _as_list(confirmed.get("ingredients")),
                "alg_tags": _as_list(confirmed.get("alg_tags")),
                "menu_description_ko": confirmed.get("menu_description_ko") or "",
            }
        )

        return out

    def _build_unknown(
        self,
        item_id: str,
        rec: Dict[str, Any],
        poly: Any,
    ) -> Optional[Dict[str, Any]]:

        raw_menu = _safe_str(rec.get("raw_menu")) or _pick_text(rec)
        menu_norm = _safe_str(rec.get("menu_norm")) or raw_menu
        if not menu_norm:
            return None

        out: Dict[str, Any] = {
            "item_id": item_id,
            "raw_menu": raw_menu,
            "menu_norm": menu_norm,
            "poly": poly,
            "match_status": "unknown",
            "confirmed": None,
        }

        # 레거시 키도 함께 두되, Step05에서 unknown 처리로직을 추가할 때 활용 가능
        out.update(
            {
                "status": "unknown",
                "menu_name": menu_norm,  # LLM이 이 텍스트를 보고 "메뉴인지/옵션인지/문구인지" 판별
                "evidence": {
                    "menu_id": None,
                    "ingredients": [],
                    "alg_tags": [],
                },
            }
        )

        return out