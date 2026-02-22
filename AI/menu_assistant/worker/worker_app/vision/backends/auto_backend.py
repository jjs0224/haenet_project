from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any, Dict, Optional, Tuple

import numpy as np

from .base import RectifyBackend, RectifyResult
from .docunet_backend import DocUNetBackend, DocUNetConfig
from .dewarpnet_backend import DewarpNetBackend, DewarpNetConfig
from ..metrics.dewarp_triggers import compute_dewarp_trigger


@dataclass(frozen=True)
class AutoConfig:
    """
    Auto backend policy:
      - run DocUNet first (fast + stable)
      - if trigger score is high AND dewarp backend is ready -> run DewarpNet
      - select best output with conservative acceptance rules
    """
    # trigger threshold: higher => less often dewarp (safer)
    trigger_threshold: float = 0.65

    # require objective improvement to accept dewarp result
    min_score_gain: float = 0.10

    # if DocUNet couldn't find quad, allow DewarpNet as "rescue" when trigger is high
    allow_dewarp_when_docunet_failed: bool = True

    # conservative rotation gate for auto mode:
    # if DocUNet orientation looks unreliable, rerun DocUNet with orientation disabled.
    conservative_rotation_gate: bool = True
    min_rotation_confidence: float = 0.97
    min_rotation_score_margin: float = 300.0
    disallow_180_without_very_high_conf: bool = True
    min_conf_for_180: float = 0.995

    # Allow trusting DocUNet fallback rotation even when doctr confidence is low,
    # if objective score margin over 0deg is large enough.
    allow_fallback_rotation_with_strong_margin: bool = True
    min_fallback_rotation_score_margin: float = 2000.0


