# menu_assistant/worker/worker_app/pipeline/steps/step_06_translate.py
from __future__ import annotations

import argparse
import hashlib
import json
import time
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Dict, List, Tuple, Optional

from menu_assistant.worker.worker_app.llm.client import GeminiClientConfig
from menu_assistant.worker.worker_app.translate.model import GeminiTranslateClient


# -----------------------------
# IO utils
# -----------------------------
def _load_json(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _save_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)


def _infer_run_dir(data_dir: Path, run_id: str, run_dir: Optional[Path]) -> Path:
    if run_dir is not None:
        return run_dir
    if not run_id:
        raise ValueError("[step06] run_id is empty and run_dir is None")
    return data_dir / "runs" / run_id


def _infer_final_json_path(run_dir: Path, input_final: Optional[Path]) -> Path:
    if input_final is not None:
        return input_final
    return run_dir / "final" / "final.json"


def _extract_items(final_obj: Dict[str, Any]) -> Tuple[List[Dict[str, Any]], Dict[str, Any], str]:
    if isinstance(final_obj, dict) and isinstance(final_obj.get("items"), list):
        return final_obj["items"], final_obj, "root_items"
    raise ValueError("[step06] Could not find items[] in final.json")


def _get_str(x: Any) -> str:
    if x is None:
        return ""
    if isinstance(x, str):
        return x.strip()
    if isinstance(x, list):
        parts = [str(v).strip() for v in x if str(v).strip()]
        return "\n".join(parts)
    return str(x).strip()


# -----------------------------
# PARTIAL translation helpers (token-optimized)
# -----------------------------
_KO_SRC_BY_EN = {
    "menu_name_en": "menu_name_ko",
    "menu_description_en": "menu_description_ko",
    "risk_description_en": "risk_description_ko",
    "comment_en": "comment_ko",
}


def _needed_en_keys(
    it: Dict[str, Any],
    *,
    translate_menu_name: bool,
    force_menu_name_en: bool,
    force_translate_all: bool,
) -> List[str]:
    # Decide if menu_name_en can be requested
    need_menu_name = False
    if translate_menu_name:
        if force_menu_name_en:
            need_menu_name = bool(_get_str(it.get("menu_name_ko")))
        else:
            need_menu_name = bool(_get_str(it.get("menu_name_ko"))) and (not _get_str(it.get("menu_name_en")))
    else:
        need_menu_name = bool(_get_str(it.get("menu_name_ko"))) and (not _get_str(it.get("menu_name_en")))

    keys: List[str] = ["menu_description_en", "risk_description_en", "comment_en"]
    if need_menu_name:
        keys = ["menu_name_en"] + keys

    need: List[str] = []
    for k in keys:
        ko_k = _KO_SRC_BY_EN.get(k)
        if ko_k and not _get_str(it.get(ko_k)):
            it[k] = ""  # source empty => keep empty
            continue

        if force_translate_all:
            need.append(k)
        else:
            if not _get_str(it.get(k)):
                need.append(k)
    return need


def _build_partial_translate_prompts_single(
    *,
    item: Dict[str, Any],
    needed_keys: List[str],
) -> Tuple[str, str]:
    # include ONLY the required Korean source fields
    src: Dict[str, str] = {}
    for en_k in needed_keys:
        ko_k = _KO_SRC_BY_EN.get(en_k)
        if ko_k:
            src[ko_k] = _get_str(item.get(ko_k))

    system_prompt = (
        "You are a translation engine. Translate Korean to English.\n"
        "TRANSLATION ONLY (no rewriting/summarizing). No invented info.\n"
        "Return ONLY valid JSON.\n"
        f"Return a JSON object with EXACTLY these keys: {', '.join(needed_keys)}.\n"
        "No extra keys.\n"
    )

    user_payload = {"needed_keys": needed_keys, "source": src}
    return system_prompt, json.dumps(user_payload, ensure_ascii=False, separators=(",", ":"))


