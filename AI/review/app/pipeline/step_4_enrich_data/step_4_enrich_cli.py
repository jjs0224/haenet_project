# ai/review/app/pipeline/step_4_enrich_data/step_4_enrich_cli.py
from __future__ import annotations

import argparse
import json
import os
from dotenv import load_dotenv
from pathlib import Path
from typing import Dict, Any, List, Optional

from AI.review.app.pipeline.step_4_enrich_data.step_4_enrich import run_step4_enrich
from AI.review.app.domain.schemas import PipelineContext

load_dotenv()

def _load_step3_json(path: Path) -> Dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))

    # step3 출력 포맷 예상:
    # { "lines": [...], "phone": "...", "menu_ko": [...] }
    phone = data.get("phone")
    menu_ko = data.get("menu_ko") or data.get("menu_name") or []
    if not isinstance(menu_ko, list):
        raise ValueError("menu_ko must be a list in step3 json")

    return {"phone": phone, "menu_ko": menu_ko, "raw": data}


def main():
    p = argparse.ArgumentParser("step4-enrich")
    p.add_argument("step3_json", type=str, help="step3 output json path (contains phone, menu_ko)")
    p.add_argument("--out", type=str, default="debug/step4", help="output folder")
    p.add_argument("--debug", action="store_true", help="store debug json (ctx.debug.enrich)")
    p.add_argument("--naver-id", type=str, default=os.getenv("NAVER_CLIENT_ID"))
    p.add_argument("--naver-secret", type=str, default=os.getenv("NAVER_CLIENT_SECRET"))
    p.add_argument("--gemini-key", type=str, default=os.getenv("GEMINI_API_KEY"))

    args = p.parse_args()

    def _mask(k: str | None) -> str:
        if not k:
            return "None"
        return f"len={len(k)} {k[:4]}...{k[-4:]}"

    step3_path = Path(args.step3_json)
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    if not args.gemini_key:
        raise ValueError("Missing Gemini API key. Pass --gemini-key or set GEMINI_API_KEY env var.")

    # load step3 result (phone + menu_ko)
    s3 = _load_step3_json(step3_path)

    # build ctx
    ctx = PipelineContext(mode="debug" if args.debug else "prod")
    ctx.extracted.phone = s3["phone"]
    ctx.extracted.menu_ko = s3["menu_ko"]

    naver_cfg: Dict[str, str] = {}
    if args.naver_id and args.naver_secret:
        naver_cfg = {"client_id": args.naver_id, "client_secret": args.naver_secret}

    # run step4
    ctx = run_step4_enrich(
        ctx,
        naver_cfg=naver_cfg,
        gemini_api_key=args.gemini_key,
    )

    # save outputs
    result = {
        "store": {
            "store_name_ko": getattr(ctx.store, "store_name", None),
            "store_name_en": getattr(ctx.store, "store_name_en", None),
            "address": getattr(ctx.store, "address", None),
            "city": getattr(ctx.store, "city", None),
            "coords": getattr(ctx.store, "coords", None),
        },
        "menu": {
            "menu_ko": ctx.extracted.menu_ko,
            "menu_en": getattr(ctx.extracted, "menu_en", None),
        },
    }

    out_json = out_dir / "step4_enrich_result.json"
    out_json.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(" saved:", out_json)

    if args.debug:
        dbg = getattr(ctx.debug, "enrich", None)
        dbg_json = out_dir / "step4_debug_enrich_raw.json"
        dbg_json.write_text(json.dumps(dbg, ensure_ascii=False, indent=2), encoding="utf-8")
        print(" saved debug:", dbg_json)

    print(" store_name_ko:", result["store"]["store_name_ko"])
    print(" menu_en:", result["menu"]["menu_en"])


if __name__ == "__main__":
    main()
