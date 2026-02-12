from typing import Any, Dict, Optional
from pydantic import BaseModel


class MenuUploadResponse(BaseModel):
    job_id: str
    upload_type: str = "menu"
    result: Dict[str, Any]


class MenuEnqueueResponse(BaseModel):
    job_id: str
    status: str
    queued_at: str


class MenuResultResponse(BaseModel):
    job_id: str
    result: Dict[str, Any]


class MenuJobResponse(BaseModel):
    job_id: str
    status: str
    result: Optional[Dict[str, Any]] = None
    error: Optional[Any] = None
    queued_at: Optional[str] = None
    updated_at: Optional[str] = None
