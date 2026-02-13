"""Image rectification utilities."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional
import time
import cv2
import numpy as np
#보정모델과 결과에대한 이미지와 meta에대한 데이터클래스(RectifyResult)
from .backends import AutoBackend, DewarpNetBackend, DocUNetBackend, DoctrBackend, RectifyResult
#좌표값을 건드리지않고 기본적으로 할수있는 보정에관한 객체및옵션값들
from .photometric import (
    EnhanceConfig,
    IlluminationConfig,
    DenoiseConfig,
    correct_illumination,
    denoise,
    apply_photometric_enhance,
)


@dataclass
class RectifyConfig:
    backend: str = "none"  # none | doctr | dewarpnet | docunet | auto
    device: str = "cpu"
    model_dir: Optional[str] = None

    # Photometric pipeline (recommended always ON)
    illumination: IlluminationConfig = IlluminationConfig()
    denoise: DenoiseConfig = DenoiseConfig()
    enhance: EnhanceConfig = EnhanceConfig()


def _get_backend(name: str, device: str, model_dir: Optional[str]):
    #이름부분부분 전부 소문자화하고 빈공간 없애기
    name = (name or "none").lower().strip()
    # name 에 따른 결과값 설정
    if name == "none":
        return None
    if name == "doctr":
        return DoctrBackend(device=device, model_dir=model_dir)
    if name == "dewarpnet":
        return DewarpNetBackend(device=device, model_dir=model_dir)
    if name == "docunet":
        return DocUNetBackend(device=device, model_dir=model_dir)
    if name == "auto":
        return AutoBackend(device=device, model_dir=model_dir)
    raise ValueError(f"Unknown backend: {name}")



#image_bgr img정보와 위에서 설정한 객체값을 받아서 RectifyResult 형식의 객체를 얻어낸다.
def rectify_image(image_bgr: np.ndarray, cfg: RectifyConfig) -> RectifyResult:
    """
    Pure rectification step:
      - NO text detection
      - Focus on making the entire menu board more OCR-friendly.
    Output is the rectified image coordinate system (for downstream OCR + overlay).
    """
    #현재 시간측정 추후에 얼마나걸릴지(처리소요시간) 체크하기위해 사용
    t0 = time.time()
    #rectify_meta.json에 저장될 객체 image.[0]=H,[1]=W,ops는 보정에 사용된 파트들 추가
    meta: Dict[str, Any] = {
        "backend": cfg.backend,
        "device": cfg.device,
        "model_dir": cfg.model_dir,
        "input_shape": [int(image_bgr.shape[0]), int(image_bgr.shape[1])],
        "ops": [],
    }
    #현재단계 까지 처리된 이미지
    out = image_bgr

    # Photometric (pixel-location invariant)
    #조명/그림자 보정
    out, m_illum = correct_illumination(out, cfg.illumination)
    if m_illum.get("illumination"):
        meta["ops"].append(m_illum)
    #노이즈 제거
    out, m_den = denoise(out, cfg.denoise)
    if m_den.get("denoise"):
        meta["ops"].append(m_den)
    #대비/선명도/감마/CLAHE 보정
    out, m_enh = apply_photometric_enhance(out, cfg.enhance)
    if m_enh.get("photometric"):
        meta["ops"].append(m_enh)

    # Optional geometric backend (may warp coordinates, which is now allowed in your UI strategy)
    # 보정모델을 사용했으면 해당정보를 받고 보정진행
    backend = _get_backend(cfg.backend, cfg.device, cfg.model_dir)
    if backend is not None:
        res = backend.rectify(out)
        out = res.image
        meta["ops"].append({"backend_meta": res.meta})
    #보정이후의 이미지크기값 저장
    meta["output_shape"] = [int(out.shape[0]), int(out.shape[1])]
    #처리시간계산해서 입력
    meta["elapsed_ms"] = int((time.time() - t0) * 1000)
    meta["notes"] = "Overlay and OCR are performed in rectified image coordinate system."
    #최종 결과값객체 도출
    return RectifyResult(image=out, meta=meta)

#run time 에서 사용되는함수 정의 이미지 읽고 쓰는부분정의
def read_image_bgr(path: str) -> np.ndarray:
    img = cv2.imread(path, cv2.IMREAD_COLOR)
    if img is None:
        raise FileNotFoundError(f"Failed to read image: {path}")
    return img


def write_image_bgr(path: str, image_bgr: np.ndarray) -> None:
    ok = cv2.imwrite(path, image_bgr)
    if not ok:
        raise IOError(f"Failed to write image: {path}")
