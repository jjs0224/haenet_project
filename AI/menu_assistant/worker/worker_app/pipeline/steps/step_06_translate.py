# menu_assistant/worker/worker_app/pipeline/steps/step_06_translate.py
from __future__ import annotations

import argparse
import hashlib
import json
import time
from pathlib import Path
from typing import Any, Dict, List, Tuple, Optional

from menu_assistant.worker.worker_app.llm.client import GeminiClientConfig
from menu_assistant.worker.worker_app.translate.model import GeminiTranslateClient
from menu_assistant.worker.worker_app.translate.prompt import (
    build_translate_prompts_for_final_item,
    build_translate_prompts_for_final_items_batch,
)
from menu_assistant.worker.worker_app.translate.schema import (
    validate_translate_output,
    validate_translate_batch_output,
)


# ============================================================
# Step06: Translate (FLAT STRICT MODE)
# - Input  : run_dir/final/final.json   (Step05 strict-flat output)
# - Output : run_dir/translate/translate.json
#            run_dir/final/final_translated.json
# ============================================================


def _load_json(path: Path) -> Any:
    if not path.exists():
        raise FileNotFoundError(f"[step06] JSON not found: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def _save_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")


def _infer_run_dir(data_dir: Path, run_id: str, run_dir: Optional[Path]) -> Path:
    return run_dir if run_dir is not None else (data_dir / "runs" / run_id)


def _infer_final_json_path(run_dir: Path, input_final: Optional[Path]) -> Path:
    if input_final is not None:
        return input_final
    p1 = run_dir / "final" / "final.json"
    if p1.exists():
        return p1
    p2 = run_dir / "final.json"
    if p2.exists():
        return p2
    return p1


def _extract_items(final_obj: Any) -> Tuple[List[Dict[str, Any]], Dict[str, Any], str]:
    if isinstance(final_obj, dict):
        if isinstance(final_obj.get("items"), list):
            return final_obj["items"], final_obj, "dict_items"
        raise ValueError("[step06] final.json is dict but missing 'items' list.")
    if isinstance(final_obj, list):
        wrapper = {"items": final_obj}
        return wrapper["items"], wrapper, "list"
    raise ValueError(f"[step06] Unsupported final.json type: {type(final_obj)}")


def _get_str(v: Any) -> str:
    if v is None:
        return ""
    if isinstance(v, str):
        return v.strip()
    if isinstance(v, list):
        parts = [str(x).strip() for x in v if str(x).strip()]
        return "\n".join(parts)
    return str(v).strip()


def _normalize_translation_output(obj: Any) -> Dict[str, Any]:
    """
    Accept either:
      A) strict output: {menu_description_en, risk_description_en, comment_en}
      B) legacy nested output: {menu{...}, risk{...}, comment{...}}
    Normalize to A.
    """
    if not isinstance(obj, dict):
        return {}

    if set(obj.keys()) in (
        {"menu_description_en", "risk_description_en", "comment_en"},
        {"menu_name_en", "menu_description_en", "risk_description_en", "comment_en"},
    ):
        return obj

    menu_en = ""
    risk_en = ""
    comment_en = ""

    m = obj.get("menu")
    if isinstance(m, dict):
        menu_en = _get_str(m.get("menu_description_en"))

    r = obj.get("risk")
    if isinstance(r, dict):
        risk_en = _get_str(r.get("risk_description_en"))

    c = obj.get("comment")
    if isinstance(c, dict):
        comment_en = _get_str(c.get("comment_en"))
    elif isinstance(obj.get("comment"), str):
        comment_en = _get_str(obj.get("comment"))

    return {
        "menu_name_en": _get_str(obj.get("menu_name_en")),
        "menu_description_en": menu_en,
        "risk_description_en": risk_en,
        "comment_en": comment_en,
    }


def _is_exact_item(it: Dict[str, Any]) -> bool:
    """EXACT 매칭 아이템 판별.

    Step05/Step04에 따라 형태가 달라질 수 있어 두 가지를 모두 허용한다.
      - strict-flat: it["match_status"] == "exact"
      - nested    : it["match"]["status"] == "exact"
    """
    try:
        if it.get("match_status") == "exact":
            return True
        m = it.get("match")
        return isinstance(m, dict) and (m.get("status") == "exact")
    except Exception:
        return False


