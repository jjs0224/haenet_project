from typing import Any, Dict
from pydantic import BaseModel


class MenuUploadResponse(BaseModel):
    job_id: str
    upload_type: str = "menu"
    result: Dict[str, Any]


class MenuResultResponse(BaseModel):
    job_id: str
    result: Dict[str, Any]