def _build_partial_translate_prompts_batch(
    *,
    items: List[Dict[str, Any]],
    needed_keys: List[str],
) -> Tuple[str, str]:
    sources: List[Dict[str, str]] = []
    for it in items:
        row: Dict[str, str] = {}
        for en_k in needed_keys:
            ko_k = _KO_SRC_BY_EN.get(en_k)
            if ko_k:
                row[ko_k] = _get_str(it.get(ko_k))
        sources.append(row)

    system_prompt = (
        "You are a translation engine. Translate Korean to English.\n"
        "TRANSLATION ONLY (no rewriting/summarizing). No invented info.\n"
        "Return ONLY valid JSON.\n"
        "Return an object with key 'items' as a list.\n"
        f"Each items[i] MUST be a JSON object with EXACTLY these keys: {', '.join(needed_keys)}.\n"
        "No extra keys anywhere. Preserve order.\n"
    )

    user_payload = {
        "needed_keys": needed_keys,
        "sources": sources,
        "return": {"items": [{k: "string" for k in needed_keys}]},
    }
    return system_prompt, json.dumps(user_payload, ensure_ascii=False, separators=(",", ":"))


def _validate_partial_output(obj: Any, needed_keys: List[str]) -> Tuple[bool, str]:
    if not isinstance(obj, dict):
        return False, "output must be object"
    if set(obj.keys()) != set(needed_keys):
        return False, f"keys mismatch. expected={sorted(needed_keys)} got={sorted(list(obj.keys()))}"
    for k in needed_keys:
        if not isinstance(obj.get(k), str):
            return False, f"field '{k}' must be string"
    return True, "OK"


def _extract_batch_items(obj: Any, expected_len: int) -> List[Dict[str, Any]]:
    if isinstance(obj, dict) and isinstance(obj.get("items"), list):
        out = obj["items"]
    elif isinstance(obj, list):
        out = obj
    else:
        raise ValueError("[step06] batch output must be list or {'items': list}")

    if len(out) != expected_len:
        raise ValueError(f"[step06] batch output length mismatch. expected={expected_len} got={len(out)}")

    cleaned: List[Dict[str, Any]] = []
    for i, it in enumerate(out):
        if not isinstance(it, dict):
            raise ValueError(f"[step06] batch items[{i}] must be object")
        cleaned.append(it)
    return cleaned


