from __future__ import annotations

import argparse
import os
from pathlib import Path
from dotenv import load_dotenv

from AI.review.app.pipeline.orchestrator import run_pipeline, PipelineConfig  # 너 파일명에 맞게

def main():
    load_dotenv()
    p = argparse.ArgumentParser("receipt-pipeline")
    p.add_argument("image", type=str, help="input receipt image path")
    p.add_argument("--name", type=str, default=None, help="run name")
    p.add_argument("--mode", type=str, default="debug", choices=["debug", "prod"])
    p.add_argument("--out", type=str, default="AI/review/test", help="base output dir")
    args = p.parse_args()

    cfg = PipelineConfig(
        mode=args.mode,
        test_base_dir=Path(args.out),
        run_name=args.name,
        naver_cfg={
            "client_id": os.getenv("NAVER_CLIENT_ID", ""),
            "client_secret": os.getenv("NAVER_CLIENT_SECRET", ""),
        },
        gemini_api_key=os.getenv("GEMINI_API_KEY"),
    )

    out = run_pipeline(input_image_path=args.image, cfg=cfg)
    print(out["run_dir"])
    print(out["final"])

if __name__ == "__main__":
    main()
