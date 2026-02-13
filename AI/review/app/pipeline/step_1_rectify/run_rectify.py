from __future__ import annotations
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Dict, Optional
import json
import numpy as np

from AI.review.app.pipeline.step_1_rectify.receipt_types import PipelineResult
from AI.review.app.pipeline.step_1_rectify.io_utils import read_bgr, write_image
from AI.review.app.pipeline.step_1_rectify.preprocess import PreprocessConfig, preprocess_for_crop
from AI.review.app.pipeline.step_1_rectify.crop_receipt import CropConfig, crop_receipt_only
from AI.review.app.pipeline.step_1_rectify.postprocess import PostprocessConfig, postprocess_for_ocr
# from deskew import DeskewConfig, deskew_receipt

@dataclass
class RectifyConfig:
    pre: PreprocessConfig = PreprocessConfig()
    crop: CropConfig = CropConfig()
    # deskew: DeskewConfig = DeskewConfig()
    post: PostprocessConfig = PostprocessConfig()
    save_debug: bool = True

def run_receipt_rectify(image_path: Path, out_dir: Path, cfg: RectifyConfig) -> PipelineResult:
    out_dir.mkdir(parents=True, exist_ok=True)

    img0 = read_bgr(image_path)

    meta: Dict[str, Any] = {
        "input_path": str(image_path),
        "cfg": {
            "pre": asdict(cfg.pre),
            "crop": asdict(cfg.crop),
            "post": asdict(cfg.post),
        },
        "step_1": [],
    }

    if cfg.save_debug:
        write_image(out_dir / "00_original.jpg", img0)

    # 1) pre-crop
    pre_img, pre_meta = preprocess_for_crop(img0, cfg.pre)
    meta["step_1"].append(pre_meta)
    if cfg.save_debug:
        write_image(out_dir / "01_pre_for_crop.jpg", pre_img)

    # 2) crop
    crop_res = crop_receipt_only(pre_img, cfg.crop)
    meta["crop"] = crop_res.meta
    if cfg.save_debug:
        write_image(out_dir / "10_edges.jpg", crop_res.edges)
        write_image(out_dir / "11_quad_overlay.jpg", crop_res.overlay_bgr)
        write_image(out_dir / "12_cropped.jpg", crop_res.cropped_bgr)

    # 3) post-crop OCR
    final_img, post_meta = postprocess_for_ocr(crop_res.cropped_bgr, cfg.post)
    meta["step_1"].append(post_meta)
    if cfg.save_debug:
        write_image(out_dir / "20_post_for_ocr.jpg", final_img)


    (out_dir / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

    return PipelineResult(
        final_for_ocr_bgr=final_img,
        crop=crop_res,
        meta=meta,
    )

'''
조립+디버그 저장+meta
'''