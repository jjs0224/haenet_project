# C:\Users\201\Desktop\PGHfolder\haenet\AI\menu_assistant\worker\worker_app\pipeline\steps\step_05_risk_score.py
"""
Step 05 (Runner):
- Input : <data_dir>/runs/<run_id>/rag_match/rag_match.json
- Output:
    <run_dir>/llm/llm_input.json
    <run_dir>/llm/llm_input_meta.json
    <run_dir>/llm/llm_prompt*.txt              (optional debug)
    <run_dir>/llm/llm_raw*.txt                 (optional debug)
    <run_dir>/llm/llm_output.json             (validated JSON)  # merged across chunks if enabled
    <run_dir>/final/final.json                ✅ NEW: finalizer merge 결과

Speed patch (옵션):
- --chunk_size N   : items를 N개씩 쪼개 LLM 호출 (대형 프롬프트 지연/실패 감소)
- --workers K      : chunk 병렬 실행(제한 병렬, 기본 1)
- --use_cache      : chunk 입력 해시 기반 캐시 사용
"""

from __future__ import annotations

import argparse
import hashlib
import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


def _read_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        f.write(text or "")


def _resolve_run_dir(data_dir: Path, run_id: str) -> Path:
    return data_dir / "runs" / run_id


# -------------------------
# Cache helpers (chunk-level)
# -------------------------

def _sha256_json(obj: Any) -> str:
    raw = json.dumps(obj, ensure_ascii=False, sort_keys=True).encode("utf-8")
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


# -------------------------
# user profile minimalizer (same as your current)
# -------------------------

def _profile_categories_to_minimal(obj: Dict[str, Any]) -> Dict[str, Any]:
    categories = obj.get("categories")
    if not isinstance(categories, list):
        return {}

    allergy_tags_set: set[str] = set()
    avoid_foods_set: set[str] = set()
    religion: Any = None

    KO_LABEL_MAP = {
        "알러지": "allergy",
        "알레르기": "allergy",
        "종교": "religion",
        "싫어하는 음식": "dislike",
        "기피": "dislike",
        "비건": "vegan",
        "채식": "vegan",
    }

    def _norm_str(x: Any) -> str:
        if not isinstance(x, str):
            return ""
        return x.strip()

    def _add_values(dst: set[str], values: Any) -> None:
        if not values:
            return
        if isinstance(values, str):
            v = values.strip()
            if v:
                dst.add(v)
            return
        if isinstance(values, list):
            for x in values:
                if isinstance(x, str):
                    v = x.strip()
                    if v:
                        dst.add(v)

    for cat in categories:
        if not isinstance(cat, dict):
            continue

        label_en = _norm_str(cat.get("category_label_en")).lower()
        if not label_en:
            label_ko = _norm_str(cat.get("category_label_ko"))
            label_en = KO_LABEL_MAP.get(label_ko, "")
        items = cat.get("items")
        if not isinstance(items, list):
            continue

        if label_en == "allergy":
            for it in items:
                if not isinstance(it, dict):
                    continue
                _add_values(allergy_tags_set, it.get("alg_tags"))
                ile = it.get("item_label_en")
                if isinstance(ile, str) and ile.strip().upper().startswith("ALG_"):
                    allergy_tags_set.add(ile.strip().upper())
                _add_values(avoid_foods_set, it.get("blocked_ingredients_ko"))

        elif label_en == "religion":
            if religion is None and items:
                first = items[0]
                if isinstance(first, dict):
                    religion = first.get("item_label_en") or first.get("item_label_ko") or None
                    if isinstance(religion, str):
                        religion = religion.strip() or None
            for it in items:
                if not isinstance(it, dict):
                    continue
                _add_values(avoid_foods_set, it.get("blocked_ingredients_ko"))

        elif label_en in ("dislike", "vegan"):
            for it in items:
                if not isinstance(it, dict):
                    continue
                _add_values(avoid_foods_set, it.get("blocked_ingredients_ko"))

    return {
        "allergy_tags": sorted(allergy_tags_set),
        "avoid_foods": sorted(avoid_foods_set),
        "religion": religion,
    }