def _build_translate_only_prompts(
    *,
    item: Dict[str, Any],
    include_menu_name: bool,
) -> Tuple[str, str]:
    """EXACT 전용: '재작성/요약' 금지, 순수 번역만.

    NOTE:
      - Step06에서 LLM을 완전히 배제할 수는 없지만(현재 client API 형태상),
        최소한 프롬프트로 "재작성"을 차단하고, KO 원문(특히 dataset description_ko)을
        절대 변경하지 않도록 한다.
    """
    # translate.prompt 모듈의 룰과 동일하게, 출력 키를 엄격히 제한
    output_schema = {
        "menu_description_en": "string",
        "risk_description_en": "string",
        "comment_en": "string",
    }
    if include_menu_name:
        output_schema["menu_name_en"] = "string"

    required_key_count = 4 if include_menu_name else 3
    required_keys_text = (
        "menu_name_en, menu_description_en, risk_description_en, comment_en"
        if include_menu_name
        else "menu_description_en, risk_description_en, comment_en"
    )

    system_prompt = (
        "You are a translation engine. Translate Korean to English.\n"
        "CRITICAL: TRANSLATION ONLY. Do NOT rewrite, summarize, paraphrase, or add safety warnings.\n"
        "Do NOT change meaning. Do NOT invent missing information.\n"
        "You MUST output ONLY valid JSON (no markdown, no code fences).\n"
        f"You MUST return a JSON object with EXACTLY {required_key_count} keys: {required_keys_text}.\n"
        "No extra keys allowed.\n"
    )

    src = {
        "menu_name_ko": _get_str(item.get("menu_name_ko")),
        "menu_description_ko": _get_str(item.get("menu_description_ko")),
        "risk_description_ko": _get_str(item.get("risk_description_ko")),
        "comment_ko": _get_str(item.get("comment_ko")),
    }
    user_payload = {
        "task": "Translate the Korean fields to English without rewriting.",
        "source": src,
        "output_schema": output_schema,
        "rules": [
            "TRANSLATE ONLY. Do NOT rewrite/summarize/paraphrase.",
            "Return ONLY JSON matching output_schema exactly.",
            "Do NOT include any other keys.",
            "If a source field is empty, output empty string.",
        ],
    }
    user_prompt = json.dumps(user_payload, ensure_ascii=False, indent=2)
    return system_prompt, user_prompt


