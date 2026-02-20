import os
import json
from typing import Any, Optional
from urllib.parse import urlparse

from backend.app.core import config


# ---------------------------
# S3 URL Resolver (private bucket 대응)
# ---------------------------
_S3_CLIENT = None


def _get_s3_client():
    global _S3_CLIENT
    if _S3_CLIENT is not None:
        return _S3_CLIENT

    try:
        import boto3  # type: ignore
    except Exception as e:
        raise RuntimeError("boto3 is required for S3 URL generation") from e

    region = os.getenv("S3_REGION") or os.getenv("AWS_DEFAULT_REGION") or os.getenv("AWS_REGION")
    _S3_CLIENT = boto3.client("s3", region_name=region) if region else boto3.client("s3")
    return _S3_CLIENT


def resolve_asset_url(storage_path: str, *, expires_in: int = 3600) -> str:
    if not storage_path:
        print("[S3DBG] empty storage_path")
        return ""

    # ---- normalize ----
    # DB에 "/upload/..." 처럼 leading slash가 들어간 케이스 보정
    storage_path = str(storage_path).strip()
    if storage_path.startswith("/"):
        storage_path = storage_path.lstrip("/")

    # ---- URL 형태 처리 ----
    # 기존 데이터가 S3 "정적 URL"(혹은 만료된 presigned URL)로 저장된 경우가 있어
    #  - private bucket이면 브라우저에서 바로 안 뜸
    #  - 따라서 URL이어도 S3 key를 추출해 presigned URL로 다시 만들어준다.
    if storage_path.startswith("http://") or storage_path.startswith("https://"):
        try:
            u = urlparse(storage_path)
            host = (u.netloc or "").lower()
            path = (u.path or "").lstrip("/")

            is_s3_host = "amazonaws.com" in host
            # CloudFront 등은 그대로 두는게 맞을 수 있음
            if is_s3_host and path:
                # virtual-hosted-style: <bucket>.s3.<region>.amazonaws.com/<key>
                # path-style: s3.<region>.amazonaws.com/<bucket>/<key>
                key: Optional[str] = None
                if config.S3_BUCKET and host.startswith(f"{config.S3_BUCKET.lower()}."):
                    key = path
                elif config.S3_BUCKET and path.startswith(f"{config.S3_BUCKET}/"):
                    key = path[len(config.S3_BUCKET) + 1 :]
                else:
                    key = path

                storage_path = key
            else:
                print("[S3DBG] already full url:", storage_path[:120])
                return storage_path
        except Exception:
            print("[S3DBG] already full url (parse failed):", storage_path[:120])
            return storage_path

    print("[S3DBG] storage_path:", storage_path)
    print("[S3DBG] config.STORAGE_BACKEND:", getattr(config, "STORAGE_BACKEND", None))
    print("[S3DBG] config.S3_BUCKET:", getattr(config, "S3_BUCKET", None))
    import os
    print("[S3DBG] env STORAGE_BACKEND:", os.getenv("STORAGE_BACKEND"))
    print("[S3DBG] env S3_BUCKET:", os.getenv("S3_BUCKET"))
    print("[S3DBG] env S3_REGION:", os.getenv("S3_REGION"))

    if config.STORAGE_BACKEND != "s3":
        print("[S3DBG] SKIP: STORAGE_BACKEND != s3")
        return storage_path

    if not config.S3_BUCKET:
        print("[S3DBG] SKIP: S3_BUCKET empty -> cannot presign")
        return storage_path

    client = _get_s3_client()

    # Guard: verify the object actually exists before generating a presigned URL.
    # A presigned URL for a non-existent key will return 404 to the browser,
    # which is hard to diagnose. Surfacing it here makes the problem visible early.
    try:
        client.head_object(Bucket=config.S3_BUCKET, Key=storage_path)
    except Exception as e:
        error_code = getattr(e, "response", {}).get("Error", {}).get("Code", "")
        if error_code in ("404", "NoSuchKey"):
            print(f"[S3DBG] MISSING OBJECT — key does not exist in S3: {storage_path}")
        else:
            print(f"[S3DBG] head_object error ({error_code}): {storage_path} -> {e}")
        return ""

    url = client.generate_presigned_url(
        ClientMethod="get_object",
        Params={"Bucket": config.S3_BUCKET, "Key": storage_path},
        ExpiresIn=int(expires_in),
    )
    print("[S3DBG] PRESIGNED OK:", url[:140])
    return url


