import json
import os
from pathlib import Path
from threading import RLock
from typing import Protocol
from uuid import UUID

from .evidence import resolve_evidence
from .models import AnalysisJob, AnalysisResult, Asset, Feedback


class Repository(Protocol):
    def save_asset(self, asset: Asset, content: bytes) -> None: ...
    def get_asset(self, asset_id: UUID) -> Asset | None: ...
    def get_asset_bytes(self, asset_id: UUID) -> bytes | None: ...
    def save_job(self, job: AnalysisJob) -> None: ...
    def get_job(self, job_id: UUID) -> AnalysisJob | None: ...
    def save_result(self, result: AnalysisResult) -> None: ...
    def get_result(self, result_id: UUID) -> AnalysisResult | None: ...
    def get_result_by_job(self, job_id: UUID) -> AnalysisResult | None: ...
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

    def save_asset(self, asset: Asset, content: bytes) -> None:
        self.assets[asset.id] = asset.model_copy(deep=True)
        self.asset_bytes[asset.id] = bytes(content)

    def get_asset(self, asset_id: UUID) -> Asset | None:
        asset = self.assets.get(asset_id)
        return asset.model_copy(deep=True) if asset else None

    def get_asset_bytes(self, asset_id: UUID) -> bytes | None:
        content = self.asset_bytes.get(asset_id)
        return bytes(content) if content is not None else None

    def save_job(self, job: AnalysisJob) -> None:
        self.jobs[job.id] = job.model_copy(deep=True)

    def get_job(self, job_id: UUID) -> AnalysisJob | None:
        job = self.jobs.get(job_id)
        return job.model_copy(deep=True) if job else None

    def save_result(self, result: AnalysisResult) -> None:
        self.results[result.job_id] = result.model_copy(deep=True)

    def get_result(self, result_id: UUID) -> AnalysisResult | None:
        result = next((item for item in self.results.values() if item.id == result_id), None)
        return result.model_copy(deep=True) if result else None

    def get_result_by_job(self, job_id: UUID) -> AnalysisResult | None:
        result = self.results.get(job_id)
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


def _json_data(model) -> dict:
    return json.loads(model.model_dump_json())


