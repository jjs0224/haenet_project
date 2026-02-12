# menu_assistant/worker/worker_app/translate/model.py
from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from menu_assistant.worker.worker_app.llm.client import (
    Gemini25FlashClient,
    GeminiClientConfig,
)


class GeminiTranslateClient:
    """
    Step6 Translation wrapper
    - .env / API key 로딩은 translate/client.py(Gemini25FlashClient)에 전적으로 위임
    - 여기서는 "프롬프트 전달 -> JSON 파싱 -> final item 번역 결과 스키마 정리"만 담당
    """

    def __init__(
        self,
        cfg: Optional[GeminiClientConfig] = None,
        dotenv_path: Optional[str] = None,
        max_dotenv_up: int = 8,
    ) -> None:
        self.cfg = cfg or GeminiClientConfig()
        self._client = Gemini25FlashClient(
            config=self.cfg,
            dotenv_path=dotenv_path,
            max_dotenv_up=max_dotenv_up,
        )

    @staticmethod
    def _strip_code_fence(s: str) -> str:
        t = (s or "").strip()
        if t.startswith("```"):
            t = t.split("\n", 1)[-1]
            if t.endswith("```"):
                t = t.rsplit("```", 1)[0]
        return t.strip()

    def generate_json(self, *, system: str, user: str) -> Any:
        text = self._client.generate_json(system=system, user=user)
        if not text:
            raise RuntimeError("[translate/model] Empty response from Gemini.")
        cleaned = self._strip_code_fence(text)
        try:
            return json.loads(cleaned)
        except Exception as e:
            raise RuntimeError(
                "[translate/model] Failed to parse JSON from Gemini.\n"
                f"Raw: {text[:1000]}\n"
                f"Cleaned: {cleaned[:1000]}\n"
                f"Error: {e}"
            )

    @staticmethod
    def extract_required_fields_from_final_item(item: Dict[str, Any]) -> Dict[str, Any]:
        if not isinstance(item, dict):
            raise ValueError("[translate/model] final item must be a dict.")

        item_id = item.get("item_id")
        if item_id is None:
            raise ValueError("[translate/model] item_id is missing in final item.")

        match = item.get("match")
        if not isinstance(match, dict):
            match = {}

        menu = item.get("menu") if isinstance(item.get("menu"), dict) else {}
        risk = item.get("risk") if isinstance(item.get("risk"), dict) else {}

        menu_description_ko = (item.get("menu_description_ko") or menu.get("menu_description_ko") or "").strip()
        risk_description_ko = (item.get("risk_description_ko") or risk.get("risk_description_ko") or "").strip()

        comment_ko = (item.get("comment_ko") or "").strip()
        if not comment_ko:
            staff_list = risk.get("staff_comment_ko") or []
            if isinstance(staff_list, list):
                comment_ko = "\n".join([str(x).strip() for x in staff_list if str(x).strip()])
        if not comment_ko:
            comment_ko = (risk.get("comment") or "").strip()

        return {
            "item_id": item_id,
            "match": match,
            "menu_description_ko": menu_description_ko,
            "risk_description_ko": risk_description_ko,
            "comment_ko": comment_ko,
        }

    def translate_final_item(
        self,
        *,
        item: Dict[str, Any],
        system_prompt: str,
        user_prompt: str,
    ) -> Dict[str, Any]:
        _ = self.extract_required_fields_from_final_item(item)  # 안전 체크(구조 보장)
        out = self.generate_json(system=system_prompt, user=user_prompt)

        if isinstance(out, dict) and set(out.keys()) in (
            {"menu_description_en", "risk_description_en", "comment_en"},
            {"menu_name_en", "menu_description_en", "risk_description_en", "comment_en"},
        ):
            return {
                "menu_name_en": (out.get("menu_name_en") or "").strip(),
                "menu_description_en": (out.get("menu_description_en") or "").strip(),
                "risk_description_en": (out.get("risk_description_en") or "").strip(),
                "comment_en": (out.get("comment_en") or "").strip(),
            }

        menu_out = out.get("menu", {}) if isinstance(out, dict) else {}
        risk_out = out.get("risk", {}) if isinstance(out, dict) else {}
        comment_out = out.get("comment", {}) if isinstance(out, dict) else {}

        return {
            "menu_description_en": (menu_out.get("menu_description_en") or "").strip(),
            "risk_description_en": (risk_out.get("risk_description_en") or "").strip(),
            "comment_en": (comment_out.get("comment_en") or "").strip(),
        }

    def translate_final_items_batch_json(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
    ) -> Any:
        """
        Batch translation low-level:
        returns parsed JSON (list OR {"items": [...]})
        """
        return self.generate_json(system=system_prompt, user=user_prompt)