def resolve_asset_urls(paths: list[str] | None, *, expires_in: int = 3600) -> list[str]:
    if not paths:
        return []
    return [resolve_asset_url(p, expires_in=expires_in) for p in paths if p]


# ---------------------------
# Validators
# ---------------------------

ALLOWED_UPLOAD_TYPES = {"menu", "receipt"}  # 이번 로직에 맞춰 최소만
ALLOWED_MIME = {"image/jpeg", "image/png", "image/webp"}
MAX_SIZE_BYTES = 10 * 1024 * 1024  # 10MB


def normalize_upload_type(value: str) -> str:
    t = (value or "").lower().strip()
    if t not in ALLOWED_UPLOAD_TYPES:
        raise ValueError(f"Invalid upload type: {t}")
    return t


def validate_image(mime_type: str, size_bytes: int) -> None:
    if mime_type not in ALLOWED_MIME:
        raise ValueError(f"Unsupported mime_type: {mime_type}")
    if size_bytes > MAX_SIZE_BYTES:
        raise ValueError(f"File too large: {size_bytes} bytes")


# ---------------------------
# Storage factory (local/s3 통합 관리)
# ---------------------------

def get_storage():
    """
    config의 변수명 체계에 맞춘 공통 storage factory
    """
    if config.STORAGE_BACKEND == "s3":
        from backend.app.common.storage.s3 import S3UploadStorage
        return S3UploadStorage(
            bucket=config.S3_BUCKET,
            prefix_tmp=config.S3_PREFIX_TMP,
            prefix_perm=config.S3_PREFIX_PERM,
            base_prefix="upload",
            region=os.getenv("S3_REGION") if hasattr(__import__("os"), "getenv") else None,
        )

    from backend.app.common.storage.local import LocalUploadStorage
    return LocalUploadStorage(
        upload_root=config.LOCAL_UPLOAD_ROOT,
        tmp_root=config.LOCAL_TMP_ROOT,
        perm_root=config.LOCAL_PERM_ROOT,
    )


def ensure_list(v):
    if v is None:
        return []
    if isinstance(v, list):
        return v
    return [v]


def dumps_json(v):
    if v is None:
        return None
    if v == [] or v == {}:
        return None
    return json.dumps(v, ensure_ascii=False)


def parse_ids(raw: Any) -> list[int]:
    if raw is None:
        return []
    if isinstance(raw, list):
        return [int(x) for x in raw]

    s = str(raw).strip()
    if not s:
        return []

    if s.startswith("[") and s.endswith("]"):
        try:
            arr = json.loads(s)
            if isinstance(arr, list):
                return [int(x) for x in arr]
        except Exception:
            pass

    out = []
    for p in s.split(","):
        p = p.strip()
        if not p:
            continue
        try:
            out.append(int(p))
        except ValueError:
            continue
    return out

