from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List

from menu_assistant.worker.worker_app.rag.retrieval import match_menu_norm

# ============================================================
# Exact precheck (STRING EXACT) before embedding search
# - Optional and backward compatible
# - Enabled when --menu_index_json is provided OR env var
#   MENU_ASSISTANT_MENU_INDEX_JSON is set.
# - This prevents cases where an exact menu exists in the index
#   but is not retrieved by embedding top_k candidates.
# ============================================================
menu_index_json = "/tmp/menu_seed_with_alg_tags_variants_v3.json"
ENV_MENU_INDEX_S3_URI = "MENU_ASSISTANT_MENU_INDEX_S3_URI"


def _parse_s3_uri(uri: str) -> Tuple[str, str]:
    if not uri.startswith("s3://"):
        raise ValueError(f"invalid s3 uri: {uri}")
    parts = uri[5:].split("/", 1)
    bucket = parts[0]
    key = parts[1] if len(parts) > 1 else ""
    return bucket, key


def _download_s3_file(uri: str, dest: Path) -> None:
    import boto3

    bucket, key = _parse_s3_uri(uri)
    dest.parent.mkdir(parents=True, exist_ok=True)
    boto3.client("s3").download_file(bucket, key, str(dest))
def _load_menu_index_for_exact(path_str: Optional[str]) -> Optional[Dict[str, Dict[str, Any]]]:
    """Load a menu index json (list of entries) and build variant->record map.

    Expected entry schema (minimal):
      {
        "id": "rep_...",
        "menu": "냉모밀",
        "variants": ["냉모밀", "..."],
        "ingredients_ko": [...],
        "alg_tags": [...]
      }

    Returns:
      dict mapping variant string -> entry dict
    """
    # Priority: CLI arg > ENV
    p = (path_str or os.environ.get("MENU_ASSISTANT_MENU_INDEX_JSON") or '').strip()
    if not p:
        return None
    path = Path(p).expanduser()
    if not path.exists():
        s3_uri = os.environ.get(ENV_MENU_INDEX_S3_URI, "").strip()
        if s3_uri:
            try:
                _download_s3_file(s3_uri, path)
            except Exception as e:
                print(f"[WARN] failed to download menu_index_json from S3: {type(e).__name__}: {e}")
        if not path.exists():
            print(f"[WARN] menu_index_json not found: {path}")
            return None
    try:
        obj = json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"[WARN] failed to read menu_index_json: {path} ({type(e).__name__}: {e})")
        return None

    entries: List[Dict[str, Any]] = []
    if isinstance(obj, dict) and isinstance(obj.get("items"), list):
        entries = obj["items"]
    elif isinstance(obj, list):
        entries = obj
    else:
        print(f"[WARN] menu_index_json schema unsupported: {type(obj)}")
        return None

    vmap: Dict[str, Dict[str, Any]] = {}
    for it in entries:
        if not isinstance(it, dict):
            continue
        menu = str(it.get("menu") or "").strip()
        if menu:
            vmap.setdefault(menu, it)
        variants = it.get("variants")
        if isinstance(variants, list):
            for v in variants:
                if isinstance(v, str):
                    vv = v.strip()
                    if vv:
                        vmap.setdefault(vv, it)
    if not vmap:
        print(f"[WARN] menu_index_json loaded but empty: {path}")
        return None
    print(f"[INFO] exact-precheck index loaded: {path} (variants={len(vmap)})")
    return vmap


