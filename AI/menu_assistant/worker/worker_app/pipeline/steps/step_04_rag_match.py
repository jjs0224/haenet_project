from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List

from menu_assistant.worker.worker_app.rag.retrieval import match_exact


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

    for idx, it in enumerate(items, start=1):
        if not isinstance(it, dict):
            continue

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

        # If query matched a variant alias, normalize to canonical menu name.
        confirmed = res.get("confirmed") if isinstance(res, dict) else None
        matched_variant = (
            str((confirmed or {}).get("matched_variant") or "").strip()
            if isinstance(confirmed, dict)
            else ""
        )
        canonical_menu = (
            str((confirmed or {}).get("menu") or "").strip()
            if isinstance(confirmed, dict)
            else ""
        )
        resolved_menu_norm = menu_norm
        if match_status == "exact" and matched_variant and canonical_menu:
            resolved_menu_norm = canonical_menu

        out_item: Dict[str, Any] = {
            "item_id": item_id,
            "raw_menu": raw_menu,
            "poly": _pick_poly(it),
            "menu_norm": resolved_menu_norm,
            "menu_norm_original": menu_norm,
            "match_status": match_status,
            "resolved_by_variant": bool(matched_variant) if match_status == "exact" else False,
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