def _load_user_profile(user_profile_json: str) -> Dict[str, Any]:
    if not user_profile_json:
        return {"allergy_tags": [], "avoid_foods": [], "religion": None}

    p = Path(user_profile_json)
    if not p.exists():
        raise FileNotFoundError(f"user_profile_json not found: {p}")
    obj = _read_json(p)
    if not isinstance(obj, dict):
        raise ValueError("user_profile_json must be a JSON object (dict).")

    for wrap_key in ("user_profile", "profile", "data"):
        if isinstance(obj.get(wrap_key), dict):
            obj = obj[wrap_key]
            break

    if any(k in obj for k in ("allergy_tags", "avoid_foods", "religion")):
        obj.setdefault("allergy_tags", [])
        obj.setdefault("avoid_foods", [])
        obj.setdefault("religion", None)
        return obj

    converted = _profile_categories_to_minimal(obj)
    if isinstance(converted, dict) and set(converted.keys()) >= {"allergy_tags", "avoid_foods", "religion"}:
        return converted

    return {"allergy_tags": [], "avoid_foods": [], "religion": None}


# -------------------------
# normalize items (same as your current)
# -------------------------

def _normalize_llm_input_items(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    def _pick_status(it: Dict[str, Any]) -> str:
        s4 = it.get("match_status")
        if isinstance(s4, str) and s4.strip():
            return s4.strip()
        s = it.get("status")
        if isinstance(s, str) and s.strip():
            return s.strip()
        m = it.get("match")
        if isinstance(m, dict):
            s2 = m.get("status")
            if isinstance(s2, str) and s2.strip():
                return s2.strip()
        rm = it.get("rag_match")
        if isinstance(rm, dict):
            s3 = rm.get("status")
            if isinstance(s3, str) and s3.strip():
                return s3.strip()
        return ""

    def _pick_menu_name(it: Dict[str, Any], status: str) -> str:
        for k in ("menu_name", "menu"):
            v = it.get(k)
            if isinstance(v, str) and v.strip():
                return v.strip()
        for k in ("decided_menu", "menu_final", "raw_menu_main", "raw_menu", "menu_norm"):
            v = it.get(k)
            if isinstance(v, str) and v.strip():
                return v.strip()
        m = it.get("match")
        if isinstance(m, dict):
            for k in ("decided_menu", "menu", "menu_name"):
                v = m.get(k)
                if isinstance(v, str) and v.strip():
                    return v.strip()
        rm = it.get("rag_match")
        if isinstance(rm, dict):
            for k in ("decided_menu", "used_query"):
                v = rm.get(k)
                if isinstance(v, str) and v.strip():
                    return v.strip()
        return ""

    def _pick_poly(it: Dict[str, Any]) -> Any:
        p = it.get("poly")
        if p is not None:
            return p
        p2 = it.get("poly_menu")
        if p2 is not None:
            return p2
        m = it.get("match")
        if isinstance(m, dict) and m.get("poly") is not None:
            return m.get("poly")
        rm = it.get("rag_match")
        if isinstance(rm, dict) and rm.get("poly") is not None:
            return rm.get("poly")
        return None

    def _pick_evidence(it: Dict[str, Any]) -> Dict[str, Any]:
        ev = it.get("evidence")
        out = dict(ev) if isinstance(ev, dict) else {}

        if "menu_id" not in out:
            mid = it.get("menu_id")
            if mid is not None:
                out["menu_id"] = mid

        if "ingredients" not in out:
            ing = it.get("ingredients")
            if isinstance(ing, list):
                out["ingredients"] = ing

        if "alg_tags" not in out:
            tags = it.get("alg_tags")
            if isinstance(tags, list):
                out["alg_tags"] = tags

        rm = it.get("rag_match")
        if isinstance(rm, dict):
            bm = rm.get("best_match")
            if isinstance(bm, dict):
                if "menu_id" not in out and bm.get("id") is not None:
                    out["menu_id"] = bm.get("id")
                if "ingredients" not in out and isinstance(bm.get("ingredients"), list):
                    out["ingredients"] = bm.get("ingredients")
                if "alg_tags" not in out and isinstance(bm.get("alg_tags"), list):
                    out["alg_tags"] = bm.get("alg_tags")

        return out


    def _pick_menu_description_ko(it: Dict[str, Any]) -> str:
        # Keep dataset/confirmed description if available (exact should not degrade)
        # Priority: explicit carried field -> confirmed -> evidence
        for k in ("menu_description_ko", "menu_description"):
            v = it.get(k)
            if isinstance(v, str) and v.strip():
                return v.strip()

        c = it.get("confirmed")
        if isinstance(c, dict):
            for k in ("menu_description_ko", "menu_description"):
                v = c.get(k)
                if isinstance(v, str) and v.strip():
                    return v.strip()

        ev = it.get("evidence")
        if isinstance(ev, dict):
            for k in ("menu_description_ko", "menu_description"):
                v = ev.get(k)
                if isinstance(v, str) and v.strip():
                    return v.strip()

        rm = it.get("rag_match")
        if isinstance(rm, dict):
            bm = rm.get("best_match")
            if isinstance(bm, dict):
                for k in ("menu_description_ko", "menu_description"):
                    v = bm.get(k)
                    if isinstance(v, str) and v.strip():
                        return v.strip()

        return ""

    out: List[Dict[str, Any]] = []
    for it in items:
        if not isinstance(it, dict):
            continue

        item_id = it.get("item_id")
        if not isinstance(item_id, str) or not item_id.strip():
            continue

        status = _pick_status(it)
        menu_name = _pick_menu_name(it, status)
        poly = _pick_poly(it)
        evidence = _pick_evidence(it)
        menu_description_ko = _pick_menu_description_ko(it)

        if not menu_name or poly is None:
            continue

        # ✅ carry risk_difficulty computed by decision_rules (exact items may skip LLM)
        rd_raw = it.get("risk_difficulty")
        risk_difficulty = None
        try:
            if isinstance(rd_raw, bool):
                risk_difficulty = None
            elif isinstance(rd_raw, (int, float)):
                risk_difficulty = int(rd_raw)
            elif isinstance(rd_raw, str) and rd_raw.strip():
                risk_difficulty = int(rd_raw.strip())
        except Exception:
            risk_difficulty = None

        out.append(
            {
                "item_id": item_id.strip(),
                "status": status or "unknown",
                "menu_name": menu_name,
                "menu_description_ko": menu_description_ko,
                "poly": poly,
                "evidence": evidence,
                "risk_difficulty": risk_difficulty,
                "user_risk_match": it.get("user_risk_match") if isinstance(it.get("user_risk_match"), dict) else None,
                "comment_ko": it.get("comment_ko") if isinstance(it.get("comment_ko"), list) else None,
                "confirmed": it.get("confirmed") if isinstance(it.get("confirmed"), dict) else None,
            }
        )

    return out


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Step05: LLM menu explain + safety (Gemini-2.5-flash)")
    p.add_argument("--run_id", required=True, help="Run id under <data_dir>/runs/<run_id>/...")
    p.add_argument(
        "--data_dir",
        required=True,
        help=r"Base data directory (e.g. C:\Users\201\Desktop\PGHfolder\haenet\AI\menu_assistant\data)",
    )
    p.add_argument(
        "--run_dir",
        default="",
        help="Optional run directory override (e.g. uploads/tmp/.../ai_runs/<run_id>). "
             "If provided, Step05 reads/writes under this directory.",
    )
    p.add_argument("--user_profile_json", default="", help="Optional: path to user profile JSON")
    p.add_argument("--include_debug", action="store_true", help="Save prompt/raw snapshots")
    p.add_argument("--max_retries", type=int, default=2, help="Max retries when schema validation fails")
    p.add_argument("--require_poly", action="store_true", help="Require poly for all kept items (recommended)")
    p.add_argument("--no_require_poly", action="store_true", help="Do not require poly (debug only)")

    # ✅ speed patch options (defaults keep original behavior)
    p.add_argument("--chunk_size", type=int, default=0, help="If >0, split items into chunks of this size.")
    p.add_argument("--workers", type=int, default=1, help="Parallel workers for chunk calls (<=4 recommended).")
    p.add_argument("--use_cache", action="store_true", help="Enable chunk-level cache under run_dir/llm/llm_cache.json")

    return p.parse_args()


def _call_llm_for_chunk(
    *,
    run_id: str,
    user_profile: Dict[str, Any],
    items_chunk: List[Dict[str, Any]],
    llm_dir: Path,
    include_debug: bool,
    max_retries: int,
    chunk_index: int,
    cache: Optional[Dict[str, Any]],
    cache_key: Optional[str],
) -> Dict[str, Any]:
    """
    One chunk -> prompt -> LLM call -> parse/validate -> returns schema-compliant obj
    """
    # cache hit
    if cache is not None and cache_key and isinstance(cache.get(cache_key), dict):
        return cache[cache_key]

    from menu_assistant.worker.worker_app.llm.prompt_builder import build_step05_prompt
    from menu_assistant.worker.worker_app.llm.client import Gemini25FlashClient
    from menu_assistant.worker.worker_app.llm.parsers import (
        parse_and_validate_llm_output,
        build_retry_prompt_from_error,
        LLMParseError,
    )
    from menu_assistant.worker.worker_app.llm.services.schema import validate_llm_output_against_input_ids

    expected_ids = [it["item_id"] for it in items_chunk]

    prompt = build_step05_prompt(run_id=run_id, user_profile=user_profile, items=items_chunk)
    system_msg = prompt["system"]
    user_msg_base = prompt["user"]
    user_msg = user_msg_base

    client = Gemini25FlashClient()

    last_err: str = ""
    for attempt in range(max_retries + 1):
        if include_debug:
            _write_text(
                llm_dir / f"llm_prompt.chunk{chunk_index:03d}.txt",
                f"[SYSTEM]\n{system_msg}\n\n[USER]\n{user_msg}\n",
            )

        raw = client.generate_json(system=system_msg, user=user_msg)

        if include_debug:
            _write_text(llm_dir / f"llm_raw.chunk{chunk_index:03d}.txt", raw)

        try:
            obj = parse_and_validate_llm_output(raw)

            # fallback fill (same as your current logic)
            items_out = obj.get("items", []) or []
            for it in items_out:
                if not isinstance(it, dict):
                    continue
                if not str(it.get("menu_description_ko") or "").strip():
                    it["menu_description_ko"] = "메뉴 설명 정보가 제한적입니다. 주문 전 구성 재료를 확인하세요."
                if not str(it.get("risk_description_ko") or "").strip():
                    it["risk_description_ko"] = "사용자 알러지/종교/기피 식품과의 충돌 가능성이 있어 주문 전 재료 확인이 필요합니다."
                if not str(it.get("comment_ko") or "").strip():
                    it["comment_ko"] = "이 메뉴에 알러지 유발 성분이나 기피 식품이 포함되나요?"

            ok_ids, msg_ids = validate_llm_output_against_input_ids(obj, expected_ids)
            if not ok_ids:
                raise LLMParseError(msg_ids)

            # cache store
            if cache is not None and cache_key:
                cache[cache_key] = obj

            return obj

        except Exception as e:
            last_err = str(e)
            if attempt >= max_retries:
                break
            user_msg = user_msg_base + "\n\n" + build_retry_prompt_from_error(last_err)

    raise RuntimeError(f"[STEP05] chunk={chunk_index} invalid after retries. last_error={last_err}")


def main() -> None:
    args = parse_args()

    data_dir = Path(args.data_dir)
    run_dir = Path(args.run_dir) if str(args.run_dir or "").strip() else _resolve_run_dir(data_dir, args.run_id)
    llm_dir = run_dir / "llm"
    final_dir = run_dir / "final"
    final_json_path = final_dir / "final.json"

    rag_match_path = run_dir / "rag_match" / "rag_match.json"
    if not rag_match_path.exists():
        raise FileNotFoundError(f"rag_match.json not found: {rag_match_path}")

    rag_match_json = _read_json(rag_match_path)
    user_profile = _load_user_profile(args.user_profile_json)
    print("[DEBUG] loaded user_profile:", user_profile)

    # Decision rules -> minimal items
    from menu_assistant.worker.worker_app.llm.services.decision_rules import DecisionRules

    require_poly = True
    if args.no_require_poly:
        require_poly = False
    elif args.require_poly:
        require_poly = True

    rules = DecisionRules(require_poly=require_poly, user_profile=user_profile)
    raw_items, rules_meta = rules.build_llm_items(rag_match_json)
    print("[DEBUG] rules_meta:", rules_meta, "raw_items_len:", len(raw_items))

    # ✅ PATCH: bring confirmed.menu_description_ko back into raw_items (DecisionRules가 drop하는 케이스 대비)
    confirmed_by_id: Dict[str, Dict[str, Any]] = {}
    try:
        src_items = rag_match_json.get("items", [])
        if isinstance(src_items, list):
            for src in src_items:
                if not isinstance(src, dict):
                    continue
                iid = src.get("item_id")
                c = src.get("confirmed")
                if isinstance(iid, str) and iid.strip() and isinstance(c, dict):
                    confirmed_by_id[iid.strip()] = c
    except Exception:
        confirmed_by_id = {}

    for it in raw_items:
        if not isinstance(it, dict):
            continue
        iid = it.get("item_id")
        if not isinstance(iid, str) or not iid.strip():
            continue
        c = confirmed_by_id.get(iid.strip())
        if isinstance(c, dict):
            # raw_items에 confirmed를 다시 달아줌
            it["confirmed"] = c
            # 선택: pick 우선순위 1번(직접 필드)로도 넣어두면 더 안전
            if not str(it.get("menu_description_ko") or "").strip():
                it["menu_description_ko"] = str(c.get("menu_description_ko") or "").strip()

    llm_items = _normalize_llm_input_items(raw_items)

    # ✅ B안: exact는 LLM 스킵, unknown만 LLM 호출
    exact_items: List[Dict[str, Any]] = []
    unknown_items: List[Dict[str, Any]] = []
    for it in llm_items:
        s = (it.get("status") or "").lower().strip()
        if s == "unknown":
            unknown_items.append(it)
        else:
            exact_items.append(it)

    llm_input_payload = {
        "schema_version": "v1",
        "run_id": args.run_id,
        "user_profile": user_profile,
        "items": llm_items,
    }
    llm_input_meta = {
        "run_id": args.run_id,
        "decision_rules": rules_meta,
        "kept_for_llm_total": len(llm_items),
        "kept_for_llm_unknown_only": len(unknown_items),
        "kept_for_llm_exact_skipped": len(exact_items),
    }

    _write_json(llm_dir / "llm_input.json", llm_input_payload)
    _write_json(llm_dir / "llm_input_meta.json", llm_input_meta)

    if not unknown_items:
        print(f"[STEP05] No unknown items to send to LLM (exact skipped). saved: {llm_dir / 'llm_input.json'}")
        from menu_assistant.worker.worker_app.llm.services.finalizer import merge_llm_output_to_final

        final_obj = merge_llm_output_to_final(
            run_id=args.run_id,
            user_profile=user_profile,
            llm_input_items=llm_items,
            llm_output_items=[],
        )
        _write_json(final_json_path, final_obj)
        print(f"[STEP05] final.json        = {final_json_path}")
        return

    # -------------------------
    # ✅ chunk / parallel / cache
    # -------------------------

    # ✅ LLM 대상은 unknown만
    items_for_llm = unknown_items
    chunk_size = int(args.chunk_size) if int(args.chunk_size or 0) > 0 else 0
    workers = max(1, int(args.workers or 1))
    use_cache = bool(args.use_cache)

    cache_path = llm_dir / "llm_cache.json"
    cache: Optional[Dict[str, Any]] = _load_cache(cache_path) if use_cache else None

    if chunk_size <= 0:
        # ✅ original behavior: single call for all items
        obj = _call_llm_for_chunk(
            run_id=args.run_id,
            user_profile=user_profile,
            items_chunk=items_for_llm,
            llm_dir=llm_dir,
            include_debug=args.include_debug,
            max_retries=int(args.max_retries),
            chunk_index=0,
            cache=cache,
            cache_key=_sha256_json({"run_id": args.run_id, "user_profile": user_profile, "items": items_for_llm}),
        )
        merged_obj = obj

    else:
        # split into chunks
        chunks: List[List[Dict[str, Any]]] = [
            items_for_llm[i:i + chunk_size] for i in range(0, len(items_for_llm), chunk_size)
        ]

        t_all = time.time()

        def _submit_payload(ci: int, ch: List[Dict[str, Any]]) -> Tuple[int, str]:
            key = _sha256_json({"run_id": args.run_id, "user_profile": user_profile, "items": ch})
            return ci, key

        results_by_chunk: Dict[int, Dict[str, Any]] = {}

        if workers == 1:
            for ci, ch in enumerate(chunks):
                _, key = _submit_payload(ci, ch)
                t0 = time.time()
                out = _call_llm_for_chunk(
                    run_id=args.run_id,
                    user_profile=user_profile,
                    items_chunk=ch,
                    llm_dir=llm_dir,
                    include_debug=args.include_debug,
                    max_retries=int(args.max_retries),
                    chunk_index=ci,
                    cache=cache,
                    cache_key=key,
                )
                results_by_chunk[ci] = out
                print(f"[STEP05][CHUNK] {ci+1}/{len(chunks)} size={len(ch)} took={time.time()-t0:.2f}s")
        else:
            # limited parallel
            with ThreadPoolExecutor(max_workers=workers) as ex:
                futs = []
                for ci, ch in enumerate(chunks):
                    _, key = _submit_payload(ci, ch)
                    futs.append(
                        ex.submit(
                            _call_llm_for_chunk,
                            run_id=args.run_id,
                            user_profile=user_profile,
                            items_chunk=ch,
                            llm_dir=llm_dir,
                            include_debug=args.include_debug,
                            max_retries=int(args.max_retries),
                            chunk_index=ci,
                            cache=cache,
                            cache_key=key,
                        )
                    )
                for fut in as_completed(futs):
                    out = fut.result()
                    # chunk_index는 out에 없으므로, prompt/raw 파일 이름으로 추적하지 않고
                    # 여기서는 "아이디 셋"으로 chunk를 찾는다 (안전하고 단순)
                    out_ids = tuple(sorted([it.get("item_id") for it in (out.get("items") or []) if isinstance(it, dict)]))
                    # find matching chunk index
                    matched_ci = None
                    for ci, ch in enumerate(chunks):
                        ch_ids = tuple(sorted([it.get("item_id") for it in ch]))
                        if ch_ids == out_ids:
                            matched_ci = ci
                            break
                    if matched_ci is None:
                        raise RuntimeError("[STEP05] parallel chunk merge failed: cannot map chunk result to chunk index")
                    results_by_chunk[matched_ci] = out

            print(f"[STEP05] chunks={len(chunks)} workers={workers} total_took={time.time()-t_all:.2f}s")

        # merge chunk outputs -> one llm_output.json
        merged_items_out: List[Dict[str, Any]] = []
        for ci in range(len(chunks)):
            obj = results_by_chunk[ci]
            merged_items_out.extend(obj.get("items", []) or [])

        merged_obj = {
            "schema_version": "v1",
            "run_id": args.run_id,
            "items": merged_items_out,
        }

    # cache save
    if cache is not None:
        _save_cache(cache_path, cache)

    # ✅ save llm_output.json
    out_path = llm_dir / "llm_output.json"
    _write_json(out_path, merged_obj)

    # ✅ final.json merge
    from menu_assistant.worker.worker_app.llm.services.finalizer import merge_llm_output_to_final

    llm_output_items = merged_obj.get("items", []) or []
    final_obj = merge_llm_output_to_final(
        run_id=args.run_id,
        user_profile=user_profile,
        llm_input_items=llm_items,
        llm_output_items=llm_output_items,
    )
    _write_json(final_json_path, final_obj)

    print(f"[STEP05] run_id           = {args.run_id}")
    print(f"[STEP05] input            = {rag_match_path}")
    print(f"[STEP05] llm_input.json    = {llm_dir / 'llm_input.json'}")
    print(f"[STEP05] llm_output.json   = {out_path}")
    print(f"[STEP05] final.json        = {final_json_path}")
    print(f"[STEP05] items_out         = {len(llm_output_items)}")
    print(f"[STEP05] items_final       = {len(final_obj.get('items', []))}")
    print(f"[STEP05] dropped_items     = {len(final_obj.get('dropped_items', []))}")
    if args.use_cache:
        print(f"[STEP05] llm_cache.json    = {cache_path}")


if __name__ == "__main__":
    main()