# import os
# from backend.app.core import config
# import json
# from typing import Any
#
#
# # ---------------------------
# # S3 URL Resolver (private bucket 대응)
# # ---------------------------
# _S3_CLIENT = None
#
#
# def _get_s3_client():
#     global _S3_CLIENT
#     if _S3_CLIENT is not None:
#         return _S3_CLIENT
#
#     try:
#         import boto3  # type: ignore
#     except Exception as e:
#         raise RuntimeError("boto3 is required for S3 URL generation") from e
#
#     region = os.getenv("S3_REGION")
#     _S3_CLIENT = boto3.client("s3", region_name=region) if region else boto3.client("s3")
#     return _S3_CLIENT
#
#
# def resolve_asset_url(storage_path: str, *, expires_in: int = 3600) -> str:
#     if not storage_path:
#         print("[S3DBG] empty storage_path")
#         return ""
#
#     # 이미 완전한 URL이면 그대로
#     if storage_path.startswith("http://") or storage_path.startswith("https://"):
#         print("[S3DBG] already full url:", storage_path[:120])
#         return storage_path
#
#     # ⭐ 여기서 환경/설정값 확인
#     print("[S3DBG] storage_path:", storage_path)
#     print("[S3DBG] config.STORAGE_BACKEND:", getattr(config, "STORAGE_BACKEND", None))
#     print("[S3DBG] config.S3_BUCKET:", getattr(config, "S3_BUCKET", None))
#     import os
#     print("[S3DBG] env STORAGE_BACKEND:", os.getenv("STORAGE_BACKEND"))
#     print("[S3DBG] env S3_BUCKET:", os.getenv("S3_BUCKET"))
#     print("[S3DBG] env S3_REGION:", os.getenv("S3_REGION"))
#
#     if config.STORAGE_BACKEND != "s3":
#         print("[S3DBG] SKIP: STORAGE_BACKEND != s3")
#         return storage_path
#
#     if not config.S3_BUCKET:
#         print("[S3DBG] SKIP: S3_BUCKET empty -> cannot presign")
#         return storage_path
#
#     client = _get_s3_client()
#     url = client.generate_presigned_url(
#         ClientMethod="get_object",
#         Params={"Bucket": config.S3_BUCKET, "Key": storage_path},
#         ExpiresIn=int(expires_in),
#     )
#     print("[S3DBG] PRESIGNED OK:", url[:140])
#     return url
#
#
# def resolve_asset_urls(paths: list[str] | None, *, expires_in: int = 3600) -> list[str]:
#     if not paths:
#         return []
#     return [resolve_asset_url(p, expires_in=expires_in) for p in paths if p]
#
#
# # ---------------------------
# # Validators
# # ---------------------------
#
# ALLOWED_UPLOAD_TYPES = {"menu", "receipt"}  # 이번 로직에 맞춰 최소만
# ALLOWED_MIME = {"image/jpeg", "image/png", "image/webp"}
# MAX_SIZE_BYTES = 10 * 1024 * 1024  # 10MB
#
#
# def normalize_upload_type(value: str) -> str:
#     t = (value or "").lower().strip()
#     if t not in ALLOWED_UPLOAD_TYPES:
#         raise ValueError(f"Invalid upload type: {t}")
#     return t
#
#
# def validate_image(mime_type: str, size_bytes: int) -> None:
#     if mime_type not in ALLOWED_MIME:
#         raise ValueError(f"Unsupported mime_type: {mime_type}")
#     if size_bytes > MAX_SIZE_BYTES:
#         raise ValueError(f"File too large: {size_bytes} bytes")
#
#
# # ---------------------------
# # Storage factory (local/s3 통합 관리)
# # ---------------------------
#
# def get_storage():
#     """
#     config의 변수명 체계에 맞춘 공통 storage factory
#     """
#     if config.STORAGE_BACKEND == "s3":
#         from backend.app.common.storage.s3 import S3UploadStorage
#         return S3UploadStorage(
#             bucket=config.S3_BUCKET,
#             prefix_tmp=config.S3_PREFIX_TMP,
#             prefix_perm=config.S3_PREFIX_PERM,
#             base_prefix="upload",   # S3 상단 폴더(고정)
#             region=os.getenv("S3_REGION") if hasattr(__import__("os"), "getenv") else None,
#         )
#
#     from backend.app.common.storage.local import LocalUploadStorage
#     return LocalUploadStorage(
#         upload_root=config.LOCAL_UPLOAD_ROOT,
#         tmp_root=config.LOCAL_TMP_ROOT,
#         perm_root=config.LOCAL_PERM_ROOT,
#     )
#
#
# def ensure_list(v):
#     if v is None:
#         return []
#     if isinstance(v, list):
#         return v
#     return [v]
#
#
# def dumps_json(v):
#     if v is None:
#         return None
#     if v == [] or v == {}:
#         return None
#     return json.dumps(v, ensure_ascii=False)
#
#
# def parse_ids(raw: Any) -> list[int]:
#     if raw is None:
#         return []
#     if isinstance(raw, list):
#         return [int(x) for x in raw]
#
#     s = str(raw).strip()
#     if not s:
#         return []
#
#     # JSON 문자열이면 JSON으로 먼저 파싱
#     if s.startswith("[") and s.endswith("]"):
#         try:
#             arr = json.loads(s)
#             if isinstance(arr, list):
#                 return [int(x) for x in arr]
#         except Exception:
#             pass
#
#     # fallback: "1,2,3" 같은 CSV
#     out = []
#     for p in s.split(","):
#         p = p.strip()
#         if not p:
#             continue
#         try:
#             out.append(int(p))
#         except ValueError:
#             continue
#     return out
