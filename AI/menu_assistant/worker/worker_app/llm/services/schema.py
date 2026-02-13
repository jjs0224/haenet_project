# menu_assistant/worker/worker_app/llm/services/schema.py
# ✅ Add patch-output validator (minimal keys) while keeping existing v1 validator intact.

from __future__ import annotations

from typing import Any, Dict, List, Tuple
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class FinalItemV1:
    item_id: str
    match_status: str            # "exact" | "unknown"
    menu_name_ko: str
    menu_name_en: str
    poly: List[List[float]] = field(default_factory=list)

    menu_description_ko: str = ""
    menu_description_en: str = ""

    risk_description_ko: str = ""
    risk_description_en: str = ""

    risk_difficulty: int = 3
    user_risk_match: Dict[str, Any] = field(default_factory=dict)

    comment_ko: str = ""
    comment_en: str = ""

    # unknown에서만 의미
    is_menu: Optional[str] = None
    drop_reason_ko: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        d = {
            "item_id": self.item_id,
            "match_status": self.match_status,
            "menu_name_ko": self.menu_name_ko,
            "menu_name_en": self.menu_name_en,
            "poly": self.poly,
            "menu_description_ko": self.menu_description_ko,
            "menu_description_en": self.menu_description_en,
            "risk_description_ko": self.risk_description_ko,
            "risk_description_en": self.risk_description_en,
            "risk_difficulty": int(self.risk_difficulty),
            "user_risk_match": self.user_risk_match,
            "comment_ko": self.comment_ko,
            "comment_en": self.comment_en,
        }
        if self.is_menu is not None:
            d["is_menu"] = self.is_menu
        if self.drop_reason_ko is not None:
            d["drop_reason_ko"] = self.drop_reason_ko
        return d

    @staticmethod
    def _as_str(x: Any) -> str:
        if x is None:
            return ""
        if isinstance(x, str):
            return x.strip()
        if isinstance(x, list):
            parts = [str(v).strip() for v in x if str(v).strip()]
            return "\n".join(parts)
        return str(x).strip()

    @staticmethod
    def _as_poly(x: Any) -> List[List[float]]:
        if not isinstance(x, list):
            return []
        out: List[List[float]] = []
        for pt in x:
            if isinstance(pt, (list, tuple)) and len(pt) >= 2:
                try:
                    out.append([float(pt[0]), float(pt[1])])
                except Exception:
                    pass
        return out

    @classmethod
    def from_dict(cls, obj: Dict[str, Any]) -> "FinalItemV1":
        if not isinstance(obj, dict):
            raise TypeError("FinalItemV1.from_dict expects dict")

        item_id = cls._as_str(obj.get("item_id"))
        if not item_id:
            raise ValueError("FinalItemV1: missing item_id")

        ms = cls._as_str(obj.get("match_status"))
        if ms not in ("exact", "unknown"):
            ms = "unknown"

        is_menu = obj.get("is_menu")
        if isinstance(is_menu, str):
            is_menu = is_menu.strip().lower()
        else:
            is_menu = None

        drop_reason_ko = cls._as_str(obj.get("drop_reason_ko")) or None

        rd = obj.get("risk_difficulty")
        try:
            rd_int = int(rd)
        except Exception:
            rd_int = 3
        if rd_int not in (0, 1, 2, 3):
            rd_int = 3

        urm = obj.get("user_risk_match")
        if not isinstance(urm, dict):
            urm = {}

        return cls(
            item_id=item_id,
            match_status=ms,
            menu_name_ko=cls._as_str(obj.get("menu_name_ko")),
            menu_name_en=cls._as_str(obj.get("menu_name_en")),
            poly=cls._as_poly(obj.get("poly")),
            menu_description_ko=cls._as_str(obj.get("menu_description_ko")),
            menu_description_en=cls._as_str(obj.get("menu_description_en")),
            risk_description_ko=cls._as_str(obj.get("risk_description_ko")),
            risk_description_en=cls._as_str(obj.get("risk_description_en")),
            risk_difficulty=rd_int,
            user_risk_match=urm,
            comment_ko=cls._as_str(obj.get("comment_ko")),
            comment_en=cls._as_str(obj.get("comment_en")),
            is_menu=is_menu,
            drop_reason_ko=drop_reason_ko,
        )


@dataclass
class FinalOutputV1:
    schema_version: str
    run_id: str
    user_profile: Dict[str, Any]
    items: List[FinalItemV1]
    dropped_items: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "run_id": self.run_id,
            "user_profile": self.user_profile,
            "items": [it.to_dict() for it in self.items],
            "dropped_items": self.dropped_items,
        }



def _is_non_empty_str(x: Any) -> bool:
    return isinstance(x, str) and x.strip() != ""


def _is_str_or_none(x: Any) -> bool:
    return x is None or isinstance(x, str)


