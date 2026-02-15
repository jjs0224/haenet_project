import os
from backend.app.core import config
import json
from typing import Any

# ---------------------------
# S3 URL resolver (private bucket 대응)
# ---------------------------

_S3_CLIENT = None


def _get_s3_client():
    """Lazy-init boto3 client (only when STORAGE_BACKEND == 's3')."""
    global _S3_CLIENT
    if _S3_CLIENT is not None:
        return _S3_CLIENT

    try:
        import boto3  # type: ignore
    except Exception as e:
        raise RuntimeError("boto3 is required for S3 URL generation") from e

    region = os.getenv("S3_REGION")
    _S3_CLIENT = boto3.client("s3", region_name=region) if region else boto3.client("s3")
    return _S3_CLIENT


def resolve_asset_url(storage_path: str, *, expires_in: int = 3600) -> str:
    """
    DB에 저장된 storage_path를 '브라우저에서 바로 접근 가능한 URL'로 변환.

    - local: 기존 storage_path(/static/...) 그대로 반환
    - s3(private): presigned GET URL 반환

    주의)
    - s3 storage_path는 현재 구현상 S3 key (예: upload/perm/community/123/xxx.png)
    """
    if not storage_path:
        return ""

    # 이미 URL이면 그대로
    if storage_path.startswith("http://") or storage_path.startswith("https://"):
        return storage_path

    if config.STORAGE_BACKEND != "s3":
        return storage_path

    client = _get_s3_client()
    return client.generate_presigned_url(
        ClientMethod="get_object",
        Params={"Bucket": config.S3_BUCKET, "Key": storage_path},
        ExpiresIn=int(expires_in),
    )


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
            base_prefix="upload",   # S3 상단 폴더(고정)
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

    # JSON 문자열이면 JSON으로 먼저 파싱
    if s.startswith("[") and s.endswith("]"):
        try:
            arr = json.loads(s)
            if isinstance(arr, list):
                return [int(x) for x in arr]
        except Exception:
            pass

    # fallback: "1,2,3" 같은 CSV
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