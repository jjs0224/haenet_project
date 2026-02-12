import json
from fastapi import APIRouter, HTTPException

from backend.app.core.job_queue import connect_redis, enqueue_task, utc_now_iso
from backend.app.features.journal.schemas import JournalGenerateRequest, EnqueueJobResponse

router = APIRouter(prefix="/journal", tags=["journal"])


@router.post("/generate", response_model=EnqueueJobResponse, status_code=202)
def enqueue_journal(req: JournalGenerateRequest):
    try:
        r = connect_redis()
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"redis unavailable: {type(e).__name__}: {e}")

    payload = req.dict()
    job_id = enqueue_task(r, task="journal_generate", payload=payload)
    return EnqueueJobResponse(job_id=job_id, status="PENDING", queued_at=utc_now_iso())