def validate_llm_patch_output_v1(obj: Any) -> Tuple[bool, str]:
    """
    Validate Step05 PATCH-OUTPUT MINIMAL schema.

    Root:
      - schema_version (non-empty str)
      - run_id (non-empty str)
      - items (list)

    Each item REQUIRED:
      - item_id (non-empty str)
      - match_status == "unknown"
      - is_menu in {"yes","no"}
      - menu_description_ko (str, non-empty if is_menu=="yes")
      - risk_description_ko (str, non-empty if is_menu=="yes")
      - comment_ko (str, non-empty if is_menu=="yes")
      - user_risk_match (dict with required keys)
    Conditional:
      - if is_menu == "no": drop_reason_ko must be non-empty str
    Optional:
      - menu_name_ko (str)
      - drop_reason_ko (str|None)
    """
    if not isinstance(obj, dict):
        return False, "Root must be a JSON object"

    for k in ("schema_version", "run_id", "items"):
        if k not in obj:
            return False, f"Missing required root key: {k}"

    if not _is_non_empty_str(obj.get("schema_version")):
        return False, "schema_version must be a non-empty string"
    if not _is_non_empty_str(obj.get("run_id")):
        return False, "run_id must be a non-empty string"

    items = obj.get("items")
    if not isinstance(items, list):
        return False, "items must be a list"

    for i, it in enumerate(items):
        if not isinstance(it, dict):
            return False, f"items[{i}] must be an object"

        # required keys
        for k in ("item_id", "match_status", "is_menu", "menu_description_ko", "risk_description_ko", "comment_ko", "user_risk_match"):
            if k not in it:
                return False, f"items[{i}] missing required key: {k}"

        if not _is_non_empty_str(it.get("item_id")):
            return False, f"items[{i}].item_id must be non-empty string"

        if it.get("match_status") != "unknown":
            return False, f"items[{i}].match_status must be 'unknown'"

        is_menu = it.get("is_menu")
        if is_menu not in ("yes", "no"):
            return False, f"items[{i}].is_menu must be 'yes'|'no'"

        # optional menu_name_ko
        if "menu_name_ko" in it and it.get("menu_name_ko") is not None and not isinstance(it.get("menu_name_ko"), str):
            return False, f"items[{i}].menu_name_ko must be string or null if present"

        # drop reason rule
        if is_menu == "no":
            dr = it.get("drop_reason_ko")
            if not _is_non_empty_str(dr):
                return False, f"items[{i}].drop_reason_ko required when is_menu=='no'"

        # for menu=yes, require non-empty texts
        if is_menu == "yes":
            for k in ("menu_description_ko", "risk_description_ko", "comment_ko"):
                if not _is_non_empty_str(it.get(k)):
                    return False, f"items[{i}].{k} must be non-empty string when is_menu=='yes'"

        # user_risk_match structure
        urm = it.get("user_risk_match")
        if not isinstance(urm, dict):
            return False, f"items[{i}].user_risk_match must be object"
        for k in ("allergy_tag_hits", "religion_hit", "avoid_food_hits", "has_any_match", "source"):
            if k not in urm:
                return False, f"items[{i}].user_risk_match missing key: {k}"
        if urm.get("source") != "unknown":
            return False, f"items[{i}].user_risk_match.source must be 'unknown'"

        # types
        if urm.get("allergy_tag_hits") is not None and not isinstance(urm.get("allergy_tag_hits"), list):
            return False, f"items[{i}].user_risk_match.allergy_tag_hits must be list or null"
        if urm.get("avoid_food_hits") is not None and not isinstance(urm.get("avoid_food_hits"), list):
            return False, f"items[{i}].user_risk_match.avoid_food_hits must be list or null"
        if not _is_str_or_none(urm.get("religion_hit")):
            return False, f"items[{i}].user_risk_match.religion_hit must be string or null"
        if not isinstance(urm.get("has_any_match"), bool):
            return False, f"items[{i}].user_risk_match.has_any_match must be boolean"

    return True, "OK"


def validate_llm_patch_output_against_input_ids(obj: Any, expected_item_ids: List[str]) -> Tuple[bool, str]:
    ok, msg = validate_llm_patch_output_v1(obj)
    if not ok:
        return ok, msg

    out_ids: List[str] = []
    for it in obj.get("items", []):
        if isinstance(it, dict) and isinstance(it.get("item_id"), str):
            out_ids.append(it["item_id"].strip())

    exp = [x.strip() for x in expected_item_ids if isinstance(x, str) and x.strip()]
    if sorted(out_ids) != sorted(exp):
        return False, f"LLM patch output item_ids mismatch. expected={exp} got={out_ids}"

    if len(set(out_ids)) != len(out_ids):
        return False, "LLM patch output has duplicated item_id"

    return True, "OK"
