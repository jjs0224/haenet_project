from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional, Tuple, List

import cv2
import numpy as np

from .base import RectifyBackend, RectifyResult
from .doc_geometry import PerspectiveRectifyParams, find_document_quad, warp_perspective


@dataclass(frozen=True)
class DocUNetConfig:
    """
    Working menu-board rectification backend.

    Pipeline:
      1) (Optional) DocTR orientation predictor
      2) Apply inverse rotation (correction) to make upright
      3) OpenCV contour-based quad detection
      4) Perspective warp to fronto-parallel rectangle

    Controls:
      - min_orientation_confidence: confidence below this => treat as uncertain
      - prefer_fallback_when_low_conf: if uncertain, prefer heuristic/candidate selection
      - prefer_doctr_when_tie: if 0deg vs doctr_inverse are nearly equal, prefer doctr prior (optional)
      - tie_area_ratio: relative area difference threshold to consider a tie (0~1)
      - prefer_keep0_when_close_score_epsilon: if best_score - score(0deg) <= epsilon, keep 0deg (prevents 180 flip on near-ties)
    """
    params: PerspectiveRectifyParams = PerspectiveRectifyParams()
    strict_weights: bool = False

    enable_orientation: bool = True
    min_orientation_confidence: float = 0.90
    prefer_fallback_when_low_conf: bool = True

    # doctr tie preference (optional)
    prefer_doctr_when_tie: bool = False
    tie_area_ratio: float = 0.01  # 1% ?대궡硫??숇쪧

    # ?듭떖: 洹쇱냼李⑥씠硫?0???좎? (?대쾲 耳?댁뒪泥섎읆 0 vs 180???ъ떎???숇쪧?몃뜲 180??誘몄꽭?섍쾶 ?닿린??臾몄젣 諛⑹?)
    prefer_keep0_when_close_score_epsilon: float = 50.0