# -----------------------------
# Cache (thread-safe)
# -----------------------------
def _translation_cache_key(
    *,
    model: str,
    item: Dict[str, Any],
    mode: str,
    needed_keys: List[str],
) -> str:
    payload: Dict[str, Any] = {"model": str(model), "mode": str(mode), "needed_keys": list(needed_keys)}
    for en_k in needed_keys:
        ko_k = _KO_SRC_BY_EN.get(en_k)
        if ko_k:
            payload[ko_k] = _get_str(item.get(ko_k))
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _load_cache(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        with path.open("r", encoding="utf-8") as f:
            obj = json.load(f)
        return obj if isinstance(obj, dict) else {}
    except Exception:
        return {}


def _save_cache(path: Path, cache: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)


def _cache_get(cache: Dict[str, Any], lock: threading.Lock, key: str) -> Any:
    with lock:
        return cache.get(key)


def _cache_set(cache: Dict[str, Any], lock: threading.Lock, key: str, value: Any) -> None:
    with lock:
        cache[key] = value


# -----------------------------
# Translation execution
# -----------------------------
def _translate_partial_single_with_retries(
    *,
    client: GeminiTranslateClient,
    item: Dict[str, Any],
    model_name: str,
    needed_keys: List[str],
    max_retries: int,
    sleep_base: float,
    cache: Dict[str, Any],
    cache_lock: threading.Lock,
    include_debug: bool,
    debug_dir: Path,
    debug_prefix: str,
) -> Dict[str, Any]:
    key = _translation_cache_key(model=model_name, item=item, mode="single", needed_keys=needed_keys)

    cached = _cache_get(cache, cache_lock, key)
    if isinstance(cached, dict):
        ok, _ = _validate_partial_output(cached, needed_keys)
        if ok:
            return cached

    last_err: Optional[Exception] = None
    for attempt in range(max_retries + 1):
        try:
            system_p, user_p = _build_partial_translate_prompts_single(item=item, needed_keys=needed_keys)

            if include_debug:
                (debug_dir / "translate").mkdir(parents=True, exist_ok=True)
                _save_json(
                    debug_dir / "translate" / f"{debug_prefix}.prompt.{attempt}.json",
                    {"system": system_p, "user": user_p, "needed_keys": needed_keys},
                )

            out = client.generate_json(system=system_p, user=user_p)

            if include_debug:
                _save_json(debug_dir / "translate" / f"{debug_prefix}.raw.{attempt}.json", out)

            ok, msg = _validate_partial_output(out, needed_keys)
            if not ok:
                raise ValueError(f"invalid partial output: {msg}")

            out_clean = {k: _get_str(out.get(k)) for k in needed_keys}
            _cache_set(cache, cache_lock, key, out_clean)
            return out_clean
        except Exception as e:
            last_err = e
            if attempt >= max_retries:
                break
            time.sleep(sleep_base * (attempt + 1))

    raise RuntimeError(f"[step06] partial single failed after retries: {last_err}") from last_err


def _translate_partial_batch_with_retries(
    *,
    client: GeminiTranslateClient,
    items: List[Dict[str, Any]],
    model_name: str,
    needed_keys: List[str],
    max_retries: int,
    sleep_base: float,
    cache: Dict[str, Any],
    cache_lock: threading.Lock,
    include_debug: bool,
    debug_dir: Path,
    debug_prefix: str,
) -> List[Dict[str, Any]]:
    out_list: List[Optional[Dict[str, Any]]] = [None] * len(items)
    pending: List[Tuple[int, Dict[str, Any]]] = []

    for i, it in enumerate(items):
        key = _translation_cache_key(model=model_name, item=it, mode="batch", needed_keys=needed_keys)
        cached = _cache_get(cache, cache_lock, key)
        if isinstance(cached, dict):
            ok, _ = _validate_partial_output(cached, needed_keys)
            if ok:
                out_list[i] = cached
                continue
        pending.append((i, it))

    if not pending:
        return [x or {k: "" for k in needed_keys} for x in out_list]

    last_err: Optional[Exception] = None
    for attempt in range(max_retries + 1):
        try:
            pend_items = [it for _, it in pending]
            system_p, user_p = _build_partial_translate_prompts_batch(items=pend_items, needed_keys=needed_keys)

            if include_debug:
                (debug_dir / "translate").mkdir(parents=True, exist_ok=True)
                _save_json(
                    debug_dir / "translate" / f"{debug_prefix}.batch.prompt.{attempt}.json",
                    {"system": system_p, "user": user_p, "needed_keys": needed_keys, "count": len(pend_items)},
                )

            out_any = client.translate_final_items_batch_json(system_prompt=system_p, user_prompt=user_p)

            if include_debug:
                _save_json(debug_dir / "translate" / f"{debug_prefix}.batch.raw.{attempt}.json", out_any)

            rows = _extract_batch_items(out_any, expected_len=len(pend_items))

            cleaned_rows: List[Dict[str, Any]] = []
            for j, row in enumerate(rows):
                ok, msg = _validate_partial_output(row, needed_keys)
                if not ok:
                    raise ValueError(f"batch row[{j}] invalid: {msg}")
                cleaned_rows.append({k: _get_str(row.get(k)) for k in needed_keys})

            for (orig_idx, it), row_clean in zip(pending, cleaned_rows):
                out_list[orig_idx] = row_clean
                key = _translation_cache_key(model=model_name, item=it, mode="batch", needed_keys=needed_keys)
                _cache_set(cache, cache_lock, key, row_clean)

            return [x or {k: "" for k in needed_keys} for x in out_list]
        except Exception as e:
            last_err = e
            if attempt >= max_retries:
                break
            time.sleep(sleep_base * (attempt + 1))

    raise RuntimeError(f"[step06] partial batch failed after retries: {last_err}") from last_err


# -----------------------------
# main (parallel singles)
# -----------------------------
def main() -> None:
    parser = argparse.ArgumentParser(description="Step06: Translate final.json fields (PARTIAL, OPT, PARALLEL)")

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

    parser.add_argument("--translate_menu_name", action="store_true")
    parser.add_argument("--force_menu_name_en", action="store_true")

    parser.add_argument("--batch_size", type=int, default=16)
    parser.add_argument("--use_cache", action="store_true")
    parser.add_argument("--force_translate_all", action="store_true")

    parser.add_argument("--include_debug", action="store_true")

    # ✅ parallelism
    parser.add_argument("--max_workers", type=int, default=4, help="Thread workers for single-item translations.")
    parser.add_argument(
        "--parallel_singles",
        action="store_true",
        help="If set, single-item translations inside groups run in parallel (recommended).",
    )

    args = parser.parse_args()

    data_dir = Path(args.data_dir)
    if args.run_id is None and args.run_dir is None:
        raise SystemExit("[step06] Either --run_id or --run_dir must be provided.")

    run_dir = _infer_run_dir(data_dir, args.run_id or "", Path(args.run_dir) if args.run_dir else None)
    final_path = _infer_final_json_path(run_dir, Path(args.input_final) if args.input_final else None)

    print("[RUN] step_06_translate (PARTIAL, OPT, PARALLEL)")
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
    client = GeminiTranslateClient(cfg, dotenv_path=args.dotenv_path, max_dotenv_up=int(args.max_dotenv_up))

    cache_path = run_dir / "translate" / "translate_cache.json"
    cache: Dict[str, Any] = _load_cache(cache_path) if args.use_cache else {}
    cache_lock = threading.Lock()

    # normalize fields
    for idx, it in enumerate(items):
        if not isinstance(it, dict):
            raise ValueError(f"[step06] items[{idx}] is not a dict")
        if it.get("item_id") is None:
            raise ValueError(f"[step06] items[{idx}] missing item_id")

        it["menu_name_ko"] = _get_str(it.get("menu_name_ko"))
        it["menu_description_ko"] = _get_str(it.get("menu_description_ko"))
        it["risk_description_ko"] = _get_str(it.get("risk_description_ko"))
        it["comment_ko"] = _get_str(it.get("comment_ko"))

        it["menu_name_en"] = _get_str(it.get("menu_name_en"))
        it["menu_description_en"] = _get_str(it.get("menu_description_en"))
        it["risk_description_en"] = _get_str(it.get("risk_description_en"))
        it["comment_en"] = _get_str(it.get("comment_en"))

    # Group by needed_keys to maximize batching
    groups: Dict[str, List[Dict[str, Any]]] = {}
    total_need = 0
    for it in items:
        needed = _needed_en_keys(
            it,
            translate_menu_name=bool(args.translate_menu_name),
            force_menu_name_en=bool(args.force_menu_name_en),
            force_translate_all=bool(args.force_translate_all),
        )
        if not needed:
            continue
        total_need += 1
        key = "|".join(sorted(needed))
        it["_needed_keys"] = needed
        groups.setdefault(key, []).append(it)

    bs = max(1, int(args.batch_size))
    max_workers = max(1, int(args.max_workers))
    parallel_singles = bool(args.parallel_singles) and max_workers > 1

    print(
        f"[PLAN] total_items={len(items)} need_translate={total_need} groups={len(groups)} "
        f"batch_size={bs} parallel_singles={parallel_singles} max_workers={max_workers}"
    )

    t_all = time.time()

    for gk, gitems in groups.items():
        needed_keys = gitems[0].get("_needed_keys") or []
        if not needed_keys:
            continue

        t0 = time.time()

        # 1) run batch translations first (sub-batches with len>=2)
        # 2) accumulate single-item translations and run in parallel (if enabled)
        single_tasks: List[Dict[str, Any]] = []

        # slice into sub-batches
        for start in range(0, len(gitems), bs):
            sub = gitems[start : start + bs]
            if len(sub) >= 2:
                outs = _translate_partial_batch_with_retries(
                    client=client,
                    items=sub,
                    model_name=args.model,
                    needed_keys=needed_keys,
                    max_retries=int(args.max_retries),
                    sleep_base=float(args.sleep_base),
                    cache=cache,
                    cache_lock=cache_lock,
                    include_debug=bool(args.include_debug),
                    debug_dir=run_dir,
                    debug_prefix=f"group.{gk}.b{start:04d}",
                )
                for it, out in zip(sub, outs):
                    for k in needed_keys:
                        it[k] = _get_str(out.get(k))
            else:
                single_tasks.extend(sub)

        # run singles
        if single_tasks:
            if parallel_singles:
                futures = []
                with ThreadPoolExecutor(max_workers=max_workers) as ex:
                    for it in single_tasks:
                        item_id = _get_str(it.get("item_id"))
                        futures.append(
                            ex.submit(
                                _translate_partial_single_with_retries,
                                client=client,
                                item=it,
                                model_name=args.model,
                                needed_keys=needed_keys,
                                max_retries=int(args.max_retries),
                                sleep_base=float(args.sleep_base),
                                cache=cache,
                                cache_lock=cache_lock,
                                include_debug=bool(args.include_debug),
                                debug_dir=run_dir,
                                debug_prefix=f"group.{gk}.item.{item_id}",
                            )
                        )

                    for fut, it in zip(futures, single_tasks):
                        out = fut.result()
                        for k in needed_keys:
                            it[k] = _get_str(out.get(k))
            else:
                for it in single_tasks:
                    item_id = _get_str(it.get("item_id"))
                    out = _translate_partial_single_with_retries(
                        client=client,
                        item=it,
                        model_name=args.model,
                        needed_keys=needed_keys,
                        max_retries=int(args.max_retries),
                        sleep_base=float(args.sleep_base),
                        cache=cache,
                        cache_lock=cache_lock,
                        include_debug=bool(args.include_debug),
                        debug_dir=run_dir,
                        debug_prefix=f"group.{gk}.item.{item_id}",
                    )
                    for k in needed_keys:
                        it[k] = _get_str(out.get(k))

        dt = time.time() - t0
        print(f"[GROUP] keys={gk} count={len(gitems)} singles={len(single_tasks)} took={dt:.2f}s")

    dt_all = time.time() - t_all
    print(f"[DONE] translate time: {dt_all:.2f}s")

    # cleanup + write outputs
    translated_rows: List[Dict[str, Any]] = []
    for it in items:
        translated_rows.append(
            {
                "item_id": it.get("item_id"),
                "menu_name_en": _get_str(it.get("menu_name_en")),
                "menu_description_en": _get_str(it.get("menu_description_en")),
                "risk_description_en": _get_str(it.get("risk_description_en")),
                "comment_en": _get_str(it.get("comment_en")),
            }
        )
        it.pop("_needed_keys", None)

    if args.use_cache:
        _save_cache(cache_path, cache)

    _save_json(run_dir / "translate" / "translate.json", {"items": translated_rows})
    container["items"] = items
    _save_json(run_dir / "final" / "final_translated.json", container)
    print(f"[DONE] wrote: {run_dir / 'final' / 'final_translated.json'}")


if __name__ == "__main__":
    main()
