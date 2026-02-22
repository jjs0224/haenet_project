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


def _extract_image_bytes(response) -> Optional[bytes]:
    """SDK 응답에서 IMAGE bytes를 최대한 안전하게 추출."""
    try:
        candidates = getattr(response, "candidates", None) or []
        if not candidates:
            return None
        content = getattr(candidates[0], "content", None)
        if not content:
            return None
        parts = getattr(content, "parts", None) or []
        for part in parts:
            inline = getattr(part, "inline_data", None)
            if inline and getattr(inline, "data", None):
                return inline.data
    except Exception:
        return None
    return None


# for journal
def generate_image(
    prompt: str,
    *,
    model: str = "gemini-2.5-flash-image",
    max_retries: int = 2,
) -> Optional[bytes]:
    """
    Journal base image 생성.
    - 외부 모델은 간헐적으로 IMAGE payload가 비는 경우가 있어(쿼터/필터/응답 변형 등)
      '빈 bytes(None)'가 나오면 짧게 재시도 후 None 반환.
    """
    client = _get_client()
    last_err: Optional[Exception] = None

    for attempt in range(max_retries + 1):
        try:
            response = client.models.generate_content(
                model=model,
                contents=prompt,
                config=types.GenerateContentConfig(response_modalities=["IMAGE"]),
            )
            out = _extract_image_bytes(response)
            if out:
                return out

            # IMAGE가 비었을 때 원인 힌트 로깅(개인정보/프롬프트는 출력하지 않음)
            try:
                fb = getattr(getattr(response, "prompt_feedback", None), "block_reason", None)
                if fb:
                    print(f"[generate_image] empty IMAGE (block_reason={fb}) attempt={attempt}")
                else:
                    print(f"[generate_image] empty IMAGE attempt={attempt}")
            except Exception:
                print(f"[generate_image] empty IMAGE attempt={attempt}")

        except Exception as e:
            last_err = e
            print("[generate_image] API call failed:", repr(e), "attempt=", attempt)

        # 다음 시도 전 짧은 백오프
        if attempt < max_retries:
            import time
            time.sleep(0.35 * (attempt + 1))

    # 마지막에 에러가 있었다면 상위에서 원인 파악 가능하도록 raise 대신 None 유지(호출부에서 fallback 처리)
    if last_err:
        return None
    return None


# for map
def generate_image_with_ref(
    prompt: str,
    ref_image_bytes: bytes,
    *,
    model: str = "gemini-2.5-flash-image",
    ref_mime: str = "image/png",
    max_retries: int = 1,
) -> Optional[bytes]:
    client = _get_client()
    last_err: Optional[Exception] = None

    # SDK 버전별 안전 처리: Part.from_bytes가 없으면 inline_data 형태로 넣기
    try:
        ref_part = types.Part.from_bytes(data=ref_image_bytes, mime_type=ref_mime)
    except Exception:
        ref_part = types.Part(inline_data=types.Blob(data=ref_image_bytes, mime_type=ref_mime))

    contents: List[Any] = [ref_part, prompt]

    for attempt in range(max_retries + 1):
        try:
            response = client.models.generate_content(
                model=model,
                contents=contents,
                config=types.GenerateContentConfig(response_modalities=["IMAGE"]),
            )
            out = _extract_image_bytes(response)
            if out:
                return out
            print(f"[generate_image_with_ref] empty IMAGE attempt={attempt}")
        except Exception as e:
            last_err = e
            print("[generate_image_with_ref] API call failed:", repr(e), "attempt=", attempt)
        if attempt < max_retries:
            import time
            time.sleep(0.35 * (attempt + 1))

    if last_err:
        return None
    return None


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
#
# # generator.py 맨 아래에 추가
#
# def generate_text(
#     prompt: str,
#     *,
#     model: str = "gemini-2.5-flash",
# ) -> str:
#     client = _get_client()
#
#     try:
#         response = client.models.generate_content(
#             model=model,
#             contents=prompt,
#         )
#     except Exception as e:
#         print("[generate_text] API call failed:", repr(e))
#         raise
#
#     text = getattr(response, "text", None)
#     if text:
#         return text.strip()
#
#     # fallback
#     if response.candidates and response.candidates[0].content:
#         parts = response.candidates[0].content.parts or []
#         out = []
#         for p in parts:
#             t = getattr(p, "text", None)
#             if t:
#                 out.append(t)
#         return "\n".join(out).strip()
#
#     return ""
#
#
#
# # from __future__ import annotations
# #
# # import os
# # from typing import Optional, List, Any
# # from dotenv import load_dotenv
# # from google import genai
# # from google.genai import types
# #
# # load_dotenv()
# #
# #
# # def _get_client() -> genai.Client:
# #     api_key = os.getenv("GEMINI_API_KEY")
# #     if not api_key:
# #         raise RuntimeError("Missing env var: GEMINI_API_KEY")
# #     return genai.Client(api_key=api_key)
# #
# # #for journal
# # def generate_image(
# #     prompt: str,
# #     *,
# #     model: str = "gemini-2.5-flash-image",
# # ) -> Optional[bytes]:
# #     client = _get_client()
# #
# #     try:
# #         response = client.models.generate_content(
# #             model=model,
# #             contents=prompt,
# #             config=types.GenerateContentConfig(response_modalities=["IMAGE"]),
# #         )
# #     except Exception as e:
# #         print("[generate_image] API call failed:", repr(e))
# #         raise
# #
# #     if not response.candidates or not response.candidates[0].content:
# #         return None
# #
# #     for part in response.candidates[0].content.parts:
# #         if getattr(part, "inline_data", None):
# #             return part.inline_data.data
# #
# #     return None
# #
# # #for map
# # def generate_image_with_ref(
# #     prompt: str,
# #     ref_image_bytes: bytes,
# #     *,
# #     model: str = "gemini-2.5-flash-image",
# #     ref_mime: str = "image/png",
# # ) -> Optional[bytes]:
# #     client = _get_client()
# #
# #     # SDK 버전별 안전 처리: Part.from_bytes가 없으면 inline_data 형태로 넣기
# #     try:
# #         ref_part = types.Part.from_bytes(data=ref_image_bytes, mime_type=ref_mime)
# #     except Exception:
# #         ref_part = types.Part(
# #             inline_data=types.Blob(data=ref_image_bytes, mime_type=ref_mime)
# #         )
# #
# #     contents: List[Any] = [ref_part, prompt]
# #
# #     response = client.models.generate_content(
# #         model=model,
# #         contents=contents,
# #         config=types.GenerateContentConfig(response_modalities=["IMAGE"]),
# #     )
# #
# #     if not response.candidates or not response.candidates[0].content:
# #         return None
# #
# #     for part in response.candidates[0].content.parts:
# #         if getattr(part, "inline_data", None):
# #             return part.inline_data.data
# #     return None
