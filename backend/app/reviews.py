import logging
from typing import Protocol
from uuid import UUID

from .evidence import resolve_evidence
from .models import AnalysisResultView, Feedback, FeedbackCreate, HumanRevision, ReviewedDimension
from .repositories import Repository


logger = logging.getLogger(__name__)


class ReviewService:
    def __init__(self, repository: Repository, indexer: "CaseIndexer | None" = None):
        self.repository = repository
        self.indexer = indexer

    def original(self, result_id: UUID):
        result = self.repository.get_result(result_id)
        if result is None:
            raise LookupError("ANALYSIS_RESULT_NOT_FOUND")
        return result

    def revision(self, result_id: UUID, revision: int | None = None) -> HumanRevision:
        original = self.original(result_id)
        history = self.repository.read_feedback(result_id)
        latest = history[-1].revision if history else 0
        if revision is not None and not 0 <= revision <= latest:
            raise LookupError("REVISION_NOT_FOUND")
        states = {d.code: ReviewedDimension(code=d.code, label=d.label, observation=d.observation,
                                           interpretation=d.interpretation) for d in original.dimensions}
        tags, excluded = list(original.tags), False
        for feedback in history:
            if revision is not None and feedback.revision > revision:
                break
            if feedback.target_path == "/knowledge_excluded":
                excluded = feedback.corrected_value
                continue
            if feedback.target_path == "/dimensions/style" and feedback.feedback_type == "edit" and "tags" in feedback.corrected_value:
                tags = list(feedback.corrected_value["tags"])
            # Legacy whole-result accept/reject applies to each existing dimension.
            parts = feedback.target_path.split("/") if feedback.target_path else []
            selected = [states[parts[2]]] if len(parts) >= 3 and parts[2] in states else list(states.values()) if not parts else []
            for state in selected:
                if feedback.feedback_type == "edit":
                    if len(parts) == 4 and parts[3] in {"observation", "interpretation"}:
                        setattr(state, parts[3], feedback.corrected_value)
                    elif len(parts) == 3 and isinstance(feedback.corrected_value, dict):
                        state.observation = feedback.corrected_value["observation"]
                        state.interpretation = feedback.corrected_value["interpretation"]
                state.review_status, state.feedback_id = feedback.feedback_type, feedback.id
        return HumanRevision(revision=latest if revision is None else revision, dimensions=list(states.values()), tags=tags, knowledge_excluded=excluded)

    def save(self, result_id: UUID, payload: FeedbackCreate) -> Feedback:
        original = self.original(result_id)
        parts = payload.target_path.split("/") if payload.target_path else []
        dimensions = {d.code: d for d in original.dimensions}
        case_action = payload.target_path == "/knowledge_excluded"
        if not case_action and parts and (len(parts) not in {3, 4} or parts[:2] != ["", "dimensions"] or parts[2] not in dimensions
                      or (len(parts) == 4 and parts[3] not in {"observation", "interpretation"})):
            raise ValueError("INVALID_FEEDBACK_TARGET")
        if payload.feedback_type == "edit":
            value = payload.corrected_value
            if case_action:
                valid = type(value) is bool
            elif len(parts) == 3:
                allowed = {"observation", "interpretation", "tags"} if parts[2] == "style" else {"observation", "interpretation"}
                valid = (isinstance(value, dict) and {"observation", "interpretation"} <= set(value) <= allowed
                         and all(isinstance(value[k], str) and value[k].strip() for k in ("observation", "interpretation"))
                         and ("tags" not in value or (isinstance(value["tags"], list) and all(isinstance(t, str) and t.strip() == t and t for t in value["tags"]) and len(set(value["tags"])) == len(value["tags"]))))
            else:
                valid = len(parts) == 4 and isinstance(value, str) and bool(value.strip())
            if not valid:
                raise ValueError("INVALID_FEEDBACK_EDIT")
        elif payload.corrected_value is not None:
            raise ValueError("CORRECTION_REQUIRES_EDIT")
        if case_action and payload.feedback_type != "edit":
            raise ValueError("INVALID_FEEDBACK_EDIT")
        raw_value = False if case_action else original.dimensions if not parts else dimensions[parts[2]].model_dump()
        if payload.target_path == "/dimensions/style":
            raw_value = {**raw_value, "tags": original.tags}
        if len(parts) == 4:
            raw_value = raw_value[parts[3]]
        if not parts:
            raw_value = [d.model_dump() for d in raw_value]
        saved = self.repository.append_feedback(Feedback(result_id=result_id, original_value=raw_value, **payload.model_dump()))
        if self.indexer is not None:
            try:
                self.indexer.refresh(result_id)
            except Exception:
                logger.exception("Feedback persisted but semantic index refresh failed for %s", result_id)
        return saved

    def view(self, result_id: UUID, revision: int | None = None) -> AnalysisResultView:
        original = self.original(result_id)
        job = self.repository.get_job(original.job_id)
        if job is None:
            raise LookupError("ANALYSIS_JOB_NOT_FOUND")
        return AnalysisResultView(**original.model_dump(), evidence=resolve_evidence(original),
                                  human_revision=self.revision(result_id, revision), asset_id=job.target.id,
                                  preview_url=f"/api/v1/assets/{job.target.id}/content",
                                  feedback_history=list(reversed(self.repository.read_feedback(result_id))))

    def history(self, result_id: UUID):
        return {"original_result": self.original(result_id), "feedback": list(reversed(self.repository.read_feedback(result_id))),
                "latest_revision": self.revision(result_id)}


class CaseIndexer(Protocol):
    def refresh(self, result_id: UUID) -> None: ...
