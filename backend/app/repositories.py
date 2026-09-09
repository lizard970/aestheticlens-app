from typing import Protocol
from threading import RLock
from uuid import UUID

from .models import AnalysisJob, AnalysisResult, Asset, Feedback


class Repository(Protocol):
    assets: dict[UUID, Asset]
    jobs: dict[UUID, AnalysisJob]
    results: dict[UUID, AnalysisResult]
    feedback: dict[UUID, list[Feedback]]
    asset_bytes: dict[UUID, bytes]

    def get_result(self, result_id: UUID) -> AnalysisResult | None: ...
    def list_results(self) -> list[AnalysisResult]: ...
    def read_feedback(self, result_id: UUID) -> list[Feedback]: ...
    def append_feedback(self, feedback: Feedback) -> Feedback: ...


class InMemoryRepository:
    def __init__(self) -> None:
        self.assets: dict[UUID, Asset] = {}
        self.jobs: dict[UUID, AnalysisJob] = {}
        self.results: dict[UUID, AnalysisResult] = {}
        self.feedback: dict[UUID, list[Feedback]] = {}
        self.asset_bytes: dict[UUID, bytes] = {}
        self._review_lock = RLock()

    def get_result(self, result_id: UUID) -> AnalysisResult | None:
        result = next((item for item in self.results.values() if item.id == result_id), None)
        return result.model_copy(deep=True) if result else None

    def list_results(self) -> list[AnalysisResult]:
        return [item.model_copy(deep=True) for item in self.results.values()]

    def read_feedback(self, result_id: UUID) -> list[Feedback]:
        with self._review_lock:
            return [item.model_copy(deep=True) for item in self.feedback.get(result_id, [])]

    def append_feedback(self, feedback: Feedback) -> Feedback:
        with self._review_lock:
            history = self.feedback.setdefault(feedback.result_id, [])
            revision = history[-1].revision if history else 0
            if feedback.base_revision is not None and feedback.base_revision != revision:
                raise ValueError("REVISION_CONFLICT")
            saved = feedback.model_copy(deep=True, update={"revision": revision + 1})
            history.append(saved)
            return saved.model_copy(deep=True)
