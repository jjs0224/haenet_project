from typing import Any, Optional, List
from pydantic import BaseModel, Field


class CommunityCreate(BaseModel):
    review_ids: List[int] = Field(default_factory=list)
    template_id: int

class CommunityUpdate(BaseModel):
    recommend: Optional[int] = Field(default=None)
    community_active: Optional[bool] = Field(default=None)

class CommunityRead(BaseModel):
    community_id: int
    recommend: int
    member_id: int
    nickname: str
    community_active: bool
    liked: Optional[bool] = False
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    image_urls: List[str] = Field(default_factory=list)
    latest_comment_text: Optional[str] = None  # 댓글
    latest_comment_nickname: Optional[str] = None

class CommunityListRead(BaseModel):
    community_id: int
    member_id: int
    recommend: int
    nickname: str
    community_active: bool
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    image_urls: List[str] = Field(default_factory=list)
    latest_comment_text: Optional[str] = None  # 댓글
    latest_comment_nickname: Optional[str] = None  # 댓글
    
    # 저널 / 맵 구분
    community_type: Optional[str] = None


class CommunityEnqueueResponse(BaseModel):
    job_id: str
    status: str
    queued_at: str


class CommunityJobResponse(BaseModel):
    job_id: str
    status: str
    result: Optional[dict] = None
    error: Optional[Any] = None
    queued_at: Optional[str] = None
    updated_at: Optional[str] = None
