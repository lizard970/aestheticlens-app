import os
from uuid import uuid4

import pytest

from app.knowledge import StoredKnowledgeRepository
from app.models import AnalysisJob, AnalysisResult, AnalysisTarget, Asset, DimensionResult, FeatureResult, FeedbackCreate, StructuredSearchRequest
from app.repositories import PostgreSQLRepository
from app.reviews import ReviewService


DATABASE_URL = os.getenv("AESTHETICLENS_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not DATABASE_URL, reason="AESTHETICLENS_TEST_DATABASE_URL is not configured")


def test_restart_persistence_revision_history_and_structured_search():
    first = PostgreSQLRepository(DATABASE_URL)
    first.migrate()
    unique_tag = f"restart-{uuid4()}"
    asset = Asset(original_filename=f"restart-{uuid4()}.png", mime_type="image/png", size_bytes=7)
    job = AnalysisJob(target=AnalysisTarget(type="asset", id=asset.id), analysis_profile_id="aesthetic-core-v1", requested_outputs=["features"])
    dimensions = [DimensionResult(code=code, label=code, observation="Original", interpretation="Original", confidence=.5,
                                  evidence_refs=["feature:metric#/value"])
                  for code in ["composition", "color", "lighting", "space", "style"]]
    result = AnalysisResult(job_id=job.id, summary="Persistent case", dimensions=dimensions, tags=[unique_tag],
                            provenance={"mode": "real", "semantic": {"status": "succeeded"}},
                            features=[FeatureResult(extractor_code="metric", extractor_version="1", feature_schema_version="1",
                                                   method="Metric", status="succeeded", values={"value": .75})])
    first.save_asset(asset, b"fixture")
    first.save_job(job)
    first.save_result(result)
    review = ReviewService(first)
    for index, dimension in enumerate(dimensions):
        review.save(result.id, FeedbackCreate(feedback_type="accept", target_path=f"/dimensions/{dimension.code}",
                                              comment=f"persist-{dimension.code}", base_revision=index))

    restarted = PostgreSQLRepository(DATABASE_URL)
    restored = ReviewService(restarted).view(result.id)
    assert restored.summary == "Persistent case"
    assert restored.feedback_history[0].revision == 5
    assert restored.feedback_history[-1].revision == 1
    assert restarted.get_asset_bytes(asset.id) == b"fixture"
    hits = StoredKnowledgeRepository(restarted).search(StructuredSearchRequest(
        tags=[unique_tag], numeric_filters=[{"feature_ref": "feature:metric#/value", "op": "gte", "value": .75}],
    ))
    assert [hit.result_id for hit in hits] == [result.id]
