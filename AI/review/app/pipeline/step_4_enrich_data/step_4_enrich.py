from typing import Dict
from AI.review.app.pipeline.step_4_enrich_data.run_enrich_data import enrich_data
from AI.review.app.domain.schemas import PipelineContext


def run_step4_enrich(ctx: PipelineContext, *, naver_cfg: Dict, gemini_api_key: str) -> PipelineContext:
    result = enrich_data(
        phone=ctx.extracted.phone,
        lines=ctx.normalize.lines,
        menu_ko=ctx.extracted.menu_ko,
        naver_cfg=naver_cfg,
        gemini_api_key=gemini_api_key,
    )

    if result["store"]:
        ctx.store.store_name = result["store"]["name_ko"]
        ctx.store.store_name_en = result["store"]["name_en"]
        ctx.store.address = result["store"].get("address")
        ctx.store.city = result["store"].get("city")
        ctx.store.coords = result["store"].get("coords")

    ctx.extracted.menu_en = [
        m["name_en"] for m in result["menu"] if m["name_en"] is not None
    ]

    if ctx.mode == "debug":
        ctx.debug.enrich = result

    return ctx
