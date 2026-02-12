from __future__ import annotations

import json
import uuid
import cv2
import time

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Dict, Any
from datetime import datetime
from copy import deepcopy

from AI.review.app.domain.schemas import PipelineContext

# step0
from AI.review.app.pipeline.step_1_rectify.step0_preprocess import run_step0_preprocess, Step0PreprocessConfig

# step1
from AI.review.app.pipeline.step_1_rectify.step_1_rectify import run_step1_rectify
from AI.review.app.pipeline.step_1_rectify.run_rectify import RectifyConfig

# step2
from AI.review.app.pipeline.step_2_ocr.step_2_ocr import run_step2_ocr
from AI.review.app.pipeline.step_2_ocr.ocr_model import OCRConfig
from AI.review.app.pipeline.step_2_ocr.access_ocr_quality import assess_ocr_quality, is_bad_quality

# step3
from AI.review.app.pipeline.step_3_normalize.step_3_normalize import run_step3_normalize, NormalizeConfig

# step4
from AI.review.app.pipeline.step_4_enrich_data.step_4_enrich import run_step4_enrich

# step5
from AI.review.app.pipeline.step_5_final.step_5_create_JSON import run_build_final_response


def make_run_dir(base: Path, name: str | None = None) -> Path:
    ts = datetime.now().strftime("%Y%m%d%H%M")
    folder = ts if not name else f"{ts}_{name}"
    run_dir = base / folder
    run_dir.mkdir(parents=True, exist_ok=False)
    return run_dir


def _items_to_dicts(items) -> list[dict]:
    out = []
    for it in items or []:
        if isinstance(it, dict):
            out.append(it)
        elif hasattr(it, "model_dump"):
            out.append(it.model_dump())
        elif hasattr(it, "dict"):
            out.append(it.dict())
        else:
            out.append({"score": 0.0})
    return out


@dataclass(frozen=True)
class PipelineConfig:
    mode: str = "prod"
    test_base_dir: Path = Path("AI/review/test")
    run_name: Optional[str] = None

    # step0
    step0_cfg: Step0PreprocessConfig = Step0PreprocessConfig()

    # step1
    rectify_cfg: RectifyConfig = field(default_factory=RectifyConfig)

    # step2
    ocr_cfg: Optional[OCRConfig] = None

    # step3
    normalize_cfg: NormalizeConfig = NormalizeConfig()

    # step4
    naver_cfg: Optional[Dict[str, str]] = None
    gemini_api_key: Optional[str] = None

    # OCR gate
    ocr_low_cut: float = 0.6

    #  Deskew gate
    deskew_min_abs_angle_deg: float = 2.0

def _print_elapsed(step: str, start: float):
    elapsed = time.perf_counter() - start
    print(f"[time] {step}: {elapsed:.2f}s")