class PostgreSQLRepository:
    """PostgreSQL storage adapter; domain/review/search rules stay in services."""

    def __init__(self, database_url: str) -> None:
        if not database_url:
            raise ValueError("DATABASE_URL_REQUIRED")
        self.database_url = database_url

    def _connect(self):
        try:
            import psycopg
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError("Install backend requirements to use PostgreSQL") from exc
        return psycopg.connect(self.database_url)

    def migrate(self) -> None:
        migration = Path(__file__).parents[1] / "migrations" / "001_initial.sql"
        with self._connect() as connection:
            connection.execute(migration.read_text(encoding="utf-8"))

    def save_asset(self, asset: Asset, content: bytes) -> None:
        from psycopg.types.json import Jsonb
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO assets (id, data, content) VALUES (%s, %s, %s) "
                "ON CONFLICT (id) DO UPDATE SET data=EXCLUDED.data, content=EXCLUDED.content",
                (asset.id, Jsonb(_json_data(asset)), content),
            )

    def get_asset(self, asset_id: UUID) -> Asset | None:
        with self._connect() as connection:
            row = connection.execute("SELECT data FROM assets WHERE id=%s", (asset_id,)).fetchone()
        return Asset.model_validate(row[0]) if row else None

    def get_asset_bytes(self, asset_id: UUID) -> bytes | None:
        with self._connect() as connection:
            row = connection.execute("SELECT content FROM assets WHERE id=%s", (asset_id,)).fetchone()
        return bytes(row[0]) if row else None

    def save_job(self, job: AnalysisJob) -> None:
        from psycopg.types.json import Jsonb
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO analysis_jobs (id, asset_id, created_at, data) VALUES (%s, %s, %s, %s) "
                "ON CONFLICT (id) DO UPDATE SET data=EXCLUDED.data",
                (job.id, job.target.id, job.created_at, Jsonb(_json_data(job))),
            )

    def get_job(self, job_id: UUID) -> AnalysisJob | None:
        with self._connect() as connection:
            row = connection.execute("SELECT data FROM analysis_jobs WHERE id=%s", (job_id,)).fetchone()
        return AnalysisJob.model_validate(row[0]) if row else None

    def save_result(self, result: AnalysisResult) -> None:
        from psycopg.types.json import Jsonb
        result_data = _json_data(result)
        features = result_data.pop("features", [])
        evidence = [_json_data(item) for item in resolve_evidence(result)]
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO analysis_results (id, job_id, data) VALUES (%s, %s, %s) "
                "ON CONFLICT (id) DO UPDATE SET data=EXCLUDED.data",
                (result.id, result.job_id, Jsonb(result_data)),
            )
            connection.execute("DELETE FROM feature_results WHERE result_id=%s", (result.id,))
            connection.execute("DELETE FROM evidence_results WHERE result_id=%s", (result.id,))
            connection.executemany(
                "INSERT INTO feature_results (result_id, position, data) VALUES (%s, %s, %s)",
                [(result.id, index, Jsonb(value)) for index, value in enumerate(features)],
            )
            connection.executemany(
                "INSERT INTO evidence_results (result_id, position, data) VALUES (%s, %s, %s)",
                [(result.id, index, Jsonb(value)) for index, value in enumerate(evidence)],
            )

    def _result_from_row(self, row) -> AnalysisResult:
        result_id, data = row
        with self._connect() as connection:
            features = [item[0] for item in connection.execute(
                "SELECT data FROM feature_results WHERE result_id=%s ORDER BY position", (result_id,)
            ).fetchall()]
        return AnalysisResult.model_validate({**data, "features": features})

    def get_result(self, result_id: UUID) -> AnalysisResult | None:
        with self._connect() as connection:
            row = connection.execute("SELECT id, data FROM analysis_results WHERE id=%s", (result_id,)).fetchone()
        return self._result_from_row(row) if row else None

    def get_result_by_job(self, job_id: UUID) -> AnalysisResult | None:
        with self._connect() as connection:
            row = connection.execute("SELECT id, data FROM analysis_results WHERE job_id=%s", (job_id,)).fetchone()
        return self._result_from_row(row) if row else None

    def list_results(self) -> list[AnalysisResult]:
        with self._connect() as connection:
            rows = connection.execute("SELECT id, data FROM analysis_results ORDER BY created_at, id").fetchall()
        return [self._result_from_row(row) for row in rows]

    def read_feedback(self, result_id: UUID) -> list[Feedback]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT data FROM feedback WHERE result_id=%s ORDER BY revision", (result_id,)
            ).fetchall()
        return [Feedback.model_validate(row[0]) for row in rows]

    def append_feedback(self, feedback: Feedback) -> Feedback:
        from psycopg.types.json import Jsonb
        with self._connect() as connection:
            if connection.execute(
                "SELECT id FROM analysis_results WHERE id=%s FOR UPDATE", (feedback.result_id,)
            ).fetchone() is None:
                raise LookupError("ANALYSIS_RESULT_NOT_FOUND")
            revision = connection.execute(
                "SELECT COALESCE(MAX(revision), 0) FROM feedback WHERE result_id=%s", (feedback.result_id,)
            ).fetchone()[0]
            if feedback.base_revision is not None and feedback.base_revision != revision:
                raise ValueError("REVISION_CONFLICT")
            saved = feedback.model_copy(deep=True, update={"revision": revision + 1})
            connection.execute(
                "INSERT INTO feedback (id, result_id, revision, created_at, data) VALUES (%s, %s, %s, %s, %s)",
                (saved.id, saved.result_id, saved.revision, saved.created_at, Jsonb(_json_data(saved))),
            )
        return saved


def repository_from_env() -> Repository:
    database_url = os.getenv("AESTHETICLENS_DATABASE_URL", "").strip()
    return PostgreSQLRepository(database_url) if database_url else InMemoryRepository()
