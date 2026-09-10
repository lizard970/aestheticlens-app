import json
import math
import os
from pathlib import Path
from threading import RLock
from typing import Protocol
from uuid import UUID

from .embeddings import EMBEDDING_DIMENSIONS
from .evidence import resolve_evidence
from .models import AnalysisJob, AnalysisResult, Asset, Feedback, StoredCaseEmbedding
from .collection_storage import MemoryCollectionStorage, PostgreSQLCollectionStorage
from .collection_models import AssetCollection, CollectionItem
from .evaluation import EvaluationCase, EvaluationRun, EvaluationFeedback
from .evaluation_storage import MemoryEvaluationStorage, PostgreSQLEvaluationStorage


class Repository(Protocol):
    def delete_knowledge_case(self, result_id: UUID) -> None: ...
    def save_evaluation_case(self, case: EvaluationCase) -> None: ...
    def get_evaluation_case(self, case_id: UUID) -> EvaluationCase | None: ...
    def list_evaluation_cases(self) -> list[EvaluationCase]: ...
    def save_evaluation_run(self, run: EvaluationRun) -> None: ...
    def get_evaluation_run(self, run_id: UUID) -> EvaluationRun | None: ...
    def save_evaluation_feedback(self, feedback: EvaluationFeedback) -> None: ...
    def list_evaluation_feedback(self, run_id: UUID) -> list[EvaluationFeedback]: ...
    def collection_lock(self, collection_id: UUID): ...
    def save_collection(self, collection: AssetCollection) -> None: ...
    def get_collection(self, collection_id: UUID) -> AssetCollection | None: ...
    def save_collection_item(self, item: CollectionItem) -> None: ...
    def list_collection_items(self, collection_id: UUID) -> list[CollectionItem]: ...
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
    def upsert_case_embedding(self, embedding: StoredCaseEmbedding) -> None: ...
    def delete_case_embedding(self, result_id: UUID) -> None: ...
    def get_case_embedding(self, result_id: UUID) -> StoredCaseEmbedding | None: ...
    def search_case_embeddings(self, embedding: list[float], limit: int,
                               result_ids: list[UUID] | None = None) -> list[tuple[StoredCaseEmbedding, float]]: ...


class InMemoryRepository(MemoryCollectionStorage, MemoryEvaluationStorage):
    def __init__(self) -> None:
        self.assets: dict[UUID, Asset] = {}
        self.jobs: dict[UUID, AnalysisJob] = {}
        self.results: dict[UUID, AnalysisResult] = {}
        self.feedback: dict[UUID, list[Feedback]] = {}
        self.asset_bytes: dict[UUID, bytes] = {}
        self.case_embeddings: dict[UUID, StoredCaseEmbedding] = {}
        self._review_lock = RLock()
        self.collections: dict[UUID, AssetCollection] = {}
        self.collection_items: dict[UUID, CollectionItem] = {}
        self.evaluation_records = {name: {} for name in
                                   ("evaluation_cases", "evaluation_runs", "evaluation_feedback")}

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

    def delete_knowledge_case(self, result_id: UUID) -> None:
        with self._review_lock:
            result = self.get_result(result_id)
            if result is None:
                raise LookupError("ANALYSIS_RESULT_NOT_FOUND")
            self.results.pop(result.job_id, None)
            self.jobs.pop(result.job_id, None)
            self.feedback.pop(result_id, None)
            self.case_embeddings.pop(result_id, None)
            for item in self.collection_items.values():
                if item.result_id == result_id or item.job_id == result.job_id:
                    item.result_id = item.job_id = None
                    item.status, item.progress_percent, item.error_info = "failed", 100, "ANALYSIS_RESULT_DELETED"
                    collection = self.collections.get(item.collection_id)
                    if collection:
                        collection.aggregation, collection.status = {}, "ready"

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

    def upsert_case_embedding(self, embedding: StoredCaseEmbedding) -> None:
        self.case_embeddings[embedding.result_id] = embedding.model_copy(deep=True)

    def delete_case_embedding(self, result_id: UUID) -> None:
        self.case_embeddings.pop(result_id, None)

    def get_case_embedding(self, result_id: UUID) -> StoredCaseEmbedding | None:
        embedding = self.case_embeddings.get(result_id)
        return embedding.model_copy(deep=True) if embedding else None

    def search_case_embeddings(self, embedding: list[float], limit: int,
                               result_ids: list[UUID] | None = None) -> list[tuple[StoredCaseEmbedding, float]]:
        def cosine(candidate: StoredCaseEmbedding) -> float:
            dot = sum(left * right for left, right in zip(candidate.embedding, embedding, strict=True))
            left_norm = math.sqrt(sum(value * value for value in candidate.embedding))
            right_norm = math.sqrt(sum(value * value for value in embedding))
            return dot / (left_norm * right_norm) if left_norm and right_norm else 0.0
        allowed = set(result_ids) if result_ids is not None else None
        candidates = (item for item in self.case_embeddings.values()
                      if allowed is None or item.result_id in allowed)
        ranked = sorted(((item, cosine(item)) for item in candidates),
                        key=lambda pair: pair[1], reverse=True)
        return [(item.model_copy(deep=True), score) for item, score in ranked[:limit]]


