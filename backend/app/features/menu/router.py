import uuid
import json
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile

from backend.app.core.security.deps import get_current_member
from backend.app.common.utils.debug import log_exception
from backend.app.common.service.file_upload_service import (
    build_temp_prefix,
    delete_prefix,
    ensure_local_path,
    upload_input_file,
)
from backend.app.features.menu.schemas import MenuUploadResponse
from backend.app.features.menu.service import run_menu_ai
from backend.app.core.database import get_db
from sqlalchemy.orm import Session
from backend.app.common.service.ai_member_info import build_user_profile_payload
from backend.app.common.service.file_upload_service import (
    ensure_local_path,
    save_temp_json,
    upload_input_file,
)
from backend.app.common.utils.debug import log_exception
from backend.app.core.database import get_db
from backend.app.core.job_queue import connect_redis, enqueue_task, utc_now_iso
from backend.app.core.security.deps import get_current_member
from backend.app.features.menu.schemas import MenuEnqueueResponse, MenuJobResponse

router = APIRouter(prefix="/menu", tags=["menu"])


@router.post("/upload", response_model=MenuUploadResponse)
async def upload_menu(
    db: Session = Depends(get_db),
    type: str = Form("menu"),
    file: UploadFile = File(...),
    current=Depends(get_current_member)):

    if (type or "").lower().strip() != "menu":
        raise HTTPException(status_code=400, detail="type must be 'menu'")

    job_id = uuid.uuid4().hex
    tmp_prefix = build_temp_prefix(upload_type="menu", scope_id=job_id)

    try:
        obj = await upload_input_file(
            upload_type="menu",
            member_id=current.member_id,
            upload=file,
            scope_id=job_id,
            is_temp=True,
        )
    except Exception as e:
        log_exception("menu.upload_input", e)
        raise HTTPException(status_code=400, detail=f"upload failed: {e}")

    local_path, cleanup = ensure_local_path(obj)

    try:
        # Prefer user_profile from client if provided, otherwise build from DB.
        profile_payload: Dict[str, Any] | None = None
        raw_profile = (user_profile or "").strip()
        if raw_profile:
            try:
                parsed = json.loads(raw_profile)
                if not isinstance(parsed, dict):
                    raise ValueError("user_profile must be a JSON object")
                profile_payload = parsed
            except Exception as e:
                raise HTTPException(status_code=400, detail=f"user_profile invalid: {e}")

        if profile_payload is None:
            try:
                profile_payload = build_user_profile_payload(db, current.member_id)
            except Exception as e:
                log_exception("menu.profile_build", e)
                profile_payload = {"allergy_tags": [], "avoid_foods": [], "religion": []}

        # Save profile JSON next to input image (same temp prefix/path group).
        # local: <tmp>/<menu>/<job_id>/user_profile.json
        # s3:    upload/tmp/menu/<job_id>/user_profile.json
        user_profile_file_key = save_temp_json(
            prefix_key=obj.prefix_key,
            file_name="user_profile.json",
            payload=profile_payload,
        )

        image_b64 = base64.b64encode(Path(local_path).read_bytes()).decode("ascii")

        payload = {
            "run_id": job_id,
            "image_base64": image_b64,
            "user_profile": profile_payload,
            "user_profile_file_key": user_profile_file_key,
            "runs_root": "/tmp/ai_runs",
            "run_step4": True,
            "run_step5": True,
            "run_step6": True,
        }

        try:
            r = connect_redis()
        except Exception as e:
            raise HTTPException(status_code=503, detail=f"redis unavailable: {type(e).__name__}: {e}")

        enqueue_task(r, task="menu_assistant_pipeline", payload=payload, job_id=job_id)
        return MenuEnqueueResponse(job_id=job_id, status="PENDING", queued_at=utc_now_iso())

    except Exception as e:
        log_exception("menu.ai_failed", e)
        import builtins
        raise HTTPException(status_code=500, detail=f"menu ai failed: {builtins.type(e).__name__}: {e}")

    finally:
        cleanup()
        # delete_prefix(prefix_key=tmp_prefix)



# import uuid
# from pathlib import Path
#
# from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
#
# from backend.app.core import config
# from backend.app.core.security.deps import get_current_member
# from backend.app.common.utils.debug import log_exception
# from backend.app.common.service.file_upload_service import (
#     build_temp_prefix,
#     delete_prefix,
#     ensure_local_path,
#     upload_input_file,
# )
# from backend.app.features.menu.schemas import MenuUploadResponse
#
# from backend.app.features.menu.service import run_menu_ai
#
# router = APIRouter(prefix="/menu", tags=["menu"])
#
#
# @router.post("/upload", response_model=MenuUploadResponse)
# async def upload_menu(
#     type: str = Form("menu"),
#     file: UploadFile = File(...),
#     current=Depends(get_current_member),
# ):
#     if (type or "").lower().strip() != "menu":
#         raise HTTPException(status_code=400, detail="type must be 'menu'")
#
#     job_id = uuid.uuid4().hex
#     tmp_prefix = build_temp_prefix(upload_type="menu", scope_id=job_id)
#
#     try:
#         obj = await upload_input_file(
#             upload_type="menu",
#             member_id=current.member_id,
#             upload=file,
#             scope_id=job_id,
#             is_temp=True,
#         )
#     except Exception as e:
#         log_exception("menu.upload_input", e)
#         raise HTTPException(status_code=400, detail=f"upload failed: {e}")
#
#     local_path, cleanup = ensure_local_path(obj)
#
#     try:
#         #  runs_root는 temp 아래로 두어도 됨(디버그 목적)
#         runs_root = Path(tmp_prefix) / "ai_runs"
#
#         result = run_menu_ai(image_path=local_path, runs_root=runs_root, run_id=job_id)
#         return MenuUploadResponse(job_id=job_id, upload_type="menu", result=result)
#
#     except Exception as e:
#         log_exception("menu.ai_failed", e)
#         raise HTTPException(status_code=500, detail=f"menu ai failed: {type(e).__name__}: {e}")
#
#     finally:
#         cleanup()
#         #  menu 정책: 작업 끝나면 temp 삭제
#         # delete_prefix(prefix_key=tmp_prefix)
