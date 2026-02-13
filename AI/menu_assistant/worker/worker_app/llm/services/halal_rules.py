# menu_assistant/worker/worker_app/llm/services/halal_rules.py
from __future__ import annotations

from typing import Any, Dict, List, Optional
import re


# ----------------------------
# Canonical religion mapping
# ----------------------------

def normalize_religion(value: Any) -> Optional[str]:
    """
    Normalize religion field into canonical string.
    Accepts: None | str | list[str] | etc.
    Returns: None | 'islam_halal' | trimmed original string
    """
    if value is None:
        return None

    # list -> first non-empty string
    if isinstance(value, list):
        for x in value:
            if isinstance(x, str) and x.strip():
                value = x.strip()
                break
        else:
            return None

    if not isinstance(value, str):
        value = str(value).strip()

    s = value.strip().lower()
    if not s:
        return None

    # canonicalize muslim/islam/halal
    if "islam" in s or "muslim" in s or "halal" in s:
        return "islam_halal"

    return value.strip()


def is_islam_religion(value: Any) -> bool:
    return normalize_religion(value) == "islam_halal"


def normalize_user_profile(user_profile: Dict[str, Any]) -> Dict[str, Any]:
    """
    Ensure user_profile has stable types:
    - allergy_tags: list
    - avoid_foods : list
    - religion    : canonical string or None
    """
    up = dict(user_profile or {})
    at = up.get("allergy_tags")
    af = up.get("avoid_foods")

    if at is None:
        at = []
    if af is None:
        af = []
    if not isinstance(at, list):
        at = [at]
    if not isinstance(af, list):
        af = [af]

    up["allergy_tags"] = at
    up["avoid_foods"] = af
    up["religion"] = normalize_religion(up.get("religion"))
    return up


# ----------------------------
# Haram keyword detection
# ----------------------------

# ✅ KO/EN 키워드 (필요하면 여기에 계속 추가)
HARAM_KO = [
    # Pork & pork products
    "돼지", "돼지고기", "삼겹살", "목살", "항정살", "갈비", "족발", "보쌈",
    "베이컨", "햄", "소시지", "순대", "돈까스", "제육", "돼지주물럭",
    "라드", "돈지",

    # Alcohol
    "알코올", "술", "맥주", "소주", "막걸리", "청주", "약주", "와인", "사케",
    "위스키", "보드카", "럼", "브랜디", "리큐르", "칵테일",
    "맛술", "미림", "요리술",
]

HARAM_EN = [
    "pork", "bacon", "ham", "sausage", "lard", "gelatin",
    "alcohol", "beer", "wine", "soju", "whisky", "whiskey", "vodka", "gin", "rum", "brandy", "sake",
    "cooking wine", "cookingwine",
]

# 플래그 매핑(DecisionRules의 religion_hit로 쓰기 좋게)
FLAG_RULES = [
    ("ALCOHOL_SUSPECT",
     ["알코올", "술", "맥주", "소주", "막걸리", "와인", "사케", "위스키", "보드카", "럼", "브랜디", "맛술", "미림", "요리술"],
     ["alcohol", "beer", "wine", "soju", "whisky", "whiskey", "vodka", "gin", "rum", "brandy", "sake", "cookingwine", "cooking wine"]),
    ("PORK_SUSPECT",
     ["돼지", "돼지고기", "삼겹살", "족발", "보쌈", "베이컨", "햄", "소시지", "순대", "제육", "돼지주물럭"],
     ["pork", "bacon", "ham", "sausage", "pepperoni", "salami"]),
    ("LARD_SUSPECT",
     ["라드", "돈지"],
     ["lard", "shortening"]),
]


def _norm_blob(s: str) -> str:
    """
    Robust text normalization for keyword contains checks:
    - lower
    - remove whitespace
    - remove common punctuation
    """
    s = (s or "").strip().lower()
    s = re.sub(r"\s+", "", s)
    s = re.sub(r"[·•\-\(\)\[\]\{\}\/\\\.,:;\"'`~!?@#$%^&*_+=|<>]", "", s)
    return s


def haram_flags_from_text(text: str) -> List[str]:
    """
    Returns list of flags like ['ALCOHOL_SUSPECT', 'PORK_SUSPECT'].
    """
    blob = _norm_blob(text)
    out: List[str] = []

    for flag, ko_keys, en_keys in FLAG_RULES:
        hit = False
        for k in ko_keys:
            if _norm_blob(k) and _norm_blob(k) in blob:
                hit = True
                break
        if not hit:
            for k in en_keys:
                if _norm_blob(k) and _norm_blob(k) in blob:
                    hit = True
                    break
        if hit:
            out.append(flag)

    return out
