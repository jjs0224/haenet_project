from __future__ import annotations
import json
from pathlib import Path
from typing import Any, Dict, Tuple, List
from io import BytesIO

from PIL import Image

from AI.journal_assistant.pipeline.templates.map_template.pin_overlay import render_pinned_map_bytes
from AI.journal_assistant.pipeline.templates.map_template.map_prompt import build_map_poster_prompt_with_ref

ASSETS_DIR = Path(__file__).parent / "assets"
BASE_MAP = ASSETS_DIR / "map_resize.png"
CALIB = ASSETS_DIR / "kakao_map_calibration.json"
PIN_ICON = ASSETS_DIR / "pin.png"


def compose_ref_canvas(
        pinned_map_bytes: bytes,
        *,
        canvas_w: int = 1200,
        canvas_h: int = 820,
        map_w: int = 900,
        map_h: int = 520,
        map_bottom_margin: int = 40,
) -> Tuple[bytes, Dict[str, int]]:
    """
    pinned map(900x520)을 캔버스(1200x820) 위에 붙여서 ref로 만들기.
    return: (ref_png_bytes, layout)
    """
    base = Image.new("RGBA", (canvas_w, canvas_h), (245, 245, 245, 255))
    m = Image.open(BytesIO(pinned_map_bytes)).convert("RGBA")

    if m.size != (map_w, map_h):
        m = m.resize((map_w, map_h), Image.LANCZOS)

    left = (canvas_w - map_w) // 2
    top = canvas_h - map_bottom_margin - map_h

    base.alpha_composite(m, dest=(left, top))

    out = BytesIO()
    base.save(out, format="PNG")

    layout = {
        "canvas_w": canvas_w,
        "canvas_h": canvas_h,
        "map_left": left,
        "map_top": top,
        "map_w": map_w,
        "map_h": map_h,
    }
    return out.getvalue(), layout


def run_map_template(payload: Dict[str, Any]) -> Tuple[bytes, str]:
    """
    Returns:
      ref_image_bytes: (캔버스+지도+핀) PNG bytes
      prompt: Gemini 편집 프롬프트
    """
    reviews = payload.get("reviews", [])

    # 최정규 1111
    # print("temp2 payload dep1 :: ", payload.get("reviews"))
    # locations = [r["location"] for r in payload.get("reviews", []) if r.get("location")]
    #
    # print("location :: ", locations)

    # 1) reviews의 location을 coords로 변환해서 심기
    for r in reviews:
        loc = r.get("location")
        if not loc:
            continue

        # location이 문자열 JSON이면 파싱
        if isinstance(loc, str):
            try:
                loc = json.loads(loc)  # ['1284216484', '348857549']
            except Exception:
                continue

        # loc이 [x, y] 형태면 coords로 변환
        if isinstance(loc, (list, tuple)) and len(loc) >= 2:
            x, y = loc[0], loc[1]
            if x is None or y is None:
                continue

            # orchestrator가 체크하는 조건: r.get("coords") and coords.x and coords.y
            r["coords"] = {"x": str(x), "y": str(y)}

    # (원하면 디버그)
    locations = [r.get("location") for r in reviews if r.get("location")]
    print("location :: ", locations)

    places: List[Dict[str, Any]] = payload.get("places") or [
        {"coords": r["coords"], "label": str(i + 1)}
        for i, r in enumerate(reviews)
        if r.get("coords") and r["coords"].get("x") and r["coords"].get("y")
    ]
    if not places:
        raise ValueError("No coordinates found to pin on the map.")

    print("최종 위치 값 :: ", places)

    pinned_map_bytes = render_pinned_map_bytes(
        base_image_path=BASE_MAP,
        calib_json_path=CALIB,
        places_raw=places,
        pin_icon_path=PIN_ICON,
        pin_width_px=20,
    )

    ref_bytes, layout = compose_ref_canvas(pinned_map_bytes)

    # ✅ ref 위에 “꾸미기만” 하도록 프롬프트 생성 (지도/핀 절대 변경 금지)
    prompt = build_map_poster_prompt_with_ref(payload, **layout)

    return ref_bytes, prompt