class AutoBackend(RectifyBackend):
    name = "auto"

    def __init__(
        self,
        device: str = "cpu",
        model_dir: Optional[str] = None,
        docunet: Optional[DocUNetConfig] = None,
        dewarpnet: Optional[DewarpNetConfig] = None,
        auto: Optional[AutoConfig] = None,
    ):
        super().__init__(device=device, model_dir=model_dir)
        self.docunet_cfg = docunet or DocUNetConfig()
        self.dewarpnet_cfg = dewarpnet or DewarpNetConfig()
        self.auto_cfg = auto or AutoConfig()

        # Sub-backends
        self._docunet = DocUNetBackend(device=device, model_dir=model_dir, config=self.docunet_cfg)
        self._dewarpnet = DewarpNetBackend(device=device, model_dir=model_dir, config=self.dewarpnet_cfg)

    def _rotation_is_trusted(self, doc_meta: Dict[str, Any]) -> bool:
        orient = (doc_meta or {}).get("orientation", {}) or {}

        # No orientation rotation was applied, so there is nothing to distrust.
        if not bool(orient.get("applied", False)):
            return True

        try:
            angle = int(orient.get("correction_angle", 0) or 0)
        except Exception:
            return False

        scored = (((orient.get("fallback", {}) or {}).get("scored", [])) or [])
        score0 = None
        score_angle = None
        for row in scored:
            try:
                a = int(row.get("angle", -1))
                s = float(row.get("score", 0.0))
            except Exception:
                continue
            if a == 0:
                score0 = s
            if a == angle:
                score_angle = s

        def _fallback_margin_strong() -> bool:
            if not self.auto_cfg.allow_fallback_rotation_with_strong_margin:
                return False
            if angle == 0:
                return False
            if (score0 is None) or (score_angle is None):
                return False
            return (score_angle - score0) >= float(self.auto_cfg.min_fallback_rotation_score_margin)

        conf = orient.get("confidence", None)
        predictor_available = bool(orient.get("predictor_available", False))
        if (not predictor_available) or (not isinstance(conf, (int, float))):
            return _fallback_margin_strong()

        conf = float(conf)
        if conf < float(self.auto_cfg.min_rotation_confidence):
            return _fallback_margin_strong()

        if (
            self.auto_cfg.disallow_180_without_very_high_conf
            and angle == 180
            and conf < float(self.auto_cfg.min_conf_for_180)
        ):
            return False

        if (score0 is not None) and (score_angle is not None):
            if (score_angle - score0) < float(self.auto_cfg.min_rotation_score_margin):
                # Optional escape hatch: trust strong fallback evidence even if doctr confidence is low.
                if _fallback_margin_strong():
                    return True
                return False

        return True

    def rectify(self, image_bgr: np.ndarray) -> RectifyResult:
        # 1) DocUNet first
        res_u = self._docunet.rectify(image_bgr)
        docunet_meta_first_pass = res_u.meta

        rotation_guard: Dict[str, Any] = {}
        if self.auto_cfg.conservative_rotation_gate:
            trusted = self._rotation_is_trusted(res_u.meta)
            rotation_guard = {
                "enabled": True,
                "trusted": bool(trusted),
            }
            if not trusted:
                cfg_no_rot = replace(self.docunet_cfg, enable_orientation=False)
                res_u = DocUNetBackend(device=self.device, model_dir=self.model_dir, config=cfg_no_rot).rectify(image_bgr)
                rotation_guard["rerun_without_orientation"] = True
                rotation_guard["reason"] = "docunet_orientation_not_trusted"
            else:
                rotation_guard["rerun_without_orientation"] = False
        else:
            rotation_guard = {"enabled": False}

        # 2) Compute trigger score on DocUNet output image (or input if docunet failed)
        trig = compute_dewarp_trigger(res_u.image)

        meta: Dict[str, Any] = {
            "backend": self.name,
            "device": self.device,
            "model_dir": self.model_dir,
            "auto": {
                "policy": {
                    "trigger_threshold": self.auto_cfg.trigger_threshold,
                    "min_score_gain": self.auto_cfg.min_score_gain,
                    "allow_dewarp_when_docunet_failed": self.auto_cfg.allow_dewarp_when_docunet_failed,
                    "conservative_rotation_gate": self.auto_cfg.conservative_rotation_gate,
                    "min_rotation_confidence": self.auto_cfg.min_rotation_confidence,
                    "min_rotation_score_margin": self.auto_cfg.min_rotation_score_margin,
                    "disallow_180_without_very_high_conf": self.auto_cfg.disallow_180_without_very_high_conf,
                    "min_conf_for_180": self.auto_cfg.min_conf_for_180,
                    "allow_fallback_rotation_with_strong_margin": self.auto_cfg.allow_fallback_rotation_with_strong_margin,
                    "min_fallback_rotation_score_margin": self.auto_cfg.min_fallback_rotation_score_margin,
                },
                "trigger": trig,
                "selected": "docunet",
                "decision": {},
                "rotation_guard": rotation_guard,
            },
            "docunet_meta_first_pass": docunet_meta_first_pass,
            "docunet_meta": res_u.meta,
            "dewarpnet_meta": None,
        }

        # Determine DocUNet success signal (quad found?)
        docunet_quad_found = False
        try:
            docunet_quad_found = bool(res_u.meta.get("opencv", {}).get("find", {}).get("found", False))
        except Exception:
            docunet_quad_found = False

        # 3) Decide whether to attempt DewarpNet
        dewarp_ready = bool(getattr(self._dewarpnet, "ready", False))
        should_try = (trig["score"] >= self.auto_cfg.trigger_threshold) and dewarp_ready

        if (not docunet_quad_found) and self.auto_cfg.allow_dewarp_when_docunet_failed and dewarp_ready:
            # “rescue” path: if docunet failed and trigger says "texty/curvy", allow trying dewarp even if threshold not met
            should_try = should_try or (trig["score"] >= max(0.45, self.auto_cfg.trigger_threshold - 0.15))

        meta["auto"]["decision"]["docunet_quad_found"] = docunet_quad_found
        meta["auto"]["decision"]["dewarp_ready"] = dewarp_ready
        meta["auto"]["decision"]["should_try_dewarpnet"] = should_try

        if not should_try:
            # Keep DocUNet result
            return RectifyResult(image=res_u.image, meta=meta)

        # 4) Try DewarpNet on DocUNet output (preferred) to reduce orientation/perspective noise
        res_d = self._dewarpnet.rectify(res_u.image)
        meta["dewarpnet_meta"] = res_d.meta

        # 5) Compare & select (conservative)
        # We recompute trigger score on dewarped output; if it improves, it likely reduced curvature/line distortion
        trig_d = compute_dewarp_trigger(res_d.image)
        meta["auto"]["trigger_dewarpnet"] = trig_d

        gain = trig_d["score"] - trig["score"]
        meta["auto"]["decision"]["score_gain"] = gain

        # Accept only if objectively better by margin, or if docunet failed and dewarp looks reasonable
        accept = False
        if gain >= self.auto_cfg.min_score_gain:
            accept = True
        elif (not docunet_quad_found) and trig_d["score"] >= trig["score"] and trig_d["score"] >= 0.55:
            accept = True

        meta["auto"]["decision"]["accept_dewarpnet"] = accept

        if accept:
            meta["auto"]["selected"] = "dewarpnet"
            return RectifyResult(image=res_d.image, meta=meta)

        # Otherwise keep DocUNet
        return RectifyResult(image=res_u.image, meta=meta)
