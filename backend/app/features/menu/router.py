import base64
import json
import uuid
from pathlib import Path
from typing import Any, Dict

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

from backend.app.common.service.ai_member_info import build_user_profile_payload
from backend.app.common.service.file_upload_service import ensure_local_path, upload_input_file
from backend.app.common.utils.debug import log_exception
from backend.app.core.database import get_db
from backend.app.core.job_queue import connect_redis, enqueue_task, utc_now_iso
from backend.app.core.security.deps import get_current_member
from backend.app.features.menu.schemas import MenuEnqueueResponse, MenuJobResponse

router = APIRouter(prefix="/menu", tags=["menu"])


def _parse_json(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, (dict, list)):
        return value
    if isinstance(value, str):
        try:
            return json.loads(value)
        except Exception:
            return value
    return value


@router.post("/upload", response_model=MenuEnqueueResponse, status_code=202)
async def upload_menu(
    db: Session = Depends(get_db),
    type: str = Form("menu"),
    file: UploadFile = File(...),
    user_profile: str = Form(""),
    current=Depends(get_current_member),
):
    if (type or "").lower().strip() != "menu":
        raise HTTPException(status_code=400, detail="type must be 'menu'")

    job_id = uuid.uuid4().hex

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

        image_b64 = base64.b64encode(Path(local_path).read_bytes()).decode("ascii")

        payload = {
            "run_id": job_id,
            "image_base64": image_b64,
            "user_profile": profile_payload,
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

    except HTTPException:
        raise
    except Exception as e:
        log_exception("menu.enqueue_failed", e)
        raise HTTPException(status_code=500, detail=f"menu enqueue failed: {type(e).__name__}: {e}")
    finally:
        cleanup()


@router.get("/job/{job_id}", response_model=MenuJobResponse)
def get_menu_job(job_id: str, current=Depends(get_current_member)):
    try:
        r = connect_redis()
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"redis unavailable: {type(e).__name__}: {e}")

    data = r.hgetall(f"cicdex:job:{job_id}")
    if not data:
        raise HTTPException(status_code=404, detail="job not found")

    result = _parse_json(data.get("result"))
    error = _parse_json(data.get("error"))

    return MenuJobResponse(
        job_id=job_id,
        status=data.get("status", "PENDING"),
        result=result if data.get("status") == "DONE" else result,
        error=error,
        queued_at=data.get("queued_at"),
        updated_at=data.get("updated_at"),
    )
