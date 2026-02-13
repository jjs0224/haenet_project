import os
import uuid
from fastapi import UploadFile

from backend.app.common.utils.util import validate_image
from backend.app.common.storage.types import UploadObject, StoredAsset

try:
    import boto3
except Exception:
    boto3 = None


def _ext(filename: str) -> str:
    ext = os.path.splitext(filename or "")[1].lower()
    return ext if ext else ".jpg"


class S3UploadStorage:
    """
    config 기준으로 통일:
    - base_prefix: 보통 "upload" (고정)
    - tmp:  upload/<S3_PREFIX_TMP>/...
    - perm: upload/<S3_PREFIX_PERM>/...
    """

    def __init__(
        self,
        *,
        bucket: str,
        prefix_tmp: str,
        prefix_perm: str,
        base_prefix: str = "upload",
        region: str | None = None,
    ):
        if boto3 is None:
            raise RuntimeError("boto3 is required for S3 backend")

        self.bucket = bucket
        self.prefix_tmp = prefix_tmp.strip("/")
        self.prefix_perm = prefix_perm.strip("/")
        self.base_prefix = base_prefix.strip("/")
        self.client = boto3.client("s3", region_name=region) if region else boto3.client("s3")

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

        base = self.prefix_tmp if is_temp else self.prefix_perm
        prefix_key = f"{self.base_prefix}/{base}/{upload_type}/{scope_id}"
        stored_name = f"input_{upload_type}_{uuid.uuid4().hex}{ext}"
        key = f"{prefix_key}/{stored_name}"

        self.client.put_object(Bucket=self.bucket, Key=key, Body=data, ContentType=mime)

        return UploadObject(
            upload_type=upload_type,
            member_id=member_id,
            file_key=key,
            input_path=None,
            org_file_name=org_name,
            stored_file_name=stored_name,
            mime_type=mime,
            size_bytes=size,
            prefix_key=prefix_key,
        )

    def delete_input(self, *, file_key: str) -> None:
        self.client.delete_object(Bucket=self.bucket, Key=file_key)

    def delete_prefix(self, *, prefix_key: str) -> None:
        # prefix 하위 오브젝트 리스트 후 삭제
        resp = self.client.list_objects_v2(Bucket=self.bucket, Prefix=prefix_key)
        contents = resp.get("Contents", [])
        if not contents:
            return
        delete_list = [{"Key": o["Key"]} for o in contents]
        self.client.delete_objects(Bucket=self.bucket, Delete={"Objects": delete_list})

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
        Returns stored object key.
        """
        key = f"{prefix_key.rstrip('/')}/{file_name}"
        self.client.put_object(Bucket=self.bucket, Key=key, Body=data, ContentType=mime_type)
        return key

    async def save_permanent(
        self,
        *,
        owner_type: str,
        owner_id: int,
        member_id: int,
        upload: UploadFile,
        sort_order: int,
    ) -> StoredAsset:
        org_name = upload.filename or "unknown"
        mime = upload.content_type or "application/octet-stream"

        data = await upload.read()
        size = len(data)
        validate_image(mime, size)

        ext = _ext(org_name)
        stored_name = f"{owner_type}_{owner_id}_{sort_order}_{uuid.uuid4().hex}{ext}"

        prefix_key = f"{self.base_prefix}/{self.prefix_perm}/{owner_type}/{owner_id}"
        key = f"{prefix_key}/{stored_name}"

        self.client.put_object(Bucket=self.bucket, Key=key, Body=data, ContentType=mime)

        storage_path = key  # (필요하면 CDN URL로 교체)

        return StoredAsset(
            owner_type=owner_type,
            owner_id=owner_id,
            member_id=member_id,
            file_key=key,
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
        org_name = origin_name or "unknown"
        mime = mime_type or "application/octet-stream"
        size = len(data)
        validate_image(mime, size)

        ext = _ext(org_name)
        stored_name = f"{owner_type}_{owner_id}_{sort_order}_{uuid.uuid4().hex}{ext}"

        prefix_key = f"{self.base_prefix}/{self.prefix_perm}/{owner_type}/{owner_id}"
        key = f"{prefix_key}/{stored_name}"

        self.client.put_object(Bucket=self.bucket, Key=key, Body=data, ContentType=mime)

        storage_path = key

        return StoredAsset(
            owner_type=owner_type,
            owner_id=owner_id,
            member_id=member_id,
            file_key=key,
            storage_path=storage_path,
            stored_file_name=stored_name,
            org_file_name=org_name,
            mime_type=mime,
            size_bytes=size,
            sort_order=sort_order,
        )

    def download_to(self, *, file_key: str, dest_path: str) -> None:
        self.client.download_file(self.bucket, file_key, dest_path)

    def is_local(self) -> bool:
        return False
