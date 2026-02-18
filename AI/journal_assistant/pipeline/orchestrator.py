from __future__ import annotations
from typing import Any, Dict

from AI.journal_assistant.pipeline.generator import generate_image, generate_image_with_ref
from AI.journal_assistant.pipeline.templates.map_template.run_map_template import run_map_template
from AI.journal_assistant.pipeline.templates.journal_template.run_journal_template import run_journal_template


def run_orchestrator(payload: Dict[str, Any]) -> bytes:
    template = payload.get("template") or {}

    print("ai 저널 진입 :: ", payload)


    # 너 payload가 template_id로 오면 이걸 쓰고, template_type도 지원
    ttype = template.get("template_type", template.get("template_id"))

    print("ttype :: ", ttype)

    try:
        ttype = int(ttype)
    except Exception:
        raise ValueError(f"Invalid template_type/template_id: {ttype}")

    if ttype == 1:
        out = run_journal_template(payload)
        if not out:
            raise RuntimeError("Journal generation failed (blocked or empty).")
        return out



    if ttype == 2:
        print("2번 진입")
        print("payload", payload)
        ref_bytes, prompt = run_map_template(payload)

        out = generate_image_with_ref(
            prompt=prompt,
            ref_image_bytes=ref_bytes,
            model="gemini-2.5-flash-image",
            ref_mime="image/png",
        )
        if not out:
            raise RuntimeError("Map generation failed (blocked or empty).")
        return out

    raise ValueError(f"Unknown template type: {ttype} (1=journal, 2=map)")




# from __future__ import annotations
# from typing import Any, Dict
#
# from AI.journal_assistant.pipeline.generator import generate_image, generate_image_with_ref
# from AI.journal_assistant.pipeline.templates.journal_template.journal_prompt import build_journal_prompt
# from AI.journal_assistant.pipeline.templates.map_template.run_map_template import run_map_template
#
#
# def run_orchestrator(payload: Dict[str, Any]) -> bytes:
#     template = payload.get("template") or {}
#
#     print("ai 저널 진입 :: ", payload)
#
#
#     # 너 payload가 template_id로 오면 이걸 쓰고, template_type도 지원
#     ttype = template.get("template_type", template.get("template_id"))
#
#     print("ttype :: ", ttype)
#
#     try:
#         ttype = int(ttype)
#     except Exception:
#         raise ValueError(f"Invalid template_type/template_id: {ttype}")
#
#     if ttype == 1:
#         prompt = build_journal_prompt(payload)
#         out = generate_image(prompt)
#         if not out:
#             raise RuntimeError("Journal generation failed (blocked or empty).")
#         return out
#
#
#
#     if ttype == 2:
#         print("2번 진입")
#         print("payload", payload)
#         ref_bytes, prompt = run_map_template(payload)
#
#         out = generate_image_with_ref(
#             prompt=prompt,
#             ref_image_bytes=ref_bytes,
#             model="gemini-2.5-flash-image",
#             ref_mime="image/png",
#         )
#         if not out:
#             raise RuntimeError("Map generation failed (blocked or empty).")
#         return out
#
#     raise ValueError(f"Unknown template type: {ttype} (1=journal, 2=map)")
