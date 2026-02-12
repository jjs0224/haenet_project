from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Iterable, List, Optional, Tuple

import cv2
import numpy as np

@dataclass(frozen=True)
class DeskewFromOCRConfig:
    min_abs_angle_deg: float = 2.0
    min_edge_len_px: float = 60.0
    min_score: float = 0.5
    require_text: bool = True
    skip_digit_only: bool = True

# ---------- helpers ----------
def _get_poly(item: Any) -> Optional[np.ndarray]:
    poly = item.get("poly") if isinstance(item, dict) else getattr(item, "poly", None)
    if not poly or len(poly) != 4:
        return None
    return np.array(poly, dtype=np.float32)

def _get_text_score(item: Any) -> tuple[str, float]:
    if isinstance(item, dict):
        return str(item.get("text") or ""), float(item.get("score") or 0.0)
    return str(getattr(item, "text", "")), float(getattr(item, "score", 0.0))

def _edge_angle_deg(p0: np.ndarray, p1: np.ndarray) -> float:
    return math.degrees(math.atan2(float(p1[1]-p0[1]), float(p1[0]-p0[0])))

def _normalize_angle(ang: float) -> float:
    while ang <= -180: ang += 360
    while ang > 180: ang -= 360
    if ang > 90: ang -= 180
    if ang < -90: ang += 180
    if ang > 45: ang -= 90
    if ang < -45: ang += 90
    return ang

# ---------- angle estimation ----------
def estimate_skew_angle_deg(
    ocr_items: Iterable[Any],
    cfg: DeskewFromOCRConfig,
) -> Optional[float]:

    angles, weights = [], []

    for it in ocr_items:
        text, score = _get_text_score(it)
        if score < cfg.min_score:
            continue
        if cfg.require_text and not text.strip():
            continue
        if cfg.skip_digit_only and text.replace(",", "").replace(".", "").isdigit():
            continue

        poly = _get_poly(it)
        if poly is None:
            continue

        best_len, best_ang = 0.0, None
        for a,b in [(0,1),(1,2),(2,3),(3,0)]:
            L = np.linalg.norm(poly[b]-poly[a])
            if L > best_len:
                best_len = L
                best_ang = _edge_angle_deg(poly[a], poly[b])

        if best_ang is None or best_len < cfg.min_edge_len_px:
            continue

        angles.append(_normalize_angle(best_ang))
        weights.append(best_len * score)

    if not angles:
        return None

    idx = np.argsort(np.array(angles))
    angs = np.array(angles)[idx]
    ws = np.array(weights)[idx]
    cum = np.cumsum(ws)
    mid = cum[-1] * 0.5
    i = int(np.searchsorted(cum, mid))
    return float(angs[min(i, len(angs)-1)])

# ---------- apply deskew ----------
def deskew_image_and_items(
    image_bgr: np.ndarray,
    ocr_items: List[Any],
    cfg: DeskewFromOCRConfig,
) -> tuple[np.ndarray, dict]:

    h, w = image_bgr.shape[:2]
    angle = estimate_skew_angle_deg(ocr_items, cfg)

    meta = {
        "estimated_angle_deg": angle,
        "applied": False,
        "applied_angle_deg": 0.0,
        "min_abs_angle_deg": cfg.min_abs_angle_deg,
    }

    if angle is None or abs(angle) < cfg.min_abs_angle_deg:
        return image_bgr, meta

    apply = -angle
    M = cv2.getRotationMatrix2D((w/2, h/2), apply, 1.0)

    cos, sin = abs(M[0,0]), abs(M[0,1])
    nw, nh = int(h*sin + w*cos), int(h*cos + w*sin)
    M[0,2] += (nw/2)-(w/2)
    M[1,2] += (nh/2)-(h/2)

    rotated = cv2.warpAffine(
        image_bgr, M, (nw, nh),
        flags=cv2.INTER_CUBIC,
        borderValue=(255,255,255),
    )

    for it in ocr_items:
        poly = _get_poly(it)
        if poly is None:
            continue
        ones = np.ones((4,1), dtype=np.float32)
        pts = np.hstack([poly, ones])
        rot = (M @ pts.T).T

        it["poly"] = rot.round().astype(int).tolist()
        x1,y1 = int(rot[:,0].min()), int(rot[:,1].min())
        x2,y2 = int(rot[:,0].max()), int(rot[:,1].max())
        it["bbox"] = [x1,y1,x2,y2]

    meta["applied"] = True
    meta["applied_angle_deg"] = apply
    return rotated, meta

def deskew_image_and_polys(
    image_bgr: np.ndarray,
    items: list[dict],
    cfg: DeskewFromOCRConfig,
):
    h, w = image_bgr.shape[:2]

    angle = estimate_skew_angle_deg(items, cfg)
    meta = {
        "estimated_angle_deg": angle,
        "applied": False,
        "applied_angle_deg": 0.0,
        "min_abs_angle_deg": cfg.min_abs_angle_deg,
    }

    if angle is None or abs(angle) < cfg.min_abs_angle_deg:
        return image_bgr, items, meta

    # normalize (거꾸로 도는 거 방지)
    if angle > 90:
        angle -= 180
    if angle < -90:
        angle += 180

    apply = -float(angle)
    cx, cy = w / 2, h / 2
    M = cv2.getRotationMatrix2D((cx, cy), apply, 1.0)

    cos = abs(M[0, 0])
    sin = abs(M[0, 1])
    new_w = int(h * sin + w * cos)
    new_h = int(h * cos + w * sin)

    M[0, 2] += (new_w / 2) - cx
    M[1, 2] += (new_h / 2) - cy

    rotated_img = cv2.warpAffine(
        image_bgr,
        M,
        (new_w, new_h),
        flags=cv2.INTER_CUBIC,
        borderValue=(255, 255, 255),
    )

    out_items = []
    for it in items:
        it2 = dict(it)
        poly = _get_poly(it2)
        if poly is None:
            out_items.append(it2)
            continue

        ones = np.ones((4, 1), dtype=np.float32)
        pts = np.hstack([poly, ones])
        rot = (M @ pts.T).T

        it2["poly"] = rot.round().astype(int).tolist()
        it2["bbox"] = [
            int(rot[:, 0].min()),
            int(rot[:, 1].min()),
            int(rot[:, 0].max()),
            int(rot[:, 1].max()),
        ]
        out_items.append(it2)

    meta["applied"] = True
    meta["applied_angle_deg"] = apply
    print("deskew 되고있니..? ")

    return rotated_img, out_items, meta



def rotate_image_keep_size(img_bgr: np.ndarray, angle_deg: float) -> np.ndarray:
    """Rotate around center, keep same canvas size, replicate border."""
    h, w = img_bgr.shape[:2]
    M = cv2.getRotationMatrix2D((w / 2.0, h / 2.0), float(angle_deg), 1.0)
    return cv2.warpAffine(
        img_bgr,
        M,
        (w, h),
        flags=cv2.INTER_CUBIC,
        borderMode=cv2.BORDER_REPLICATE,
    )

def pick_ocr_image_path(ctx) -> str:
    # step2에서 OCR에 사용한 소스 이미지 경로 우선순위
    return (
        getattr(ctx.images, "rectified_path", None)
        or getattr(ctx.images, "cropped_path", None)
        or getattr(ctx.images, "input_path", None)
    )
