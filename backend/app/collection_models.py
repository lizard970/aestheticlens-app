from datetime import datetime
from typing import Any, Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, Field

from .models import utc_now


class CollectionCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    analysis_profile_id: str = "aesthetic-core-v1"


class AssetCollection(CollectionCreate):
    collection_id: UUID = Field(default_factory=uuid4)
    created_at: datetime = Field(default_factory=utc_now)
    status: Literal["ready", "running", "succeeded", "partial", "failed"] = "ready"
    aggregation: dict[str, Any] = Field(default_factory=dict)


class CollectionItem(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    collection_id: UUID
    asset_id: UUID
    position: int = Field(ge=0)
    timestamp_ms: int | None = Field(default=None, ge=0)
    status: Literal["queued", "running", "succeeded", "partial", "failed"] = "queued"
    progress_percent: int = Field(default=0, ge=0, le=100)
    job_id: UUID | None = None
    result_id: UUID | None = None
    error_info: str | None = None
