from datetime import datetime, timezone
from enum import Enum
from typing import Any, Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class JobStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    PARTIAL = "partial"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class Capability(BaseModel):
    code: str
    status: Literal["available", "not_implemented"]
    version: str | None = None


class AnalysisDimensionProfile(BaseModel):
    code: str
    label: str


class AnalysisProfile(BaseModel):
    id: str
    name: str
    version: str
    dimensions: list[AnalysisDimensionProfile]
    provider: str
    pipeline_version: str


class Asset(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    original_filename: str
    mime_type: str
    size_bytes: int
    status: Literal["ready"] = "ready"
    created_at: datetime = Field(default_factory=utc_now)


class AnalysisTarget(BaseModel):
    type: Literal["asset"]
    id: UUID


class AnalysisJobCreate(BaseModel):
    target: AnalysisTarget
    analysis_profile_id: str
    requested_outputs: list[Literal["features", "aesthetic_analysis", "evidence"]]


class AnalysisJob(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    target: AnalysisTarget
    analysis_profile_id: str
    requested_outputs: list[str]
    status: JobStatus = JobStatus.QUEUED
    progress_stage: str = "queued"
    progress_percent: int = 0
    created_at: datetime = Field(default_factory=utc_now)


class DimensionResult(BaseModel):
    code: str
    label: str
    observation: str
    interpretation: str
    confidence: float = Field(ge=0, le=1)
    evidence_refs: list[str]


class AnalysisResult(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    job_id: UUID
    schema_version: str = "1.0"
    summary: str
    dimensions: list[DimensionResult]
    tags: list[str]
    provenance: dict[str, Any]
    features: list["FeatureResult"] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    completion_status: Literal["complete", "partial"] = "complete"


class FeatureResult(BaseModel):
    extractor_code: str
    extractor_version: str
    feature_schema_version: str
    method: str
    standard: str | None = None
    status: Literal["succeeded", "failed"]
    parameters: dict[str, Any] = Field(default_factory=dict)
    values: dict[str, Any] = Field(default_factory=dict)
    artifacts: list[dict[str, Any]] = Field(default_factory=list)
    provenance: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    error_detail: str | None = None


class FeedbackCreate(BaseModel):
    feedback_type: Literal["accept", "edit", "reject", "flag_error"]
    target_path: str | None = None
    corrected_value: Any | None = None
    error_category: str | None = None
    comment: str | None = None
    base_revision: int | None = Field(default=None, ge=0)


class Feedback(FeedbackCreate):
    id: UUID = Field(default_factory=uuid4)
    result_id: UUID
    created_at: datetime = Field(default_factory=utc_now)
    revision: int = 0
    original_value: Any | None = None


class ResolvedEvidence(BaseModel):
    id: str
    label: str
    value: Any | None = None
    extractor_code: str | None = None
    field_path: str | None = None
    status: Literal["resolved", "invalid", "mock"]
    supports_dimensions: list[str]


class ReviewedDimension(BaseModel):
    code: str
    label: str
    observation: str
    interpretation: str
    review_status: Literal["unreviewed", "accept", "edit", "reject", "flag_error"] = "unreviewed"
    feedback_id: UUID | None = None


class HumanRevision(BaseModel):
    revision: int
    dimensions: list[ReviewedDimension]


class AnalysisResultView(AnalysisResult):
    evidence: list[ResolvedEvidence] = Field(default_factory=list)
    human_revision: HumanRevision
    asset_id: UUID
    preview_url: str


class NumericFilter(BaseModel):
    model_config = ConfigDict(extra="forbid")
    feature_ref: str = Field(pattern=r"^feature:[^#\s]+#/(?:[^~]|~[01])+$")
    op: Literal["eq", "gt", "gte", "lt", "lte"]
    value: float = Field(strict=True, allow_inf_nan=False)


class StructuredSearchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    tags: list[str] = Field(default_factory=list)
    numeric_filters: list[NumericFilter] = Field(default_factory=list)


class SearchableCase(BaseModel):
    asset_id: UUID
    result_id: UUID
    job_id: UUID
    original_filename: str
    preview_url: str
    tags: list[str]
    revision: int
    preview_text: str