class DocUNetBackend(RectifyBackend):
    """
    docunet backend: DocTR orientation (optional) + OpenCV perspective rectify.

    Key decisions:
      - The predictor output is interpreted as "current document orientation".
        Therefore we apply the inverse rotation as the correction:
          correction_angle = (-pred_angle) % 360

      - If confidence is low or parsing fails, we fall back to heuristic candidate rotations
        and select the best one by document quad detection quality.

      - SAFE fallback: if no candidate produces a valid quad, do NOT rotate.
    """

    name = "docunet"

    def __init__(self, device: str = "cpu", model_dir: Optional[str] = None, config: Optional[DocUNetConfig] = None):
        super().__init__(device=device, model_dir=model_dir)
        self.config = config or DocUNetConfig()

        # torch (future DL weights path)
        self._torch = None
        self._torch_import_error: Optional[BaseException] = None
        self._model = None
        self._weights_path: Optional[Path] = None

        try:
            import torch as _torch  # type: ignore
        except Exception as e:
            self._torch = None
            self._torch_import_error = e
        else:
            self._torch = _torch
            self._torch_import_error = None

        # doctr (orientation)
        self._doctr = None
        self._doctr_import_error: Optional[BaseException] = None
        self._orientation_predictor = None

        try:
            import doctr as _doctr  # type: ignore
        except Exception as e:
            self._doctr = None
            self._doctr_import_error = e
        else:
            self._doctr = _doctr
            self._doctr_import_error = None

        self._models_ready: bool = False

    # -------------------------
    # basic helpers
    # -------------------------
    @staticmethod
    def _validate_image(image_bgr: np.ndarray) -> Tuple[int, int]:
        if not isinstance(image_bgr, np.ndarray):
            raise TypeError(f"image_bgr must be np.ndarray, got {type(image_bgr)}")
        if image_bgr.ndim != 3 or image_bgr.shape[2] != 3:
            raise ValueError(f"image_bgr must have shape (H, W, 3). Got {image_bgr.shape}")
        h, w = int(image_bgr.shape[0]), int(image_bgr.shape[1])
        if h < 2 or w < 2:
            raise ValueError(f"image_bgr too small: {(h, w)}")
        return h, w

    @staticmethod
    def _bgr_to_rgb(image_bgr: np.ndarray) -> np.ndarray:
        return image_bgr[:, :, ::-1].copy()

    @staticmethod
    def _apply_rotation_bgr(image_bgr: np.ndarray, angle: int) -> np.ndarray:
        a = angle % 360
        if a == 0:
            return image_bgr
        if a == 90:
            return cv2.rotate(image_bgr, cv2.ROTATE_90_CLOCKWISE)
        if a == 180:
            return cv2.rotate(image_bgr, cv2.ROTATE_180)
        if a == 270:
            return cv2.rotate(image_bgr, cv2.ROTATE_90_COUNTERCLOCKWISE)
        return image_bgr

    # -------------------------
    # doctr output normalization/parsing
    # -------------------------
    @staticmethod
    def _normalize_angle(val: Any) -> Optional[int]:
        """Normalize angle-like values into one of {0, 90, 180, 270}. Supports -90 -> 270."""
        if val is None:
            return None

        if isinstance(val, (int, np.integer, float, np.floating)):
            v = int(round(float(val)))
            v = v % 360
            return v if v in (0, 90, 180, 270) else None

        if isinstance(val, str):
            s = val.strip().lower()
            mapping = {
                "0": 0, "90": 90, "180": 180, "270": 270,
                "-90": 270,
                "upright": 0, "rot90": 90, "rot180": 180, "rot270": 270,
            }
            if s in mapping:
                return mapping[s]
            for key in ("0", "90", "180", "270", "-90"):
                if key in s:
                    return mapping.get(key, None)

        return None

    @staticmethod
    def _angle_from_doctr_output(out: Any) -> Optional[int]:
        """
        Extract normalized angle in {0,90,180,270} from various doctr outputs.

        Known page_orientation_predictor format (observed):
          [[class_id], [angle_deg], [confidence]]
          e.g. [[1], [-90], [0.9]]
        """
        if isinstance(out, dict):
            for k in ("angle", "orientation", "rotation"):
                if k in out:
                    return DocUNetBackend._normalize_angle(out[k])

        if isinstance(out, (list, tuple)) and len(out) == 3:
            try:
                angle_part = out[1]
                if isinstance(angle_part, (list, tuple, np.ndarray)) and len(angle_part) > 0:
                    angle_part = angle_part[0]
                ang = DocUNetBackend._normalize_angle(angle_part)
                if ang is not None:
                    return ang
            except Exception:
                pass

        if isinstance(out, (list, tuple)) and len(out) > 0:
            first = out[0]
            ang = DocUNetBackend._angle_from_doctr_output(first)
            if ang is not None:
                return ang

            if len(out) == 4 and all(isinstance(x, (int, float, np.floating, np.integer)) for x in out):
                arr = np.array(out, dtype=float)
                idx = int(arr.argmax())
                return [0, 90, 180, 270][idx]

        if isinstance(out, np.ndarray):
            arr = out
            if arr.ndim == 2 and arr.shape[0] == 1:
                arr = arr[0]
            if arr.ndim == 1 and arr.shape[0] == 4:
                idx = int(np.argmax(arr))
                return [0, 90, 180, 270][idx]

        return DocUNetBackend._normalize_angle(out)

    @staticmethod
    def _confidence_from_doctr_output(out: Any) -> Optional[float]:
        """Extract confidence from page_orientation_predictor output: [[cls], [angle], [conf]]"""
        if isinstance(out, (list, tuple)) and len(out) == 3:
            try:
                conf_part = out[2]
                if isinstance(conf_part, (list, tuple, np.ndarray)) and len(conf_part) > 0:
                    conf_part = conf_part[0]
                return float(conf_part)
            except Exception:
                return None
        return None

    # -------------------------
    # weights discovery (future DL path)
    # -------------------------
    def _resolve_weights_path(self) -> Optional[Path]:
        if not self.model_dir:
            return None
        p = Path(self.model_dir)
        if p.is_file():
            return p
        if not p.exists():
            return None
        candidates = [p / "docunet.pth", p / "docunet.pt", p / "best.pth", p / "model.pth"]
        for c in candidates:
            if c.exists() and c.is_file():
                return c
        found = sorted(list(p.glob("*.pth")) + list(p.glob("*.pt")))
        return found[0] if found else None

    # -------------------------
    # lazy init (doctr predictor)
    # -------------------------
    def _lazy_init_models(self) -> Dict[str, Any]:
        if self._models_ready:
            return {
                "init": "cached",
                "weights_path": str(self._weights_path) if self._weights_path else None,
                "torch_available": self._torch is not None,
                "doctr_available": self._doctr is not None,
                "orientation_predictor_available": self._orientation_predictor is not None,
            }

        self._weights_path = self._resolve_weights_path()

        init_meta: Dict[str, Any] = {
            "init": "opencv_perspective_ready",
            "weights_path": str(self._weights_path) if self._weights_path else None,
            "torch_available": self._torch is not None,
            "torch_import_error": repr(self._torch_import_error) if self._torch_import_error else None,
            "doctr_available": self._doctr is not None,
            "doctr_import_error": repr(self._doctr_import_error) if self._doctr_import_error else None,
        }

        if self.config.enable_orientation and self._doctr is not None:
            try:
                from doctr.models import page_orientation_predictor  # type: ignore
                self._orientation_predictor = page_orientation_predictor(pretrained=True)
                init_meta["orientation_predictor_name"] = "page_orientation_predictor"
            except Exception as e1:
                try:
                    from doctr.models import crop_orientation_predictor  # type: ignore
                    self._orientation_predictor = crop_orientation_predictor(pretrained=True)
                    init_meta["orientation_predictor_name"] = "crop_orientation_predictor"
                except Exception as e2:
                    self._orientation_predictor = None
                    init_meta["orientation_predictor_error"] = {
                        "page_orientation_predictor": repr(e1),
                        "crop_orientation_predictor": repr(e2),
                    }

        self._models_ready = True
        init_meta["orientation_predictor_available"] = self._orientation_predictor is not None
        return init_meta

    # -------------------------
    # orientation correction (confidence + candidate selection)
    # -------------------------
    def _maybe_apply_orientation(self, image_bgr: np.ndarray) -> Tuple[np.ndarray, Dict[str, Any]]:
        """
        Orientation correction with:
          - doctr prediction parsing (angle + confidence) if available
          - confidence thresholding
          - SAFE fallback candidate selection (0/90/180/270) by quad detection quality
          - KEY FIX: if best_score is only slightly better than 0deg (<= epsilon), keep 0deg
        """
        meta: Dict[str, Any] = {
            "enabled": bool(self.config.enable_orientation),
            "applied": False,
            "predictor_available": self._orientation_predictor is not None,
        }

        if not self.config.enable_orientation:
            meta["reason"] = "orientation disabled"
            meta["correction_angle"] = 0
            return image_bgr, meta

        def _textline_score(img_bgr: np.ndarray) -> float:
            """OCR ?놁씠 '媛濡?湲以?援ъ“'瑜??좏샇?섎뒗 蹂댁“ ?먯닔."""
            try:
                gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
                h, w = gray.shape[:2]
                max_side = 900
                m = max(h, w)
                if m > max_side:
                    r = max_side / float(m)
                    gray = cv2.resize(gray, (int(w * r), int(h * r)), interpolation=cv2.INTER_AREA)

                gx = cv2.Sobel(gray, cv2.CV_32F, 1, 0, ksize=3)
                gy = cv2.Sobel(gray, cv2.CV_32F, 0, 1, ksize=3)
                mag = cv2.magnitude(gx, gy)

                row = np.sum(mag, axis=1)
                col = np.sum(mag, axis=0)

                vr = float(np.var(row))
                vc = float(np.var(col))
                return (vr + 1e-6) / (vc + 1e-6)
            except Exception:
                return 0.0

        def score_rotation(img: np.ndarray) -> Tuple[float, Dict[str, Any]]:
            quad, find_meta = find_document_quad(img, self.config.params)
            if quad is None:
                return 0.0, {"found": False, "find": find_meta}

            best_area = float(find_meta.get("best_area", 0.0))
            tls = float(_textline_score(img))

            # ?덉젙?? best_area媛 二쇰룄?섍퀬, tls???숈젏 洹쇱쿂?먯꽌留??곹뼢
            alpha = 1e5
            score = 1e9 + best_area + (alpha * tls)

            return score, {"found": True, "find": find_meta, "textline_score": tls}

        # ---- doctr prediction (optional) ----
        pred_angle: Optional[int] = None
        pred_conf: Optional[float] = None
        doctr_correction: Optional[int] = None
        uncertain: bool = False

        if self._orientation_predictor is not None:
            try:
                rgb = self._bgr_to_rgb(image_bgr)
                pred_out = self._orientation_predictor([rgb])

                meta["raw_output_type"] = type(pred_out).__name__
                try:
                    meta["raw_output_preview"] = str(pred_out)[:500]
                except Exception:
                    meta["raw_output_preview"] = "<unserializable>"

                pred_angle = self._angle_from_doctr_output(pred_out)
                pred_conf = self._confidence_from_doctr_output(pred_out)

                meta["angle"] = pred_angle
                meta["confidence"] = pred_conf

                if pred_angle is None:
                    uncertain = True
                    meta["uncertain_reason"] = "angle_parse_failed"
                elif pred_conf is not None and pred_conf < float(self.config.min_orientation_confidence):
                    uncertain = True
                    meta["uncertain_reason"] = f"low_confidence<{self.config.min_orientation_confidence}"

                if pred_angle in (0, 90, 180, 270):
                    # predictor??"?꾩옱 諛⑺뼢"?대씪怨??댁꽍 -> inverse rotation??correction
                    doctr_correction = int((-int(pred_angle)) % 360)

            except Exception as e:
                # predictor媛 "?덉?留? ?ㅽ뙣 -> fallback
                meta["predictor_error"] = repr(e)
                meta["predictor_available"] = False
                pred_angle = None
                pred_conf = None
                doctr_correction = None
                uncertain = True

        # ---- build candidates (always include 0 first) ----
        candidates: List[Tuple[int, str]] = [(0, "keep_0deg")]

        # doctr correction ?꾨낫瑜?0 ?ㅼ쓬???곗꽑 ?ｋ릺, 以묐났 ?쒓굅
        if doctr_correction in (0, 90, 180, 270) and doctr_correction != 0:
            candidates.append((int(doctr_correction), "doctr_inverse"))

        # ?섎㉧吏 90/180/270 梨꾩슦湲?
        for ang in (90, 180, 270):
            if all(c[0] != ang for c in candidates):
                candidates.append((ang, f"rot{ang}"))

        # ---- score candidates safely ----
        scored: List[Dict[str, Any]] = []
        best_score = -1.0
        best_ang = 0
        best_tag = "keep_0deg"
        best_detail: Dict[str, Any] = {}
        all_failed = True

        score0: float = 0.0
        found0: bool = False

        for ang, tag in candidates:
            rotated_try = self._apply_rotation_bgr(image_bgr, int(ang))
            s, detail = score_rotation(rotated_try)
            found = bool(detail.get("found", False))
            if found:
                all_failed = False

            row = {
                "angle": int(ang),
                "tag": tag,
                "score": float(s),
                "found": found,
                "best_area": float(detail.get("find", {}).get("best_area", 0.0)),
                "textline_score": float(detail.get("textline_score", 0.0)),
            }
            scored.append(row)

            if int(ang) == 0:
                score0 = float(s)
                found0 = found

            # 湲곕낯 best ?좏깮 (?숈젏?대㈃ 0???곗꽑)
            if (s > best_score) or (s == best_score and int(ang) == 0 and best_ang != 0):
                best_score = float(s)
                best_ang = int(ang)
                best_tag = tag
                best_detail = detail

        # SAFETY: 紐⑤몢 ?ㅽ뙣硫??뚯쟾?섏? ?딆쓬
        if all_failed or best_score <= 0.0:
            meta["fallback"] = {
                "applied": False,
                "chosen": {"angle": 0, "tag": "no_rotation_all_candidates_failed"},
                "candidates": candidates,
                "scored": scored,
                "scoring": {"all_failed": True},
            }
            meta["correction_angle"] = 0
            meta["applied"] = False
            meta["reason"] = (
                "fallback_disabled_all_candidates_failed"
                if meta.get("predictor_available", False)
                else "fallback_disabled_all_candidates_failed_no_predictor"
            )
            return image_bgr, meta

        # ?듭떖 FIX: best媛 0蹂대떎 "洹쇱냼?섍쾶" 醫뗭쑝硫?0 ?좎?
        # (?뱁엳 predictor ?놁쓣 ??0/180???ъ떎???숈씪?쒕뜲 area 1~???쎌? 李⑥씠濡?180 ?좏깮?섎뒗 臾몄젣 諛⑹?)
        # Guard only for low-confidence "upright-like" predictions (0/180).
        # If low-confidence predicts 90/270, let candidate scoring decide rotation.
        low_conf_guard = (
            bool(meta.get("predictor_available", False))
            and isinstance(pred_conf, (int, float))
            and (float(pred_conf) < float(self.config.min_orientation_confidence))
            and (pred_angle in (0, 180))
        )
        if low_conf_guard:
            best_ang = 0
            best_tag = "keep_0deg_low_confidence_guard"
            best_detail = {
                "guard": "low_confidence_keep0",
                "confidence": float(pred_conf),
                "min_orientation_confidence": float(self.config.min_orientation_confidence),
            }
        elif found0:
            epsilon = float(self.config.prefer_keep0_when_close_score_epsilon)
            if (best_ang != 0) and ((best_score - score0) <= epsilon):
                best_ang = 0
                best_tag = "keep_0deg_close_score"
                best_detail = {"keep0_epsilon": epsilon, "best_minus_0": float(best_score - score0)}
        # ?좏깮?? 0deg vs doctr_inverse 硫댁쟻??嫄곗쓽 媛숈쑝硫?doctr ?곗꽑 (?듭뀡 耳곗쓣 ?뚮쭔)
        if (
            bool(self.config.prefer_doctr_when_tie)
            and (doctr_correction is not None)
            and (pred_conf is not None)
            and (pred_conf >= float(self.config.min_orientation_confidence))
        ):
            areas = {r["angle"]: float(r.get("best_area", 0.0)) for r in scored if r.get("found", False)}
            if 0 in areas and int(doctr_correction) in areas:
                a0 = areas[0]
                ad = areas[int(doctr_correction)]
                denom = max(a0, ad, 1e-6)
                rel_diff = abs(a0 - ad) / denom
                if rel_diff <= float(self.config.tie_area_ratio):
                    best_ang = int(doctr_correction)
                    best_tag = "doctr_inverse_tie_break"
                    best_detail = {
                        "tie_break": {
                            "rel_diff": rel_diff,
                            "area_0deg": a0,
                            "area_doctr_inverse": ad,
                            "tie_area_ratio": float(self.config.tie_area_ratio),
                        }
                    }

        rotated = self._apply_rotation_bgr(image_bgr, best_ang)

        meta["fallback"] = {
            "applied": bool(best_ang != 0),
            "chosen": {"angle": best_ang, "tag": best_tag},
            "candidates": candidates,
            "scored": scored,
            "scoring": best_detail,
        }
        meta["correction_angle"] = best_ang
        meta["applied"] = bool(best_ang != 0)

        # reason 臾몄옄?댁? 湲곗〈 meta ?ㅽ??쇱쓣 ?좎?
        if meta.get("predictor_available", False):
            if low_conf_guard:
                meta["reason"] = "doctr_low_confidence -> keep_0deg_guard"
            elif pred_angle is not None and not uncertain and pred_conf is not None and pred_conf >= float(self.config.min_orientation_confidence):
                meta["reason"] = "used_fallback_candidate_selection_safe"  # (기존과 동일 톤 유지)
            else:
                meta["reason"] = "doctr_uncertain -> fallback_candidate_selection"
        else:
            meta["reason"] = "used_fallback_candidate_selection_safe_no_predictor"

        return rotated, meta

    # -------------------------
    # public
    # -------------------------
    def rectify(self, image_bgr: np.ndarray) -> RectifyResult:
        h, w = self._validate_image(image_bgr)
        init_meta = self._lazy_init_models()

        meta: Dict[str, Any] = {
            "backend": self.name,
            "device": self.device,
            "model_dir": self.model_dir,
            "input_shape": [h, w],
            "init": init_meta,
            "applied": False,
            "method": "orientation_then_opencv_perspective",
            "orientation": {},
            "opencv": {
                "params": {
                    "canny1": self.config.params.canny1,
                    "canny2": self.config.params.canny2,
                    "dilate_iter": self.config.params.dilate_iter,
                    "approx_eps_ratio": self.config.params.approx_eps_ratio,
                    "min_area_ratio": self.config.params.min_area_ratio,
                    "border": self.config.params.border,
                }
            },
        }

        if self.config.strict_weights and self._weights_path is None:
            raise RuntimeError(
                "DocUNet strict mode: weights were not found. "
                "Provide --model_dir pointing to a weights file or directory."
            )

        # 1) orientation correction
        oriented, orient_meta = self._maybe_apply_orientation(image_bgr)
        meta["orientation"] = orient_meta

        # 2) perspective rectify on oriented image
        quad, find_meta = find_document_quad(oriented, self.config.params)
        meta["opencv"]["find"] = find_meta

        if quad is None:
            meta["warning"] = "No document-like quadrilateral found; returning oriented image."
            meta["applied"] = bool(orient_meta.get("applied"))
            meta["output_shape"] = [int(oriented.shape[0]), int(oriented.shape[1])]
            return RectifyResult(image=oriented, meta=meta)

        try:
            warped, warp_meta = warp_perspective(oriented, quad, self.config.params)
            meta["opencv"]["warp"] = warp_meta
            meta["applied"] = True
            meta["output_shape"] = [int(warped.shape[0]), int(warped.shape[1])]
            return RectifyResult(image=warped, meta=meta)
        except Exception as e:
            meta["warning"] = "Perspective warp failed; returning oriented image."
            meta["error"] = repr(e)
            meta["applied"] = bool(orient_meta.get("applied"))
            meta["output_shape"] = [int(oriented.shape[0]), int(oriented.shape[1])]
            return RectifyResult(image=oriented, meta=meta)