def _json_data(model) -> dict:
    return json.loads(model.model_dump_json())


class PostgreSQLRepository(PostgreSQLCollectionStorage, PostgreSQLEvaluationStorage):
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
        migrations = Path(__file__).parents[1] / "migrations"
        with self._connect() as connection:
            for migration in sorted(migrations.glob("*.sql")):
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
            with connection.cursor() as cursor:
                cursor.executemany(
                    "INSERT INTO feature_results (result_id, position, data) VALUES (%s, %s, %s)",
                    [(result.id, index, Jsonb(value)) for index, value in enumerate(features)],
                )
                cursor.executemany(
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

    def delete_knowledge_case(self, result_id: UUID) -> None:
        """Remove analysis records only. The asset row and image bytes intentionally remain."""
        with self._connect() as connection:
            row = connection.execute(
                "SELECT job_id FROM analysis_results WHERE id=%s FOR UPDATE", (result_id,)
            ).fetchone()
            if row is None:
                raise LookupError("ANALYSIS_RESULT_NOT_FOUND")
            job_id = row[0]
            # Collection JSON references are not foreign keys; invalidate derived snapshots.
            affected = connection.execute(
                "UPDATE collection_items SET data = data || "
                "'{\"result_id\":null,\"job_id\":null,\"status\":\"failed\",\"progress_percent\":100,"
                "\"error_info\":\"ANALYSIS_RESULT_DELETED\"}'::jsonb "
                "WHERE data->>'result_id'=%s OR data->>'job_id'=%s RETURNING collection_id",
                (str(result_id), str(job_id)),
            ).fetchall()
            for (collection_id,) in affected:
                connection.execute("UPDATE asset_collections SET data=data || "
                                   "'{\"aggregation\":{},\"status\":\"ready\"}'::jsonb WHERE id=%s", (collection_id,))
            # feedback does not cascade; result children/vector do.
            connection.execute("DELETE FROM feedback WHERE result_id=%s", (result_id,))
            connection.execute("DELETE FROM analysis_results WHERE id=%s", (result_id,))
            connection.execute("DELETE FROM analysis_jobs WHERE id=%s", (job_id,))

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

    @staticmethod
    def _vector_literal(embedding: list[float]) -> str:
        return "[" + ",".join(format(value, ".17g") for value in embedding) + "]"

    def upsert_case_embedding(self, embedding: StoredCaseEmbedding) -> None:
        if len(embedding.embedding) != EMBEDDING_DIMENSIONS:
            raise ValueError("EMBEDDING_DIMENSION_MISMATCH")
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO knowledge_case_embeddings "
                "(result_id, revision, model, source_text, embedding) VALUES (%s, %s, %s, %s, %s::vector) "
                "ON CONFLICT (result_id) DO UPDATE SET revision=EXCLUDED.revision, model=EXCLUDED.model, "
                "source_text=EXCLUDED.source_text, embedding=EXCLUDED.embedding, updated_at=now()",
                (embedding.result_id, embedding.revision, embedding.model, embedding.source_text,
                 self._vector_literal(embedding.embedding)),
            )

    def delete_case_embedding(self, result_id: UUID) -> None:
        with self._connect() as connection:
            connection.execute("DELETE FROM knowledge_case_embeddings WHERE result_id=%s", (result_id,))

    def get_case_embedding(self, result_id: UUID) -> StoredCaseEmbedding | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT result_id, revision, model, source_text, embedding::text "
                "FROM knowledge_case_embeddings WHERE result_id=%s", (result_id,)
            ).fetchone()
        if not row:
            return None
        return StoredCaseEmbedding(result_id=row[0], revision=row[1], model=row[2], source_text=row[3],
                                   embedding=json.loads(row[4]))

    def search_case_embeddings(self, embedding: list[float], limit: int,
                               result_ids: list[UUID] | None = None) -> list[tuple[StoredCaseEmbedding, float]]:
        vector = self._vector_literal(embedding)
        where = "" if result_ids is None else "WHERE result_id = ANY(%s::uuid[])"
        parameters = (vector, vector, limit) if result_ids is None else (vector, result_ids, vector, limit)
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT result_id, revision, model, source_text, embedding::text, "
                "1 - (embedding <=> %s::vector) AS similarity "
                f"FROM knowledge_case_embeddings {where} ORDER BY embedding <=> %s::vector LIMIT %s",
                parameters,
            ).fetchall()
        return [(StoredCaseEmbedding(result_id=row[0], revision=row[1], model=row[2], source_text=row[3],
                                     embedding=json.loads(row[4])), float(row[5])) for row in rows]


def repository_from_env() -> Repository:
    database_url = os.getenv("AESTHETICLENS_DATABASE_URL", "").strip()
    return PostgreSQLRepository(database_url) if database_url else InMemoryRepository()
