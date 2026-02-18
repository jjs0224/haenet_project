from __future__ import annotations

import os
from typing import Optional, List, Any
from dotenv import load_dotenv
from google import genai
from google.genai import types

load_dotenv()


def _get_client() -> genai.Client:
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("Missing env var: GEMINI_API_KEY")
    return genai.Client(api_key=api_key)

#for journal
def generate_image(
    prompt: str,
    *,
    model: str = "gemini-2.5-flash-image",
) -> Optional[bytes]:
    client = _get_client()

    try:
        response = client.models.generate_content(
            model=model,
            contents=prompt,
            config=types.GenerateContentConfig(response_modalities=["IMAGE"]),
        )
    except Exception as e:
        print("[generate_image] API call failed:", repr(e))
        raise

    if not response.candidates or not response.candidates[0].content:
        return None

    for part in response.candidates[0].content.parts:
        if getattr(part, "inline_data", None):
            return part.inline_data.data

    return None

#for map
def generate_image_with_ref(
    prompt: str,
    ref_image_bytes: bytes,
    *,
    model: str = "gemini-2.5-flash-image",
    ref_mime: str = "image/png",
) -> Optional[bytes]:
    client = _get_client()

    # SDK 버전별 안전 처리: Part.from_bytes가 없으면 inline_data 형태로 넣기
    try:
        ref_part = types.Part.from_bytes(data=ref_image_bytes, mime_type=ref_mime)
    except Exception:
        ref_part = types.Part(
            inline_data=types.Blob(data=ref_image_bytes, mime_type=ref_mime)
        )

    contents: List[Any] = [ref_part, prompt]

    response = client.models.generate_content(
        model=model,
        contents=contents,
        config=types.GenerateContentConfig(response_modalities=["IMAGE"]),
    )

    if not response.candidates or not response.candidates[0].content:
        return None

    for part in response.candidates[0].content.parts:
        if getattr(part, "inline_data", None):
            return part.inline_data.data
    return None

# generator.py 맨 아래에 추가

def generate_text(
    prompt: str,
    *,
    model: str = "gemini-2.5-flash",
) -> str:
    client = _get_client()

    try:
        response = client.models.generate_content(
            model=model,
            contents=prompt,
        )
    except Exception as e:
        print("[generate_text] API call failed:", repr(e))
        raise

    text = getattr(response, "text", None)
    if text:
        return text.strip()

    # fallback
    if response.candidates and response.candidates[0].content:
        parts = response.candidates[0].content.parts or []
        out = []
        for p in parts:
            t = getattr(p, "text", None)
            if t:
                out.append(t)
        return "\n".join(out).strip()

    return ""



# from __future__ import annotations
#
# import os
# from typing import Optional, List, Any
# from dotenv import load_dotenv
# from google import genai
# from google.genai import types
#
# load_dotenv()
#
#
# def _get_client() -> genai.Client:
#     api_key = os.getenv("GEMINI_API_KEY")
#     if not api_key:
#         raise RuntimeError("Missing env var: GEMINI_API_KEY")
#     return genai.Client(api_key=api_key)
#
# #for journal
# def generate_image(
#     prompt: str,
#     *,
#     model: str = "gemini-2.5-flash-image",
# ) -> Optional[bytes]:
#     client = _get_client()
#
#     try:
#         response = client.models.generate_content(
#             model=model,
#             contents=prompt,
#             config=types.GenerateContentConfig(response_modalities=["IMAGE"]),
#         )
#     except Exception as e:
#         print("[generate_image] API call failed:", repr(e))
#         raise
#
#     if not response.candidates or not response.candidates[0].content:
#         return None
#
#     for part in response.candidates[0].content.parts:
#         if getattr(part, "inline_data", None):
#             return part.inline_data.data
#
#     return None
#
# #for map
# def generate_image_with_ref(
#     prompt: str,
#     ref_image_bytes: bytes,
#     *,
#     model: str = "gemini-2.5-flash-image",
#     ref_mime: str = "image/png",
# ) -> Optional[bytes]:
#     client = _get_client()
#
#     # SDK 버전별 안전 처리: Part.from_bytes가 없으면 inline_data 형태로 넣기
#     try:
#         ref_part = types.Part.from_bytes(data=ref_image_bytes, mime_type=ref_mime)
#     except Exception:
#         ref_part = types.Part(
#             inline_data=types.Blob(data=ref_image_bytes, mime_type=ref_mime)
#         )
#
#     contents: List[Any] = [ref_part, prompt]
#
#     response = client.models.generate_content(
#         model=model,
#         contents=contents,
#         config=types.GenerateContentConfig(response_modalities=["IMAGE"]),
#     )
#
#     if not response.candidates or not response.candidates[0].content:
#         return None
#
#     for part in response.candidates[0].content.parts:
#         if getattr(part, "inline_data", None):
#             return part.inline_data.data
#     return None
