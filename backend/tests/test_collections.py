from io import BytesIO
import os
import zipfile

import pytest
from fastapi.testclient import TestClient
from PIL import Image

import app.main as main
from app.collection_models import CollectionCreate
from app.collections import CollectionService, unpack_images
from app.repositories import InMemoryRepository, PostgreSQLRepository
from app.services import MockAnalysisService


def png(level):
    stream = BytesIO()
    Image.new("RGB", (16, 16), (level,) * 3).save(stream, format="PNG")
    return stream.getvalue()


def test_pipeline_partial_failure_order_aggregation_and_repeat(monkeypatch):
    repo = InMemoryRepository()
    monkeypatch.setattr(main, "repository", repo)
    calls = []
    original = MockAnalysisService.run
    def recording(self, job):
        calls.append(job.target.id)
        return original(self, job)
    monkeypatch.setattr(MockAnalysisService, "run", recording)
    client = TestClient(main.app)
    created = client.post("/api/v1/collections", json={"name": "batch"})
    assert created.status_code == 201
    collection_id = created.json()["collection_id"]
    response = client.post(f"/api/v1/collections/{collection_id}/items", files=[
        ("files", ("first.png", png(0), "image/png")),
        ("files", ("bad.png", b"corrupt", "image/png")),
        ("files", ("last.png", png(255), "image/png")),
    ], data={"timestamps_ms": "[0,100,200]"})
    assert response.status_code == 201
    assert [i["timestamp_ms"] for i in response.json()["items"]] == [0, 100, 200]
    result = client.post(f"/api/v1/collections/{collection_id}/process")
    assert result.status_code == 200
    payload = result.json()
    assert payload["collection"]["status"] == "partial"
    assert [i["status"] for i in payload["items"]] == ["succeeded", "failed", "succeeded"]
    assert [i["position"] for i in payload["items"]] == [0, 1, 2]
    assert len(calls) == 3
    aggregation = payload["collection"]["aggregation"]
    assert aggregation["completed_count"] == 2
    assert all(s["count"] == 2 for s in aggregation["feature_statistics"].values())
    assert aggregation["representative_item_ids"]
    assert "outlier_items" in aggregation
    failed_id = payload["items"][1]["id"]
    assert all(failed_id not in c["item_ids"] for c in aggregation["clusters"])
    assert client.get(f"/api/v1/collections/{collection_id}/results").json() == payload
    client.post(f"/api/v1/collections/{collection_id}/process")
    assert len(calls) == 3


def test_zip_preserves_entry_order_and_checks_paths():
    output = BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        archive.writestr("folder/z.png", png(100))
        archive.writestr("notes.txt", "ignored")
        archive.writestr("folder/a.png", png(150))
    service = CollectionService(InMemoryRepository())
    collection = service.create(CollectionCreate(name="ZIP"))
    view = service.upload(collection.collection_id, [("batch.zip", output.getvalue())])
    assert [service.repository.get_asset(i.asset_id).original_filename for i in view["items"]] == ["z.png", "a.png"]
    assert service.process(collection.collection_id)["collection"].status == "succeeded"
    output = BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        archive.writestr("../bad.png", png(0))
    with pytest.raises(ValueError, match="UNSAFE_ZIP_ENTRY"):
        unpack_images([("unsafe.zip", output.getvalue())])


def test_restart_resumes_saved_result_without_rerunning():
    repo = InMemoryRepository()
    service = CollectionService(repo)
    collection = service.create(CollectionCreate(name="resume"))
    service.upload(collection.collection_id, [("one.png", png(100))])
    service.process(collection.collection_id)
    item = repo.list_collection_items(collection.collection_id)[0]
    item.status, item.result_id = "running", None
    repo.save_collection_item(item)
    class MustNotRun:
        def run(self, job):
            raise AssertionError("Already persisted result must be recovered")
    restored = CollectionService(repo, MustNotRun()).process(collection.collection_id)
    assert restored["items"][0].status == "succeeded"
    assert restored["items"][0].result_id


def test_aggregation_identifies_feature_outlier_and_all_failed_is_empty():
    service = CollectionService(InMemoryRepository())
    collection = service.create(CollectionCreate(name="outlier"))
    service.upload(collection.collection_id,
                   [(f"{i}.png", png(level)) for i, level in enumerate([0] * 5 + [255])])
    view = service.process(collection.collection_id)
    aggregation = view["collection"].aggregation
    assert [i["item_id"] for i in aggregation["outlier_items"]] == [str(view["items"][-1].id)]
    assert len(aggregation["representative_item_ids"]) == len(aggregation["clusters"])
    failed = service.create(CollectionCreate(name="failed"))
    service.upload(failed.collection_id, [("bad.png", b"bad")])
    view = service.process(failed.collection_id)
    assert view["collection"].status == "failed"
    assert view["collection"].aggregation["feature_statistics"] == {}
    assert view["collection"].aggregation["representative_item_ids"] == []


@pytest.mark.skipif(not os.getenv("AESTHETICLENS_TEST_DATABASE_URL"), reason="PostgreSQL test URL not configured")
def test_postgresql_collection_restart():
    url = os.environ["AESTHETICLENS_TEST_DATABASE_URL"]
    repo = PostgreSQLRepository(url)
    repo.migrate()
    service = CollectionService(repo)
    collection = service.create(CollectionCreate(name="restart"))
    service.upload(collection.collection_id, [("first.png", png(50)), ("bad.png", b"bad"), ("last.png", png(200))])
    initial = service.process(collection.collection_id)
    restarted = CollectionService(PostgreSQLRepository(url)).view(collection.collection_id)
    assert restarted == initial
    assert restarted["collection"].status == "partial"
    assert restarted["collection"].aggregation["representative_item_ids"]
