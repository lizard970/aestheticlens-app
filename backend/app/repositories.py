from typing import Protocol
from uuid import UUID

from .models import AnalysisJob, AnalysisResult, Asset, Feedback


class Repository(Protocol):
    assets: dict[UUID, Asset]
    jobs: dict[UUID, AnalysisJob]
    results: dict[UUID, AnalysisResult]
    feedback: dict[UUID, list[Feedback]]


class InMemoryRepository:
    def __init__(self) -> None:
        self.assets: dict[UUID, Asset] = {}
        self.jobs: dict[UUID, AnalysisJob] = {}
        self.results: dict[UUID, AnalysisResult] = {}
        self.feedback: dict[UUID, list[Feedback]] = {}
