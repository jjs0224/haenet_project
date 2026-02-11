from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


@dataclass
class NormalizeConfig:
    min_len: int = 2
    min_score: float = 0.0


# 영어+숫자 제거 (fullwidth 포함)
_RE_REMOVE_EN_DIGIT = re.compile(r"[A-Za-z0-9Ａ-Ｚａ-ｚ０-９]+", re.UNICODE)
# 한글 제외 특수기호 제거 (·, •, -, _, | 등)
_RE_REMOVE_SYMBOLS = re.compile(r"[^\uAC00-\uD7A3]+", re.UNICODE)


def _safe_poly(poly: Any) -> Optional[List[List[float]]]:
    if not isinstance(poly, list) or len(poly) < 4:
        return None
    out: List[List[float]] = []
    for p in poly[:4]:
        if not isinstance(p, (list, tuple)) or len(p) < 2:
            return None
        try:
            out.append([float(p[0]), float(p[1])])
        except Exception:
            return None
    return out

def remove_symbols_except_korean(text: str) -> str:
    if not text:
        return ""
    return _RE_REMOVE_SYMBOLS.sub("", text)

def _poly_bbox(poly: List[List[float]]) -> Tuple[float, float, float, float]:
    xs = [float(p[0]) for p in poly]
    ys = [float(p[1]) for p in poly]
    return min(xs), min(ys), max(xs), max(ys)


def _bbox_to_poly(x1: float, y1: float, x2: float, y2: float) -> List[List[float]]:
    return [[x1, y1], [x2, y1], [x2, y2], [x1, y2]]


def remove_english_and_digits(text: str) -> str:
    return _RE_REMOVE_EN_DIGIT.sub("", text or "")


def split_by_policy(text: str) -> List[str]:
    """
    Split policy:
      - Split 기준: '(' , ')' , ',' , '，' , '/' , ':'
      - 괄호 () 안의 내용은 전부 삭제
      - 구분 기호는 delimiter 역할만 수행
    """
    if not text:
        return []

    parts: List[str] = []
    buf: List[str] = []
    depth = 0

    for ch in text:
        if ch == "(":
            if buf:
                parts.append("".join(buf))
                buf = []
            depth += 1
            continue

        if ch == ")":
            if depth > 0:
                depth -= 1
            if buf:
                parts.append("".join(buf))
                buf = []
            continue

        if depth > 0:
            continue  # 괄호 내부 삭제

        if ch in [",", "，", "/", ":"]:
            if buf:
                parts.append("".join(buf))
                buf = []
            continue

        buf.append(ch)

    if buf:
        parts.append("".join(buf))

    return parts


def normalize_spacing(text: str) -> str:
    """
    - 양끝 공백 제거
    - 문자열 내부의 모든 공백 제거
    """
    if not text:
        return ""
    return "".join(text.strip().split())


def strip_parts(parts: List[str]) -> List[str]:
    out: List[str] = []
    for p in parts:
        # 1) part 내부 공백 제거
        s = normalize_spacing(p)

        # 2) part 내부 특수기호 제거 (스플릿 이후에만!)
        s = remove_symbols_except_korean(s)

        # 3) 최종 공백/길이 정리 (안전)
        s = normalize_spacing(s)

        if s:
            out.append(s)
    return out



def split_poly_by_text_lengths(base_poly: List[List[float]], parts: List[str]) -> List[List[List[float]]]:
    if not parts:
        return []
    if len(parts) == 1:
        return [base_poly]

    x1, y1, x2, y2 = _poly_bbox(base_poly)
    width = max(1.0, float(x2 - x1))

    lens = [max(0, len(p)) for p in parts]
    total = sum(lens)
    if total <= 0:
        return [base_poly for _ in parts]

    polys: List[List[List[float]]] = []
    cur_x = float(x1)
    for i, ln in enumerate(lens):
        if i == len(lens) - 1:
            seg_x2 = float(x2)
        else:
            seg_x2 = cur_x + (float(ln) / float(total)) * width

        if seg_x2 < cur_x:
            seg_x2 = cur_x

        polys.append(_bbox_to_poly(cur_x, y1, seg_x2, y2))
        cur_x = seg_x2

    return polys


def is_keep_item(score: float, raw_menu: str, cfg: NormalizeConfig) -> bool:
    if score < float(cfg.min_score):
        return False
    if len(raw_menu) < int(cfg.min_len):
        return False
    return True


def run_step_03_normalize(ocr_json_path: Path, out_json_path: Path, cfg: NormalizeConfig) -> Path:
    with ocr_json_path.open("r", encoding="utf-8") as f:
        ocr = json.load(f)

    items_out: List[Dict[str, Any]] = []

    for it in ocr.get("items", []):
        text_in = str(it.get("text", "") or "")
        poly_in = _safe_poly(it.get("poly"))
        score = float(it.get("score", 0.0) or 0.0)

        if not text_in or poly_in is None:
            continue

        t1 = remove_english_and_digits(text_in)
        parts = strip_parts(split_by_policy(t1))  # strip_parts 내부에서 기호 제거 수행

        if not parts:
            continue

        part_polys = split_poly_by_text_lengths(poly_in, parts)

        for raw_menu, ppoly in zip(parts, part_polys):
            if not is_keep_item(score, raw_menu, cfg):
                continue

            items_out.append(
                {
                    "raw_menu": raw_menu,
                    "poly": ppoly,
                    "menu_norm": raw_menu,
                }
            )

    out_json_path.parent.mkdir(parents=True, exist_ok=True)
    with out_json_path.open("w", encoding="utf-8") as f:
        json.dump({"items": items_out}, f, ensure_ascii=False, indent=2)

    return out_json_path


def _find_latest_run_dir(runs_root: Path) -> Path:
    run_dirs = [p for p in runs_root.iterdir() if p.is_dir()]
    if not run_dirs:
        raise FileNotFoundError(f"No run directories under: {runs_root}")
    run_dirs.sort(key=lambda p: p.name)
    return run_dirs[-1]


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Step03 normalize (no merge)")
    p.add_argument("--runs-root", default="menu_assistant/data/runs")
    p.add_argument("--run-id", default=None)
    p.add_argument("--out-json", default=None)
    p.add_argument("--min-len", type=int, default=2)
    p.add_argument("--min-score", type=float, default=0.0)

    args = p.parse_args()

    runs_root = Path(args.runs_root)
    run_dir = (runs_root / args.run_id) if args.run_id else _find_latest_run_dir(runs_root)

    in_json = run_dir / "ocr" / "ocr.json"
    out_json = Path(args.out_json) if args.out_json else run_dir / "normalize" / "normalize.json"

    cfg = NormalizeConfig(min_len=args.min_len, min_score=args.min_score)
    run_step_03_normalize(in_json, out_json, cfg)

    print("=== step_03_normalize DONE ===")
