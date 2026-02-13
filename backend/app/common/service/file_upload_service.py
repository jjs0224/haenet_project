import os
import json
import uuid
from pathlib import Path
from typing import Callable, Tuple, Optional

from fastapi import UploadFile

from backend.app.core import config
from backend.app.common.storage.types import UploadObject, StoredAsset
from backend.app.common.utils.util import get_storage, normalize_upload_type

_WORK_DIR = Path("./_work").resolve()
_WORK_DIR.mkdir(parents=True, exist_ok=True)


# --------------------------------------------------------------------
# Prefix builder (local/s3 통일)
# --------------------------------------------------------------------
def build_temp_prefix(*, upload_type: str, scope_id: str) -> str:
    """
    임시 저장 폴더(prefix) 생성 규칙을 "한 군데"에서 통일
    - local:  <LOCAL_TMP_ROOT>/<upload_type>/<scope_id>
    - s3:     upload/<S3_PREFIX_TMP>/<upload_type>/<scope_id>
    """
    t = normalize_upload_type(upload_type)

    if config.STORAGE_BACKEND == "local":
        return (config.LOCAL_TMP_ROOT / t / scope_id).resolve().as_posix()

    # s3 prefix 규칙
    base = "upload"  # s3 상단 prefix(고정, 필요하면 config로 뺄 수 있음)
    return f"{base}/{config.S3_PREFIX_TMP}/{t}/{scope_id}"


def build_perm_prefix(*, owner_type: str, owner_id: int) -> str:
    """
    영구 저장 prefix 규칙 (필요 시 사용)
    - local: <LOCAL_PERM_ROOT>/<owner_type>/<owner_id>
    - s3:    upload/<S3_PREFIX_PERM>/<owner_type>/<owner_id>
    """
    if config.STORAGE_BACKEND == "local":
        return (config.LOCAL_PERM_ROOT / owner_type / str(owner_id)).resolve().as_posix()

    base = "upload"
    return f"{base}/{config.S3_PREFIX_PERM}/{owner_type}/{owner_id}"


# --------------------------------------------------------------------
# Save / Delete
# --------------------------------------------------------------------
async def upload_input_file(
    *,
    upload_type: str,
    member_id: int,
    upload: UploadFile,
    scope_id: str,
    is_temp: bool = True,
) -> UploadObject:
    """
    menu/receipt 원본 업로드 저장
    - temp(True): tmp/{type}/{scope_id}/...
    - temp(False): perm/{type}/{scope_id}/... (현재는 거의 안 씀)
    """
    t = normalize_upload_type(upload_type)
    storage = get_storage()

    obj = await storage.save_input(
        upload_type=t,
        member_id=member_id,
        upload=upload,
        scope_id=scope_id,
        is_temp=is_temp,
    )
    return obj


def delete_input_file(*, file_key: str) -> None:
    """
    단일 파일 삭제(선택)
    """
    storage = get_storage()
    storage.delete_input(file_key=file_key)


def delete_prefix(*, prefix_key: str) -> None:
    """
    폴더(prefix) 단위 삭제
    - local: 디렉토리 rmtree
    - s3: prefix 하위 오브젝트 삭제
    """
    storage = get_storage()
    storage.delete_prefix(prefix_key=prefix_key)


# --------------------------------------------------------------------
# Permanent save (UploadFile)
# --------------------------------------------------------------------
async def save_permanent_asset(
    *,
    owner_type: str,
    owner_id: int,
    member_id: int,
    upload: UploadFile,
    sort_order: int,
) -> StoredAsset:
    """
    리뷰 이미지 등 영구 저장
    - local: uploads/perm/{owner_type}/{owner_id}/...
            storage_path=/static/perm/{owner_type}/{owner_id}/...
    - s3:    upload/perm/{owner_type}/{owner_id}/...
    """
    storage = get_storage()
    if not hasattr(storage, "save_permanent"):
        raise RuntimeError("Storage does not support save_permanent()")

    stored = await storage.save_permanent(
        owner_type=owner_type,
        owner_id=owner_id,
        member_id=member_id,
        upload=upload,
        sort_order=sort_order,
    )
    return stored


# --------------------------------------------------------------------
# Local path guarantee (AI 필요)
# --------------------------------------------------------------------
def ensure_local_path(obj: UploadObject) -> Tuple[str, Callable[[], None]]:
    """
    AI가 파일 경로를 필요로 할 때(local path 보장)
    - local: obj.input_path 그대로 사용
    - s3: obj.file_key 를 _work 에 다운로드 후 경로 반환
    """
    storage = get_storage()

    # local이면 input_path가 이미 존재
    if obj.input_path:
        return obj.input_path, lambda: None

    # s3이면 다운로드 필요
    if not hasattr(storage, "download_to"):
        raise RuntimeError("Storage does not support download_to() for remote backend")

    ext = os.path.splitext(obj.stored_file_name)[1] or ".bin"
    local_path = _WORK_DIR / f"dl_{uuid.uuid4().hex}{ext}"

    storage.download_to(file_key=obj.file_key, dest_path=str(local_path))

    def cleanup():
        try:
            if local_path.exists():
                local_path.unlink()
        except Exception:
            pass

    return str(local_path), cleanup


# --------------------------------------------------------------------
# Permanent save from bytes (AI outputs)
# --------------------------------------------------------------------
async def save_permanent_bytes(
    *,
    owner_type: str,
    owner_id: int,
    member_id: int,
    data: bytes,
    origin_name: str = "generated.png",
    mime_type: str = "image/png",
    sort_order: int = 0,
) -> StoredAsset:
    """
    AI 등에서 생성된 bytes를 영구 저장할 때 사용
    - local: uploads/perm/{owner_type}/{owner_id}/...
            storage_path=/static/perm/{owner_type}/{owner_id}/...
    - s3:    upload/<perm prefix>/{owner_type}/{owner_id}/... (지원 시)
    """
    storage = get_storage()
    if not hasattr(storage, "save_permanent_bytes"):
        raise RuntimeError("Storage does not support save_permanent_bytes()")

    return await storage.save_permanent_bytes(
        owner_type=owner_type,
        owner_id=owner_id,
        member_id=member_id,
        data=data,
        origin_name=origin_name,
        mime_type=mime_type,
        sort_order=sort_order,
    )


def save_temp_json(*, prefix_key: str, file_name: str, payload: dict) -> str:
    """
    Save JSON under an existing temp prefix.
    - local: <prefix_key>/<file_name>
    - s3:    <prefix_key>/<file_name>
    Returns stored key/path.
    """
    storage = get_storage()
    if not hasattr(storage, "save_temp_bytes"):
        raise RuntimeError("Storage does not support save_temp_bytes()")

    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    return storage.save_temp_bytes(
        prefix_key=prefix_key,
        file_name=file_name,
        data=data,
        mime_type="application/json",
    )
