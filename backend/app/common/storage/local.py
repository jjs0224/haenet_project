import os
import uuid
from pathlib import Path
from fastapi import UploadFile

from backend.app.common.utils.util import validate_image
from backend.app.common.storage.types import UploadObject, StoredAsset


def _ext(filename: str) -> str:
    ext = os.path.splitext(filename or "")[1].lower()
    return ext if ext else ".jpg"


class LocalUploadStorage:
    """
    config 기준으로 통일:
    - upload_root: <PROJECT_ROOT>/uploads
    - tmp_root: upload_root/tmp
    - perm_root: upload_root/perm

    임시는 scope_id 기준으로 폴더 생성해서 "폴더 단위" 삭제
    """

    def __init__(self, upload_root: Path, tmp_root: Path, perm_root: Path):
        self.upload_root = Path(upload_root).resolve()
        self.tmp_root = Path(tmp_root).resolve()
        self.perm_root = Path(perm_root).resolve()

        self.upload_root.mkdir(parents=True, exist_ok=True)
        self.tmp_root.mkdir(parents=True, exist_ok=True)
        self.perm_root.mkdir(parents=True, exist_ok=True)

    async def save_input(
        self,
        *,
        upload_type: str,
        member_id: int,
        upload: UploadFile,
        scope_id: str,
        is_temp: bool = True,
    ) -> UploadObject:
        org_name = upload.filename or "unknown"
        mime = upload.content_type or "application/octet-stream"

        data = await upload.read()
        size = len(data)
        validate_image(mime, size)

        ext = _ext(org_name)

        base = self.tmp_root if is_temp else self.perm_root

        # 임시/영구 모두 scope_id 단위 폴더로 격리
        scoped_dir = base / upload_type / scope_id
        scoped_dir.mkdir(parents=True, exist_ok=True)

        stored_name = f"input_{upload_type}_{uuid.uuid4().hex}{ext}"
        path = scoped_dir / stored_name

        path.write_bytes(data)

        # prefix_key는 "폴더 단위 삭제"를 위한 값
        prefix_key = str(scoped_dir)

        return UploadObject(
            upload_type=upload_type,
            member_id=member_id,
            file_key=str(path),
            input_path=str(path),
            org_file_name=org_name,
            stored_file_name=stored_name,
            mime_type=mime,
            size_bytes=size,
            prefix_key=prefix_key,
        )

    def delete_input(self, *, file_key: str) -> None:
        p = Path(file_key)
        if p.exists() and p.is_file():
            try:
                p.unlink()
            except Exception:
                return

    def delete_prefix(self, *, prefix_key: str) -> None:
        """
        local: prefix_key는 디렉터리 경로
        - scope 폴더를 통째로 삭제
        """
        d = Path(prefix_key)
        if not d.exists() or not d.is_dir():
            return

        # 안전한 rmtree
        import shutil
        shutil.rmtree(d, ignore_errors=True)

    def save_temp_bytes(
        self,
        *,
        prefix_key: str,
        file_name: str,
        data: bytes,
        mime_type: str = "application/octet-stream",
    ) -> str:
        """
        Temporary helper file save for non-image artifacts (e.g., user_profile.json).
        Returns stored file key/path.
        """
        d = Path(prefix_key)
        d.mkdir(parents=True, exist_ok=True)
        p = d / file_name
        p.write_bytes(data)
        return str(p)

    async def save_permanent(
        self,
        *,
        owner_type: str,
        owner_id: int,
        member_id: int,
        upload: UploadFile,
        sort_order: int,
    ) -> StoredAsset:
        """
        영구 저장:
        upload/perm/{owner_type}/{owner_id}/...
        """
        org_name = upload.filename or "unknown"
        mime = upload.content_type or "application/octet-stream"

        data = await upload.read()
        size = len(data)
        validate_image(mime, size)

        ext = _ext(org_name)

        scoped_dir = self.perm_root / owner_type / str(owner_id)
        scoped_dir.mkdir(parents=True, exist_ok=True)

        stored_name = f"{owner_type}_{owner_id}_{sort_order}_{uuid.uuid4().hex}{ext}"
        path = scoped_dir / stored_name
        path.write_bytes(data)

        # upload_root 기준 상대경로 → /static URL (Windows/Linux 안전)
        rel_posix = path.relative_to(self.upload_root).as_posix()
        storage_path = f"/static/{rel_posix}"

        return StoredAsset(
            owner_type=owner_type,
            owner_id=owner_id,
            member_id=member_id,
            file_key=str(path),
            storage_path=storage_path,
            stored_file_name=stored_name,
            org_file_name=org_name,
            mime_type=mime,
            size_bytes=size,
            sort_order=sort_order,
        )

    async def save_permanent_bytes(
        self,
        *,
        owner_type: str,
        owner_id: int,
        member_id: int,
        data: bytes,
        origin_name: str,
        mime_type: str,
        sort_order: int,
    ) -> StoredAsset:
        """
        bytes(예: AI 생성 이미지) 영구 저장:
        uploads/perm/{owner_type}/{owner_id}/...
        storage_path=/static/perm/{owner_type}/{owner_id}/...
        """
        org_name = origin_name or "unknown"
        mime = mime_type or "application/octet-stream"
        size = len(data)

        # AI 산출물도 이미지로 제한하고 싶으면 validate 유지 (싫으면 이 줄 제거)
        validate_image(mime, size)

        ext = _ext(org_name)

        scoped_dir = self.perm_root / owner_type / str(owner_id)
        scoped_dir.mkdir(parents=True, exist_ok=True)

        stored_name = f"{owner_type}_{owner_id}_{sort_order}_{uuid.uuid4().hex}{ext}"
        path = scoped_dir / stored_name
        path.write_bytes(data)

        rel_posix = path.relative_to(self.upload_root).as_posix()
        storage_path = f"/static/{rel_posix}"

        return StoredAsset(
            owner_type=owner_type,
            owner_id=owner_id,
            member_id=member_id,
            file_key=str(path),
            storage_path=storage_path,
            stored_file_name=stored_name,
            org_file_name=org_name,
            mime_type=mime,
            size_bytes=size,
            sort_order=sort_order,
        )

    def is_local(self) -> bool:
        return True
