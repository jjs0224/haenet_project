import re
from typing import Dict, Optional
from AI.review.app.pipeline.step_4_enrich_data.translate_menu import translate_to_en
from AI.review.app.pipeline.step_4_enrich_data.naverApi_search import find_store_by_query
from AI.review.app.pipeline.step_4_enrich_data.search_store_candidate import extract_store_name_candidates

def enrich_data(
    *,
    phone: Optional[str],
    lines: list[str],
    menu_ko: list[str],
    naver_cfg: Dict,
    gemini_api_key: str,
) -> Dict:
    store = None

    client_id = (naver_cfg or {}).get("NAVER_CLIENT_ID")
    client_secret = (naver_cfg or {}).get("NAVER_CLIENT_SECRET")

    # 1) phone search
    if phone:
        store = find_store_by_query(phone, client_id=client_id, client_secret=client_secret)

    # 2) name + address token search
    MAX_TRIES = 4  # 여기서 요청 상한

    if store is None:
        cands = extract_store_name_candidates(lines, top_k=10, max_candidates=5)

        tries = 0
        for cand in cands:
            query = cand.strip()
            if not query:
                continue

            # 요청 상한
            if tries >= MAX_TRIES:
                break

            # 네 기존 find_store_by_query 호출
            store = find_store_by_query(
                query,
                client_id=client_id,
                client_secret=client_secret,
            )
            tries += 1

            if store is not None:
                break

    # translate
    texts_to_translate = []
    if store:
        texts_to_translate.append(store["name_ko"])
    texts_to_translate.extend(menu_ko)

    translations = translate_to_en(texts_to_translate, api_key=gemini_api_key)

    return {
        "store": {
            **store,
            "name_en": translations.get(store["name_ko"]) if store else None,
        } if store else None,
        "menu": [{"name_ko": m, "name_en": translations.get(m)} for m in menu_ko],
    }
