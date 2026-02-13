import base64
import json
import uuid
from pathlib import Path
from typing import Any, Dict, List
from sqlalchemy import select
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

from backend.app.common.service.file_upload_service import ensure_local_path, upload_input_file
from backend.app.core.database import get_db
from backend.app.core.job_queue import connect_redis, enqueue_task, utc_now_iso
from backend.app.core.security.deps import get_current_member
from backend.app.common.utils.debug import log_exception
from backend.app.common.service.receipt_session_service import ReceiptSessionService
from backend.app.features.review.schemas import (
    ReviewEnqueueResponse,
    ReviewJobResponse,
    ReviewCreateResponse,
    ReviewContentUpdateResponse,
    ReviewContentUpdate,
    ReviewRead,
)
from backend.app.features.review.service import create_review_from_receipt, list_reviews, get_review_detail, update_review_content_only

router = APIRouter(prefix="/review", tags=["review"])

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


@router.post("/receipt/verify", response_model=ReviewEnqueueResponse, status_code=202)
async def receipt_verify(
    type: str = Form("receipt"),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current=Depends(get_current_member),
):
    if (type or "").lower().strip() != "receipt":
        raise HTTPException(status_code=400, detail="type must be 'receipt'")

    receipt_id = uuid.uuid4().hex

    try:
        obj = await upload_input_file(
            upload_type="receipt",
            member_id=current.member_id,
            upload=file,
            scope_id=receipt_id,
            is_temp=True,
        )
    except Exception as e:
        log_exception("review.upload_input", e)
        raise HTTPException(status_code=400, detail=f"upload failed: {e}")

    local_path, cleanup = ensure_local_path(obj)

    try:
        image_b64 = base64.b64encode(Path(local_path).read_bytes()).decode("ascii")

        payload: Dict[str, Any] = {
            "receipt_id": receipt_id,
            "image_base64": image_b64,
        }

        try:
            r = connect_redis()
        except Exception as e:
            raise HTTPException(status_code=503, detail=f"redis unavailable: {type(e).__name__}: {e}")

        enqueue_task(r, task="review_receipt_ocr", payload=payload, job_id=receipt_id)
        return ReviewEnqueueResponse(job_id=receipt_id, status="PENDING", queued_at=utc_now_iso())
    except Exception as e:
        log_exception("router.receipt_verify", e)
        raise HTTPException(status_code=500, detail=f"review enqueue failed: {type(e).__name__}: {e}")
    finally:
        cleanup()


@router.get("/receipt/job/{job_id}", response_model=ReviewJobResponse)
def receipt_job_status(job_id: str, current=Depends(get_current_member)):
    try:
        r = connect_redis()
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"redis unavailable: {type(e).__name__}: {e}")

    data = r.hgetall(f"cicdex:job:{job_id}")
    if not data:
        raise HTTPException(status_code=404, detail="job not found")

    print("receipt_job_status job_id :: ", job_id)
    print("receipt_job_status data :: ", data)


    result = _parse_json(data.get("result"))
    error = _parse_json(data.get("error"))
    status = data.get("status", "PENDING")

    if status == "DONE":
        # Store receipt session for later review creation.
        if not ReceiptSessionService.get(receipt_id=job_id):
            ReceiptSessionService.put(
                receipt_id=job_id,
                member_id=current.member_id,
                payload=result or {},
            )

    return ReviewJobResponse(
        job_id=job_id,
        status=status,
        extracted=result if status == "DONE" else None,
        error=error,
        queued_at=data.get("queued_at"),
        updated_at=data.get("updated_at"),
    )


@router.post("/create", response_model=ReviewCreateResponse)
async def review_create(
    receipt_id: str = Form(...),
    title: str = Form(...),
    content: str = Form(...),
    rating: int = Form(...),
    menu_name: str = Form(default=None),
    images: List[UploadFile] = File(default=[]),
    db: Session = Depends(get_db),
    current=Depends(get_current_member),
):
    imgs = images or []
    if len(imgs) > 3:
        raise HTTPException(status_code=400, detail="images max 3")


    print("현재 review_create 진입 :: ")

    try:
        out = await create_review_from_receipt(
            db=db,
            member_id=current.member_id,
            receipt_id=receipt_id,
            title=title,
            content=content,
            rating=rating,
            menu_name_override=menu_name,
            images=imgs,
        )
        return ReviewCreateResponse(review_id=out["review_id"], image_urls=out["image_urls"])
    except Exception as e:
        log_exception("router.review_create", e)
        raise

# active True or 1
@router.get("", response_model=list[ReviewRead])
def review_list(db: Session = Depends(get_db)):
    # return list_reviews(db, member_id=None, active_only=True)
    return list_reviews(db, member_id=None)

# active 상관없이 내것 전부
@router.get("/me", response_model=list[ReviewRead])
def review_my_list(db: Session = Depends(get_db), current=Depends(get_current_member)):
    print("review list 내것만 조회중")
    # return list_reviews(db, member_id=current.member_id, active_only=None)
    return list_reviews(db, member_id=current.member_id)

@router.get("/{review_id}", response_model=ReviewRead)
def review_detail(
    review_id: int,
    db: Session = Depends(get_db),
    current=Depends(get_current_member),
):
    print("review 상세 진입 :: ", current.member_id)

    return get_review_detail(db, review_id)


@router.patch("/{review_id}", response_model=ReviewContentUpdateResponse)
def review_update_content(
    review_id: int,
    payload: ReviewContentUpdate,
    db: Session = Depends(get_db),
    current=Depends(get_current_member),
):
    print("수정 들어옴", payload)

    return update_review_content_only(
        db,
        review_id=review_id,
        current_member_id=current.member_id,
        current_role=getattr(current, "role", None),
        new_content=payload.review_content,
    )

# CI/CD Test3