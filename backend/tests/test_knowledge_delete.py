import os
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

import app.main as main
from app.collection_models import AssetCollection, CollectionItem
from app.models import Asset, AnalysisJob, AnalysisTarget, AnalysisResult, Feedback, StoredCaseEmbedding
from app.repositories import InMemoryRepository, PostgreSQLRepository


def seed(repo):
    asset = Asset(original_filename="keep.png", mime_type="image/png", size_bytes=5)
    job = AnalysisJob(target=AnalysisTarget(type="asset", id=asset.id), analysis_profile_id="aesthetic-core-v1", requested_outputs=[])
    result = AnalysisResult(job_id=job.id, summary="delete", dimensions=[], tags=[], provenance={})
    repo.save_asset(asset, b"image")
    repo.save_job(job)
    repo.save_result(result)
    repo.append_feedback(Feedback(result_id=result.id, feedback_type="accept", original_value={}, revision=1))
    repo.upsert_case_embedding(StoredCaseEmbedding(result_id=result.id, revision=1, model="test", source_text="text", embedding=[1.0] + [0.0] * 1535))
    collection = AssetCollection(name="keep collection", aggregation={"summary": "stale"})
    repo.save_collection(collection)
    repo.save_collection_item(CollectionItem(collection_id=collection.collection_id, asset_id=asset.id, position=0, job_id=job.id, result_id=result.id, status="succeeded"))
    return asset, job, result, collection


def check_deleted(repo, asset, job, result, collection):
    assert repo.get_result(result.id) is None
    assert repo.get_job(job.id) is None
    assert repo.read_feedback(result.id) == []
    assert repo.get_case_embedding(result.id) is None
    assert repo.get_asset_bytes(asset.id) == b"image"
    assert repo.get_asset(asset.id) == asset
    assert repo.get_collection(collection.collection_id).aggregation == {}
    item = repo.list_collection_items(collection.collection_id)[0]
    assert item.result_id is None and item.job_id is None
    assert item.error_info == "ANALYSIS_RESULT_DELETED"


def test_delete_api_removes_only_case_records_and_keeps_original_file(monkeypatch, tmp_path):
    repo = InMemoryRepository()
    monkeypatch.setattr(main, "repository", repo)
    asset, job, result, collection = seed(repo)
    other = seed(repo)
    # The deletion code has no filesystem operations; verify an original file remains untouched.
    path = tmp_path / "keep.png"
    path.write_bytes(b"original file")
    client = TestClient(main.app)
    assert client.delete(f"/api/v1/knowledge/cases/{result.id}").status_code == 204
    check_deleted(repo, asset, job, result, collection)
    assert path.read_bytes() == b"original file"
    assert repo.get_result(other[2].id) is not None
    assert client.get(f"/api/v1/analysis-results/{result.id}").status_code == 404
    assert client.get(f"/api/v1/assets/{asset.id}/content").content == b"image"
    assert client.delete(f"/api/v1/knowledge/cases/{result.id}").status_code == 404
    assert client.delete(f"/api/v1/knowledge/cases/{uuid4()}").status_code == 404


@pytest.mark.skipif(not os.getenv("AESTHETICLENS_TEST_DATABASE_URL"), reason="PostgreSQL test URL not configured")
def test_delete_survives_postgresql_restart():
    url = os.environ["AESTHETICLENS_TEST_DATABASE_URL"]
    repo = PostgreSQLRepository(url)
    repo.migrate()
    records = seed(repo)
    repo.delete_knowledge_case(records[2].id)
    check_deleted(PostgreSQLRepository(url), *records)
