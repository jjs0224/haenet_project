from typing import List, Optional
from enum import Enum
from pydantic import BaseModel, Field, field_validator


class JournalType(str, Enum):
    journal = "journal"
    culture = "culture"


class JournalTemplate(BaseModel):
    template_type: Optional[int] = Field(1, description="Template type: 1=journal, 2=map")
    language: str = Field("en", description="Output language code (default: en)")
    style: Optional[dict] = Field(default=None, description="Optional style overrides")


class JournalMember(BaseModel):
    nickname: str = Field(..., min_length=1)
    gender: Optional[str] = None
    country: Optional[str] = None
    dislike_tags: Optional[List[str]] = None
    item_ids: Optional[List[int]] = None


class JournalReview(BaseModel):
    review_title: str = Field(..., min_length=1)
    review_content: str = Field(..., min_length=1)


class JournalGenerateRequest(BaseModel):
    journal_type: JournalType = JournalType.journal
    template: JournalTemplate
    member: JournalMember
    reviews: List[JournalReview] = Field(..., min_length=3, max_length=3)

    @field_validator("reviews")
    def _reviews_len(cls, v):
        if len(v) != 3:
            raise ValueError("reviews must contain exactly 3 items")
        return v


class EnqueueJobResponse(BaseModel):
    job_id: str
    status: str
    queued_at: str