def _exact_precheck(menu_norm: str, vmap: Optional[Dict[str, Dict[str, Any]]]) -> Optional[Dict[str, Any]]:
    if not vmap:
        return None
    q = (menu_norm or "").strip()
    if not q:
        return None
    hit = vmap.get(q)
    if not isinstance(hit, dict):
        return None
    # Build a rag-like response compatible with downstream logic
    best_match = {
        "id": hit.get("id"),
        "menu": hit.get("menu"),
        "best_variant": q,
        "embed_score": 1.0,
        "jamo_score": 1.0,
        "final_score": 1.0,
        "ingredients_ko": hit.get("ingredients_ko") or [],
        "alg_tags": hit.get("alg_tags") or [],
    }
    return {
        "status": "EXACT",
        "decision_method": "STRING_EXACT_PRECHECK",
        "used_query": q,
        "best_match": best_match,
        "candidates": [],
        "signals": {"thresholds": {}},
        "debug": None,
        "decided_menu": hit.get("menu"),
    }


def _read_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)


def _extract_items(normalized: Any) -> List[Dict[str, Any]]:
    if isinstance(normalized, dict) and isinstance(normalized.get("items"), list):
        return normalized["items"]
    if isinstance(normalized, list):
        return normalized
    raise ValueError("normalize.json schema not supported: expected dict{items:[]} or list.")


def _pick_poly(it: Dict[str, Any]) -> Any:
    return (
        it.get("poly")
        or it.get("poly_menu")
        or it.get("polybox")
        or it.get("poly_box")
        or it.get("polygon")
        or None
    )


def run_step(run_dir: Path) -> Path:
    normalize_path = run_dir / "normalize" / "normalize.json"
    if not normalize_path.exists():
        alt = run_dir / "normalize" / "normalized.json"
        if alt.exists():
            normalize_path = alt
        else:
            raise FileNotFoundError(f"normalize output not found: {normalize_path}")

    normalized = _read_json(normalize_path)
    items = _extract_items(normalized)

    out_items: List[Dict[str, Any]] = []
    stats = {"TOTAL": 0, "EXACT": 0, "UNKNOWN": 0}

    # 기존: for it in items:
    for idx, it in enumerate(items, start=1):
        if not isinstance(it, dict):
            continue

        # ✅ item_id 자동 생성 (없거나 null/빈값이면 순번 부여)
        src_item_id = it.get("item_id", None)
        if src_item_id is None or (isinstance(src_item_id, str) and src_item_id.strip() == ""):
            item_id = f"itm_{idx:04d}"  # itm_0001, itm_0002 ...
        else:
            item_id = src_item_id

        raw_menu = str(
            it.get("raw_menu")
            or it.get("menu_raw")
            or it.get("text")
            or it.get("menu")
            or it.get("query")
            or ""
        ).strip()

        menu_norm = str(it.get("menu_norm") or "").strip()

        res = match_exact(menu_norm)
        match_status = res.get("status", "unknown")
        if match_status != "exact":
            match_status = "unknown"

        out_item: Dict[str, Any] = {
            "item_id": item_id,  # ✅ 여기 null 대신 보장
            "raw_menu": raw_menu,
            "poly": _pick_poly(it),
            "menu_norm": menu_norm,
            "match_status": match_status,
            "confirmed": res.get("confirmed") if match_status == "exact" else None,

        }

        out_items.append(out_item)

        stats["TOTAL"] += 1
        if match_status == "exact":
            stats["EXACT"] += 1
        else:
            stats["UNKNOWN"] += 1

    out_path = run_dir / "rag_match" / "rag_match.json"
    payload = {
        "run_dir": str(run_dir),
        "input_normalize": str(normalize_path),
        "config": {"policy": "EXACT_ONLY_CHROMA_MENU"},
        "stats": stats,
        "items": out_items,
    }
    _write_json(out_path, payload)
    return out_path


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Step04 RAG match (EXACT-only)")
    p.add_argument("--run_id", type=str, required=True)
    p.add_argument("--data_dir", type=str, required=True)
    p.add_argument("--run_dir", type=str, required=True)
    return p


def main() -> None:
    args = build_parser().parse_args()
    run_dir = Path(args.run_dir)
    out_path = run_step(run_dir)
    print(f"[Step04] wrote: {out_path}")


if __name__ == "__main__":
    main()
