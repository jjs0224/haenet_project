from __future__ import annotations

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

class ReviewEnqueueResponse(BaseModel):
    job_id: str
    status: str
    queued_at: str

class ReviewJobResponse(BaseModel):
    job_id: str
    status: str
    extracted: Optional[Dict[str, Any]] = None
    error: Optional[Any] = None
    queued_at: Optional[str] = None
    updated_at: Optional[str] = None

class ReceiptVerifyResponse(BaseModel):
    receipt_id: str
    extracted: Dict[str, Any]

class ReviewCreateResponse(BaseModel):
    review_id: int
    image_urls: List[str] = Field(default_factory=list)
    review_items: List[int] = Field(default_factory=list)

class ReviewCreatePayload(BaseModel):
    receipt_id: str
    title: str
    content: str
    rating: int
    location: List[str] = Field(default_factory=list)
    # 추후 ocr 작업 끝나면 list로 변경 예정
    menu_name: List[str] = Field(default_factory=list)
    review_items: List[str] = Field(default_factory=list)

class ReviewRead(BaseModel):
    member_id: int
    review_id: int
    review_title: str
    review_content: str
    rating: int
    location: Optional[str] = None
    available: int
    nickname: str
    # menu_name: Optional[str] = None
    menu_name: List[str] = Field(default_factory=list)
    image_urls: List[str] = Field(default_factory=list)
    review_items: List[int] = Field(default_factory=list)

    created_at: Optional[str] = None
    updated_at: Optional[str] = None

class ReviewContentUpdate(BaseModel):
    review_content: Optional[str] = None

class ReviewContentUpdateResponse(BaseModel):
    review_id: int
    review_content: str