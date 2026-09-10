"""Human evaluation records and descriptive metrics; never invokes analysis/scoring."""
from datetime import datetime
from typing import Any, Literal
from uuid import UUID, uuid4

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, JsonValue

from .models import utc_now


class EvaluationCaseCreate(BaseModel):
    asset_id: UUID
    expected_tags: list[str] | None = None
    evaluator_notes: str = ""
    category: str = Field(min_length=1)


class EvaluationCase(EvaluationCaseCreate):
    id: UUID = Field(default_factory=uuid4)


class EvaluationRun(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    case_id: UUID
    model_output: JsonValue
    timestamp: datetime = Field(default_factory=utc_now)


class EvaluationFeedbackCreate(BaseModel):
    run_id: UUID
    decision: Literal["approved", "modified", "rejected"]
    revision_count: int = Field(default=0, ge=0, strict=True)
    error_categories: list[str] = Field(default_factory=list)
    comments: str | None = None


class EvaluationFeedback(EvaluationFeedbackCreate):
    id: UUID = Field(default_factory=uuid4)


def approval_rate(feedback):
    rows = list(feedback)
    return sum(row.decision == "approved" for row in rows) / len(rows) if rows else 0.0


def modification_rate(feedback):
    rows = list(feedback)
    return sum(row.decision == "modified" for row in rows) / len(rows) if rows else 0.0


def rejection_rate(feedback):
    rows = list(feedback)
    return sum(row.decision == "rejected" for row in rows) / len(rows) if rows else 0.0


def average_revision_count(feedback):
    rows = list(feedback)
    return sum(row.revision_count for row in rows) / len(rows) if rows else 0.0


class EvaluationService:
    def __init__(self, repository):
        self.repository = repository

    def create_case(self, request: EvaluationCaseCreate):
        if self.repository.get_asset(request.asset_id) is None:
            raise LookupError("ASSET_NOT_FOUND")
        case = EvaluationCase(**request.model_dump())
        self.repository.save_evaluation_case(case)
        return case

    def record_run(self, case_id: UUID, model_output: Any):
        if self.repository.get_evaluation_case(case_id) is None:
            raise LookupError("EVALUATION_CASE_NOT_FOUND")
        run = EvaluationRun(case_id=case_id, model_output=model_output)
        self.repository.save_evaluation_run(run)
        return run

    def submit_feedback(self, request: EvaluationFeedbackCreate):
        if self.repository.get_evaluation_run(request.run_id) is None:
            raise LookupError("EVALUATION_RUN_NOT_FOUND")
        feedback = EvaluationFeedback(**request.model_dump())
        self.repository.save_evaluation_feedback(feedback)
        return feedback


def evaluation_router(repository):
    router = APIRouter(prefix="/api/v1/evaluation")

    def call(method, request):
        try:
            return method(request)
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from None

    @router.post("/cases", response_model=EvaluationCase, status_code=201)
    def create_case(request: EvaluationCaseCreate):
        return call(EvaluationService(repository()).create_case, request)

    @router.get("/cases", response_model=list[EvaluationCase])
    def list_cases():
        return repository().list_evaluation_cases()

    @router.post("/feedback", response_model=EvaluationFeedback, status_code=201)
    def feedback(request: EvaluationFeedbackCreate):
        return call(EvaluationService(repository()).submit_feedback, request)

    return router