def _translation_cache_key(
    *,
    model: str,
    include_menu_name: bool,
    item: Dict[str, Any],
    mode: str,
) -> str:
    """
    캐시 키는 "번역 입력"만으로 결정 (item_id, poly 등은 제외)
    """
    payload = {
        "model": model,
        "include_menu_name": bool(include_menu_name),
        "mode": str(mode),
        "menu_name_ko": _get_str(item.get("menu_name_ko")),
        "menu_description_ko": _get_str(item.get("menu_description_ko")),
        "risk_description_ko": _get_str(item.get("risk_description_ko")),
        "comment_ko": _get_str(item.get("comment_ko")),
    }
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _load_cache(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        obj = json.loads(path.read_text(encoding="utf-8"))
        return obj if isinstance(obj, dict) else {}
    except Exception:
        return {}


def _save_cache(path: Path, cache: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")


def _translate_single_with_retries(
    *,
    client: GeminiTranslateClient,
    item: Dict[str, Any],
    model_name: str,
    include_menu_name: bool,
    max_retries: int,
    sleep_base: float,
    cache: Dict[str, Any],
) -> Dict[str, Any]:
    # 캐시 우선
    key = _translation_cache_key(model=model_name, include_menu_name=include_menu_name, item=item, mode="llm")
    cached = cache.get(key)
    if isinstance(cached, dict):
        out = _normalize_translation_output(cached)
        ok, _ = validate_translate_output(out, require_menu_name_en=include_menu_name)
        if ok:
            return out

    last_err: Optional[Exception] = None
    for attempt in range(max_retries + 1):
        try:
            system_p, user_p = build_translate_prompts_for_final_item(item, include_menu_name=include_menu_name)
            out = client.translate_final_item(item=item, system_prompt=system_p, user_prompt=user_p)
            out = _normalize_translation_output(out)

            ok, msg = validate_translate_output(out, require_menu_name_en=include_menu_name)
            if not ok:
                raise ValueError(f"[step06] Invalid translation output: {msg}")

            # HARD CHECK: KO가 있는데 EN이 비면 실패로 처리
            if _get_str(item.get("menu_description_ko")) and not _get_str(out.get("menu_description_en")):
                raise ValueError("[step06] empty menu_description_en while menu_description_ko exists")
            if _get_str(item.get("risk_description_ko")) and not _get_str(out.get("risk_description_en")):
                raise ValueError("[step06] empty risk_description_en while risk_description_ko exists")
            if _get_str(item.get("comment_ko")) and not _get_str(out.get("comment_en")):
                raise ValueError("[step06] empty comment_en while comment_ko exists")

            cache[key] = out
            return out

        except Exception as e:
            last_err = e
            if attempt >= max_retries:
                break
            time.sleep(sleep_base * (attempt + 1))

    raise RuntimeError(f"[step06] Translation failed after retries: {last_err}") from last_err


def _translate_exact_translate_only_with_retries(
    *,
    client: GeminiTranslateClient,
    item: Dict[str, Any],
    model_name: str,
    include_menu_name: bool,
    max_retries: int,
    sleep_base: float,
    cache: Dict[str, Any],
) -> Dict[str, Any]:
    """EXACT 아이템 전용: '번역만' 수행.

    - LLM을 호출하더라도, 프롬프트로 재작성/요약/경고문 생성 등을 금지
    - KO 원문 필드는 절대 수정하지 않음 (Step06에서 it["*_ko"]를 변경하지 않게 유지)
    """
    key = _translation_cache_key(model=model_name, include_menu_name=include_menu_name, item=item, mode="exact")
    cached = cache.get(key)
    if isinstance(cached, dict):
        out = _normalize_translation_output(cached)
        ok, _ = validate_translate_output(out, require_menu_name_en=include_menu_name)
        if ok:
            return out

    last_err: Optional[Exception] = None
    for attempt in range(max_retries + 1):
        try:
            system_p, user_p = _build_translate_only_prompts(item=item, include_menu_name=include_menu_name)
            out = client.translate_final_item(item=item, system_prompt=system_p, user_prompt=user_p)
            out = _normalize_translation_output(out)

            ok, msg = validate_translate_output(out, require_menu_name_en=include_menu_name)
            if not ok:
                raise ValueError(f"[step06] Invalid translation output (exact): {msg}")

            # HARD CHECK: KO가 있는데 EN이 비면 실패로 처리
            if _get_str(item.get("menu_description_ko")) and not _get_str(out.get("menu_description_en")):
                raise ValueError("[step06] empty menu_description_en while menu_description_ko exists")
            if _get_str(item.get("risk_description_ko")) and not _get_str(out.get("risk_description_en")):
                raise ValueError("[step06] empty risk_description_en while risk_description_ko exists")
            if _get_str(item.get("comment_ko")) and not _get_str(out.get("comment_en")):
                raise ValueError("[step06] empty comment_en while comment_ko exists")

            cache[key] = out
            return out
        except Exception as e:
            last_err = e
            if attempt >= max_retries:
                break
            time.sleep(sleep_base * (attempt + 1))

    raise RuntimeError(f"[step06] Exact translate-only failed after retries: {last_err}") from last_err


def _translate_batch_with_retries(
    *,
    client: GeminiTranslateClient,
    items: List[Dict[str, Any]],
    model_name: str,
    include_menu_name: bool,
    max_retries: int,
    sleep_base: float,
) -> Any:
    last_err: Optional[Exception] = None
    for attempt in range(max_retries + 1):
        try:
            system_p, user_p = build_translate_prompts_for_final_items_batch(items, include_menu_name=include_menu_name)
            out = client.translate_final_items_batch_json(system_prompt=system_p, user_prompt=user_p)

            ok, msg = validate_translate_batch_output(
                out,
                expected_len=len(items),
                require_menu_name_en=include_menu_name,
            )
            if not ok:
                raise ValueError(f"[step06] Invalid batch translation output: {msg}")

            return out
        except Exception as e:
            last_err = e
            if attempt >= max_retries:
                break
            time.sleep(sleep_base * (attempt + 1))

    raise RuntimeError(f"[step06] Batch translation failed after retries: {last_err}") from last_err


def _extract_batch_items(out: Any) -> List[Dict[str, Any]]:
    if isinstance(out, dict) and isinstance(out.get("items"), list):
        return out["items"]
    if isinstance(out, list):
        return out
    return []


def main() -> None:
    parser = argparse.ArgumentParser(description="Step06: Translate final.json fields (STRICT-FLAT)")

    parser.add_argument("--run_id", type=str, default=None)
    parser.add_argument("--data_dir", type=str, default="menu_assistant/data")
    parser.add_argument("--run_dir", type=str, default=None)
    parser.add_argument("--input_final", type=str, default=None)

    parser.add_argument("--model", type=str, default="gemini-2.5-flash")
    parser.add_argument("--api_key_env", type=str, default="GEMINI_API_KEY")
    parser.add_argument("--temperature", type=float, default=0.2)
    parser.add_argument("--top_p", type=float, default=0.95)
    parser.add_argument("--top_k", type=int, default=40)

    parser.add_argument("--dotenv_path", type=str, default=None)
    parser.add_argument("--max_dotenv_up", type=int, default=8)

    parser.add_argument("--max_retries", type=int, default=2)
    parser.add_argument("--sleep_base", type=float, default=0.7)

    parser.add_argument(
        "--translate_menu_name",
        action="store_true",
        help="If set, translate menu_name_ko -> menu_name_en in Step6 (overrides Step5).",
    )
    parser.add_argument(
        "--force_menu_name_en",
        action="store_true",
        help="If set, re-translate menu_name_en even if it already exists (requires --translate_menu_name).",
    )

    # ✅ 성능 옵션
    parser.add_argument(
        "--batch_size",
        type=int,
        default=1,
        help="If >1, translate items in batches to reduce API calls.",
    )
    parser.add_argument(
        "--use_cache",
        action="store_true",
        help="If set, enable translation cache under run_dir/translate/translate_cache.json",
    )
    parser.add_argument(
        "--force_translate_all",
        action="store_true",
        help="If set, translate even if *_en already exists (cache still applies).",
    )
    # Orchestrator compatibility flags (accepted for CLI compatibility, unused here).
    parser.add_argument("--parallel_singles", action="store_true")
    parser.add_argument("--max_workers", type=int, default=4)

    args = parser.parse_args()

    data_dir = Path(args.data_dir)
    if args.run_id is None and args.run_dir is None:
        raise SystemExit("[step06] Either --run_id or --run_dir must be provided.")

    run_dir = _infer_run_dir(data_dir, args.run_id or "", Path(args.run_dir) if args.run_dir else None)
    final_path = _infer_final_json_path(run_dir, Path(args.input_final) if args.input_final else None)

    print("[RUN] step_06_translate (STRICT-FLAT)")
    print(f"[RUN] run_dir    = {run_dir}")
    print(f"[RUN] final.json = {final_path}")

    final_obj = _load_json(final_path)
    items, container, _mode = _extract_items(final_obj)

    cfg = GeminiClientConfig(
        model=args.model,
        api_key_env=args.api_key_env,
        temperature=float(args.temperature),
        top_p=float(args.top_p),
        top_k=int(args.top_k),
        response_mime_type="application/json",
    )
    client = GeminiTranslateClient(
        cfg,
        dotenv_path=args.dotenv_path,
        max_dotenv_up=int(args.max_dotenv_up),
    )

    cache_path = run_dir / "translate" / "translate_cache.json"
    cache: Dict[str, Any] = _load_cache(cache_path) if args.use_cache else {}

    translated_rows: List[Dict[str, Any]] = []
    merged_items: List[Dict[str, Any]] = []

    # --- normalize inputs / compute per-item include_menu flag ---
    for idx, it in enumerate(items):
        if not isinstance(it, dict):
            raise ValueError(f"[step06] items[{idx}] is not an object/dict.")
        if it.get("item_id") is None:
            raise ValueError(f"[step06] items[{idx}] missing item_id.")

        it["menu_description_ko"] = _get_str(it.get("menu_description_ko"))
        it["risk_description_ko"] = _get_str(it.get("risk_description_ko"))
        it["comment_ko"] = _get_str(it.get("comment_ko"))
        it["menu_name_ko"] = _get_str(it.get("menu_name_ko"))
        it["menu_name_en"] = _get_str(it.get("menu_name_en"))

        need_menu = False
        if args.translate_menu_name:
            if args.force_menu_name_en:
                need_menu = bool(it["menu_name_ko"])
            else:
                need_menu = bool(it["menu_name_ko"]) and (not it["menu_name_en"])
        else:
            need_menu = bool(it["menu_name_ko"]) and (not it["menu_name_en"])

        it["_need_menu_name_en"] = need_menu

    # --- translate ---
    bs = max(1, int(args.batch_size))
    idx = 0
    while idx < len(items):
        chunk = items[idx : idx + bs]

        # chunk 내에서 menu_name_en 필요가 하나라도 있으면 batch에 포함
        include_menu_name = any(bool(x.get("_need_menu_name_en")) for x in chunk)

        # ✅ 스킵 조건(이미 en이 있고 force_translate_all 아니면)
        def _needs_translation_llm(it: Dict[str, Any]) -> bool:
            # 🔒 EXACT는 LLM(일반 프롬프트) 경로 금지
            if _is_exact_item(it):
                return False
            if args.force_translate_all:
                return True
            has_menu_en = bool(_get_str(it.get("menu_description_en")))
            has_risk_en = bool(_get_str(it.get("risk_description_en")))
            has_comment_en = bool(_get_str(it.get("comment_en")))
            if include_menu_name and bool(it.get("_need_menu_name_en")):
                has_name_en = bool(_get_str(it.get("menu_name_en")))
                return not (has_menu_en and has_risk_en and has_comment_en and has_name_en)
            return not (has_menu_en and has_risk_en and has_comment_en)

        def _needs_translation_exact_only(it: Dict[str, Any]) -> bool:
            # EXACT는 '번역만' 경로로 처리
            if not _is_exact_item(it):
                return False
            if args.force_translate_all:
                return True
            has_menu_en = bool(_get_str(it.get("menu_description_en")))
            has_risk_en = bool(_get_str(it.get("risk_description_en")))
            has_comment_en = bool(_get_str(it.get("comment_en")))
            if include_menu_name and bool(it.get("_need_menu_name_en")):
                has_name_en = bool(_get_str(it.get("menu_name_en")))
                return not (has_menu_en and has_risk_en and has_comment_en and has_name_en)
            return not (has_menu_en and has_risk_en and has_comment_en)

        # 실제로 번역이 필요한 item만 따로 모음
        need_items_llm = [it for it in chunk if _needs_translation_llm(it)]
        need_items_exact = [it for it in chunk if _needs_translation_exact_only(it)]

        t0 = time.time()

        # 1) EXACT: translate-only (항상 개별 처리)
        for it in need_items_exact:
            translated = _translate_exact_translate_only_with_retries(
                client=client,
                item=it,
                model_name=args.model,
                include_menu_name=bool(it.get("_need_menu_name_en")),
                max_retries=int(args.max_retries),
                sleep_base=float(args.sleep_base),
                cache=cache,
            )
            it["menu_description_en"] = _get_str(translated.get("menu_description_en"))
            it["risk_description_en"] = _get_str(translated.get("risk_description_en"))
            it["comment_en"] = _get_str(translated.get("comment_en"))
            if bool(it.get("_need_menu_name_en")):
                it["menu_name_en"] = _get_str(translated.get("menu_name_en"))

        # 2) NON-EXACT: 기존 LLM 로직 유지
        if bs > 1 and len(need_items_llm) > 0:
            # ✅ Batch path (필요한 것만 배치로 보냄)
            try:
                out_any = _translate_batch_with_retries(
                    client=client,
                    items=need_items_llm,
                    model_name=args.model,
                    include_menu_name=include_menu_name,
                    max_retries=int(args.max_retries),
                    sleep_base=float(args.sleep_base),
                )
                out_list = _extract_batch_items(out_any)

                # 캐시 저장 + 결과 반영(need_items와 동일 순서 가정)
                for it, translated in zip(need_items_llm, out_list):
                    translated = _normalize_translation_output(translated)

                    # HARD CHECK
                    if _get_str(it.get("menu_description_ko")) and not _get_str(translated.get("menu_description_en")):
                        raise ValueError("[step06] empty menu_description_en while menu_description_ko exists")
                    if _get_str(it.get("risk_description_ko")) and not _get_str(translated.get("risk_description_en")):
                        raise ValueError("[step06] empty risk_description_en while risk_description_ko exists")
                    if _get_str(it.get("comment_ko")) and not _get_str(translated.get("comment_en")):
                        raise ValueError("[step06] empty comment_en while comment_ko exists")

                    # write EN to root only
                    it["menu_description_en"] = _get_str(translated.get("menu_description_en"))
                    it["risk_description_en"] = _get_str(translated.get("risk_description_en"))
                    it["comment_en"] = _get_str(translated.get("comment_en"))

                    if bool(it.get("_need_menu_name_en")):
                        it["menu_name_en"] = _get_str(translated.get("menu_name_en"))

                    if args.use_cache:
                        key = _translation_cache_key(
                            model=args.model,
                            include_menu_name=include_menu_name,
                            item=it,
                            mode="llm",
                        )
                        cache[key] = translated

            except Exception as e:
                # ✅ 안전 폴백: 배치 실패 시 기존 1개씩 번역
                print(
                    f"[WARN] batch failed (idx={idx} size={len(need_items_llm)}). fallback to single. err={e}"
                )
                for it in need_items_llm:
                    translated = _translate_single_with_retries(
                        client=client,
                        item=it,
                        model_name=args.model,
                        include_menu_name=bool(it.get("_need_menu_name_en")),
                        max_retries=int(args.max_retries),
                        sleep_base=float(args.sleep_base),
                        cache=cache,
                    )
                    it["menu_description_en"] = _get_str(translated.get("menu_description_en"))
                    it["risk_description_en"] = _get_str(translated.get("risk_description_en"))
                    it["comment_en"] = _get_str(translated.get("comment_en"))
                    if bool(it.get("_need_menu_name_en")):
                        it["menu_name_en"] = _get_str(translated.get("menu_name_en"))
        else:
            # ✅ Single path (or bs==1)
            for it in need_items_llm:
                translated = _translate_single_with_retries(
                    client=client,
                    item=it,
                    model_name=args.model,
                    include_menu_name=bool(it.get("_need_menu_name_en")),
                    max_retries=int(args.max_retries),
                    sleep_base=float(args.sleep_base),
                    cache=cache,
                )
                it["menu_description_en"] = _get_str(translated.get("menu_description_en"))
                it["risk_description_en"] = _get_str(translated.get("risk_description_en"))
                it["comment_en"] = _get_str(translated.get("comment_en"))
                if bool(it.get("_need_menu_name_en")):
                    it["menu_name_en"] = _get_str(translated.get("menu_name_en"))

        dt = time.time() - t0
        print(
            f"[BATCH] idx={idx:04d} size={len(chunk)} exact_need={len(need_items_exact)} llm_need={len(need_items_llm)} "
            f"batch_size={bs} took={dt:.2f}s"
        )

        # translate.json rows + cleanup flag
        for it in chunk:
            translated_rows.append(
                {
                    "item_id": it.get("item_id"),
                    "menu_name_en": it.get("menu_name_en"),
                    "menu_description_en": _get_str(it.get("menu_description_en")),
                    "risk_description_en": _get_str(it.get("risk_description_en")),
                    "comment_en": _get_str(it.get("comment_en")),
                }
            )
            it.pop("_need_menu_name_en", None)
            merged_items.append(it)

        idx += bs

    if args.use_cache:
        _save_cache(cache_path, cache)

    _save_json(run_dir / "translate" / "translate.json", {"items": translated_rows})
    container["items"] = merged_items
    _save_json(run_dir / "final" / "final_translated.json", container)

    print(f"[DONE] translate.json        = {run_dir / 'translate' / 'translate.json'}")
    print(f"[DONE] final_translated.json = {run_dir / 'final' / 'final_translated.json'}")
    if args.use_cache:
        print(f"[DONE] translate_cache.json  = {cache_path}")


if __name__ == "__main__":
    main()