def run_pipeline(*, input_image_path: str, cfg: PipelineConfig) -> Dict[str, Any]:
    t0 = time.perf_counter()  # orchestrator start
    print("[time] orchestrator start (0.00s)")

    run_dir = make_run_dir(base=cfg.test_base_dir, name=cfg.run_name)

    step0_dir = run_dir / "step0_preprocess"
    step1_dir = run_dir / "step1_rectify"
    step2_dir = run_dir / "step2_ocr"
    step3_dir = run_dir / "step3_normalize"
    step4_dir = run_dir / "step4_enrich"
    step5_dir = run_dir / "step5_final"

    ctx = PipelineContext(mode=cfg.mode)
    ctx.job_id = str(uuid.uuid4())
    ctx.images.input_path = input_image_path

    # =========================
    # Step0: light preprocess
    # =========================
    print("step0")
    step0 = run_step0_preprocess(
        input_image_path=ctx.images.input_path,
        out_dir=step0_dir,
        cfg=cfg.step0_cfg,
    )
    pre_ocr_path = step0["pre_ocr_path"]

    if cfg.mode == "debug":
        ctx.debug.jsons["step0_meta"] = str(step0_dir / "meta.json")
        ctx.debug.images["step0_pre_ocr"] = pre_ocr_path

    _print_elapsed("step0_preprocess", t0)

    # =========================
    # Step2 pass1: OCR on preprocessed
    # =========================
    print("step2")
    ctx_ocr1 = run_step2_ocr(
        ctx,
        out_dir=step2_dir / "pass1_pre",
        cfg=cfg.ocr_cfg,
        image_path=pre_ocr_path,
    )

    q1 = assess_ocr_quality(_items_to_dicts(ctx_ocr1.ocr.items), low_cut=cfg.ocr_low_cut)
    bad1 = is_bad_quality(q1)

    (step2_dir / "pass1_pre").mkdir(parents=True, exist_ok=True)
    (step2_dir / "pass1_pre" / "quality.json").write_text(
        json.dumps(q1, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    # =========================
    # Step2 pass2: if bad -> rectify(original) + OCR
    # =========================
    if bad1:
        ctx2 = deepcopy(ctx)

        ctx2.images.input_path = input_image_path
        ctx2 = run_step1_rectify(ctx2, out_dir=step1_dir, cfg=cfg.rectify_cfg)

        ocr_src2 = ctx2.images.rectified_path or ctx2.images.cropped_path or ctx2.images.input_path

        ctx_ocr2 = run_step2_ocr(
            ctx2,
            out_dir=step2_dir / "pass2_rectified",
            cfg=cfg.ocr_cfg,
            image_path=ocr_src2,
        )

        q2 = assess_ocr_quality(_items_to_dicts(ctx_ocr2.ocr.items), low_cut=cfg.ocr_low_cut)

        (step2_dir / "pass2_rectified").mkdir(parents=True, exist_ok=True)
        (step2_dir / "pass2_rectified" / "quality.json").write_text(
            json.dumps(q2, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        def better(a: dict, b: dict) -> bool:
            if a["avg"] != b["avg"]:
                return a["avg"] > b["avg"]
            if a["p10"] != b["p10"]:
                return a["p10"] > b["p10"]
            return a["low_ratio"] < b["low_ratio"]

        ctx = ctx_ocr2 if better(q2, q1) else ctx_ocr1
    else:
        ctx = ctx_ocr1

    # =========================
    # ✅ Deskew (rotate image only) then OCR again
    # =========================

    from AI.review.app.pipeline.step_2_ocr.deskew_from_ocr import (
        DeskewFromOCRConfig,
        estimate_skew_angle_deg,
        rotate_image_keep_size,
        pick_ocr_image_path,
    )
    ocr_img_path = pick_ocr_image_path(ctx)
    img = cv2.imread(str(ocr_img_path))

    if img is not None and getattr(ctx, "ocr", None) is not None and ctx.ocr.items:
        deskew_cfg = DeskewFromOCRConfig(min_abs_angle_deg=2.0)

        angle = estimate_skew_angle_deg(ctx.ocr.items, deskew_cfg)
        if angle is not None and abs(angle) >= deskew_cfg.min_abs_angle_deg:
            # poly를 수평으로 만들려면 -angle
            apply_angle = -float(angle)

            rotated = rotate_image_keep_size(img, apply_angle)

            # "새 파일 만들지 말라" -> 기존 OCR 소스 이미지를 덮어쓰기
            cv2.imwrite(str(ocr_img_path), rotated)

            # 이미지가 바뀌었으니 OCR도 다시 돌려서 ctx.ocr.items를 '정방향' 결과로 갱신
            ctx = run_step2_ocr(
                ctx,
                out_dir=step2_dir / "pass1_pre",  # 기존 폴더 그대로 사용(새 폴더 생성 X)
                cfg=cfg.ocr_cfg,
                image_path=str(ocr_img_path),
            )

    _print_elapsed("step2_ocr", t0)

    # =========================
    # Step3
    # =========================
    print("step3")
    ctx = run_step3_normalize(ctx, cfg=cfg.normalize_cfg)

    step3_dir.mkdir(parents=True, exist_ok=True)
    (step3_dir / "step3_result.json").write_text(
        json.dumps(ctx.model_dump() if hasattr(ctx, "model_dump") else ctx.dict(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    _print_elapsed("step3_normalize", t0)

    # =========================a
    # Step4
    # =========================
    if not cfg.gemini_api_key:
        raise ValueError("Missing gemini_api_key ...")

    naver_cfg = cfg.naver_cfg or {}

    print("step4")
    ctx = run_step4_enrich(ctx, naver_cfg=naver_cfg, gemini_api_key=cfg.gemini_api_key)

    step4_dir.mkdir(parents=True, exist_ok=True)
    (step4_dir / "ctx_after_step4.json").write_text(
        json.dumps(ctx.model_dump() if hasattr(ctx, "model_dump") else ctx.dict(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    _print_elapsed("step4_enrich", t0)

    # =========================
    # Step5
    # =========================
    print("step5")
    ctx = run_build_final_response(ctx)

    final_payload = ctx.final.model_dump() if hasattr(ctx.final, "model_dump") else ctx.final.dict()

    step5_dir.mkdir(parents=True, exist_ok=True)
    (step5_dir / "final.json").write_text(
        json.dumps(final_payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    _print_elapsed("step5_finalize", t0)

    return {"run_dir": str(run_dir), "final": final_payload}
