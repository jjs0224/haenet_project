import json
from pathlib import Path
from typing import Dict, Any, List, Optional


def load_json(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _match_keywords(texts: List[str], keywords: Optional[List[str]]) -> bool:
    if not keywords:
        return True
    joined = " ".join([t for t in texts if t])
    return any(k in joined for k in keywords)


def summary(data: Dict[str, Any]) -> None:
    """
    Final Step03 output schema:
      {
        "items": [
          {"raw_menu": "...", "poly": [...], "menu_norm": "..."},
          ...
        ]
      }
    """
    items = data.get("items", []) or []

    total = len(items)
    with_poly = sum(1 for it in items if isinstance(it.get("poly"), list) and len(it.get("poly", [])) >= 4)

    menu_norms = [str(it.get("menu_norm", "") or "") for it in items]
    raw_menus = [str(it.get("raw_menu", "") or "") for it in items]

    nonempty_norm = sum(1 for s in menu_norms if s)
    unique_norm = len(set([s for s in menu_norms if s]))
    unique_raw = len(set([s for s in raw_menus if s]))

    one_char_norm = sum(1 for s in menu_norms if len(s) == 1)
    avg_len = (sum(len(s) for s in menu_norms if s) / max(1, nonempty_norm))

    print("\n=== STEP 03 SUMMARY (FINAL) ===")
    print(f"- total items             : {total}")
    print(f"- non-empty menu_norm     : {nonempty_norm}")
    print(f"- items with poly         : {with_poly}")
    print(f"- unique menu_norm        : {unique_norm}")
    print(f"- unique raw_menu         : {unique_raw}")
    print(f"- 1-char menu_norm count  : {one_char_norm}")
    print(f"- avg menu_norm length    : {avg_len:.2f}")


def show_items(items: List[Dict[str, Any]], keywords: Optional[List[str]] = None, limit: int = 30) -> None:
    """
    Print normalized items (raw_menu / menu_norm / poly bbox)
    """
    print("\n=== ITEMS (sample) ===")
    cnt = 0
    for i, it in enumerate(items):
        raw_menu = str(it.get("raw_menu", "") or "")
        menu_norm = str(it.get("menu_norm", "") or "")
        poly = it.get("poly")

        if not _match_keywords([raw_menu, menu_norm], keywords):
            continue

        # bbox 표시(있으면)
        bbox = ""
        if isinstance(poly, list) and len(poly) >= 4:
            try:
                xs = [float(p[0]) for p in poly[:4]]
                ys = [float(p[1]) for p in poly[:4]]
                bbox = f" bbox=({min(xs):.1f},{min(ys):.1f})-({max(xs):.1f},{max(ys):.1f})"
            except Exception:
                bbox = ""

        print(f"- {i:>3} | raw_menu='{raw_menu}' | menu_norm='{menu_norm}'{bbox}")
        cnt += 1
        if cnt >= limit:
            break

    if cnt == 0:
        print("(no matches)")


def show_structured_items(items: List[Dict[str, Any]], keywords: Optional[List[str]] = None, limit: int = 30) -> None:
    """
    Print raw structured item dictionaries (JSON) for quick debugging.
    """
    print("\n=== ITEMS (structured sample) ===")
    cnt = 0
    for i, it in enumerate(items):
        raw_menu = str(it.get("raw_menu", "") or "")
        menu_norm = str(it.get("menu_norm", "") or "")
        if not _match_keywords([raw_menu, menu_norm], keywords):
            continue

        print(f"- {i:>3} | {json.dumps(it, ensure_ascii=False)}")
        cnt += 1
        if cnt >= limit:
            break

    if cnt == 0:
        print("(no matches)")


def main():
    import argparse

    p = argparse.ArgumentParser(description="Quick check for FINAL step_03_normalize output")
    p.add_argument("--json", required=True, help="step_03 normalize output json path")
    p.add_argument("--keywords", nargs="*", default=None, help="optional keywords to filter outputs")
    p.add_argument("--limit", type=int, default=30, help="max rows to print in sample")
    p.add_argument("--no-sample", action="store_true", help="print summary only")
    p.add_argument("--show-structured", action="store_true", help="print structured JSON sample")

    args = p.parse_args()

    data = load_json(Path(args.json))
    summary(data)

    if not args.no_sample:
        if args.show_structured:
            show_structured_items(data.get("items", []) or [], keywords=args.keywords, limit=args.limit)
        else:
            show_items(data.get("items", []) or [], keywords=args.keywords, limit=args.limit)


if __name__ == "__main__":
    main()


"""
Example:

python -m menu_assistant.worker.worker_app.utils.check_step_03_result ^
  --json menu_assistant\data\runs\20260113_121958\normalize\normalize.json ^
  --keywords 죽 떡사리 ^
  --limit 50
"""
