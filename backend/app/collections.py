from io import BytesIO
from pathlib import PurePosixPath
from uuid import UUID
import zipfile

from .collection_models import AssetCollection, CollectionCreate, CollectionItem
from .collection_aggregation import aggregate_collection
from .config import load_analysis_profiles
from .models import Asset, AnalysisJob, AnalysisTarget, JobStatus
from .services import MockAnalysisService


# Bounded uploads and decompression, independent of existing image normalization limits.
MAX_UPLOAD_BYTES = 64 * 1024 * 1024
MAX_EXPANDED_BYTES = 256 * 1024 * 1024
MAX_ITEMS = 100
IMAGE_TYPES = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp"}


def unpack_images(uploads):
    images, expanded = [], 0
    for filename, body in uploads:
        if len(body) > MAX_UPLOAD_BYTES:
            raise ValueError("COLLECTION_UPLOAD_TOO_LARGE")
        if filename.lower().endswith(".zip"):
            try:
                with zipfile.ZipFile(BytesIO(body)) as archive:
                    for entry in archive.infolist():
                        path = PurePosixPath(entry.filename.replace("\\", "/"))
                        if entry.is_dir() or path.suffix.lower() not in IMAGE_TYPES:
                            continue
                        if path.is_absolute() or ".." in path.parts or entry.flag_bits & 1:
                            raise ValueError("UNSAFE_ZIP_ENTRY")
                        expanded += entry.file_size
                        if expanded > MAX_EXPANDED_BYTES or entry.file_size > MAX_UPLOAD_BYTES or len(images) >= MAX_ITEMS:
                            raise ValueError("COLLECTION_UPLOAD_TOO_LARGE")
                        images.append((path.name, IMAGE_TYPES[path.suffix.lower()], archive.read(entry)))
            except (zipfile.BadZipFile, NotImplementedError, RuntimeError) as exc:
                raise ValueError("INVALID_ZIP") from exc
        else:
            suffix = PurePosixPath(filename).suffix.lower()
            if suffix not in IMAGE_TYPES:
                raise ValueError("UNSUPPORTED_MEDIA_TYPE")
            expanded += len(body)
            images.append((filename, IMAGE_TYPES[suffix], body))
        if expanded > MAX_EXPANDED_BYTES or len(images) > MAX_ITEMS:
            raise ValueError("COLLECTION_UPLOAD_TOO_LARGE")
    if not images:
        raise ValueError("NO_IMAGES")
    return images


class CollectionService:
    def __init__(self, repository, analysis=None):
        self.repository = repository
        self.analysis = analysis or MockAnalysisService(repository)

    def get(self, collection_id):
        collection = self.repository.get_collection(collection_id)
        if collection is None:
            raise LookupError("COLLECTION_NOT_FOUND")
        return collection

    def create(self, request: CollectionCreate):
        if request.analysis_profile_id not in load_analysis_profiles():
            raise ValueError("ANALYSIS_PROFILE_NOT_FOUND")
        collection = AssetCollection(**request.model_dump())
        self.repository.save_collection(collection)
        return collection

    def upload(self, collection_id: UUID, uploads, timestamps=None):
        images = unpack_images(uploads)
        if timestamps is not None and (len(timestamps) != len(images) or
                any(t is not None and (type(t) is not int or t < 0) for t in timestamps)):
            raise ValueError("INVALID_TIMESTAMPS")
        with self.repository.collection_lock(collection_id):
            collection = self.get(collection_id)
            existing = self.repository.list_collection_items(collection_id)
            if len(existing) + len(images) > MAX_ITEMS:
                raise ValueError("COLLECTION_ITEM_LIMIT")
            for index, (name, mime, body) in enumerate(images):
                asset = Asset(original_filename=name, mime_type=mime, size_bytes=len(body))
                self.repository.save_asset(asset, body)
                self.repository.save_collection_item(CollectionItem(collection_id=collection_id, asset_id=asset.id,
                    position=len(existing) + index, timestamp_ms=timestamps[index] if timestamps else None))
            collection.status, collection.aggregation = "ready", {}
            self.repository.save_collection(collection)
        return self.view(collection_id)

    def process(self, collection_id):
        with self.repository.collection_lock(collection_id):
            collection = self.get(collection_id)
            items = self.repository.list_collection_items(collection_id)
            if not items:
                raise ValueError("NO_IMAGES")
            collection.status = "running"
            self.repository.save_collection(collection)
            for item in items:
                if item.status not in {"queued", "running"}:
                    continue
                # Recover a result saved before a process interruption without calling the model again.
                result = self.repository.get_result_by_job(item.job_id) if item.job_id else None
                if result is None:
                    job = self.repository.get_job(item.job_id) if item.job_id else None
                    job = job or AnalysisJob(target=AnalysisTarget(type="asset", id=item.asset_id),
                        analysis_profile_id=collection.analysis_profile_id,
                        requested_outputs=["features", "aesthetic_analysis", "evidence"])
                    self.repository.save_job(job)
                    item.job_id, item.status, item.progress_percent = job.id, "running", 20
                    self.repository.save_collection_item(item)
                    try:
                        result = self.analysis.run(job)
                    except Exception as exc:
                        job.status, job.progress_stage, job.progress_percent = JobStatus.FAILED, "failed", 100
                        self.repository.save_job(job)
                        item.status, item.progress_percent = "failed", 100
                        # Avoid storing provider payloads/credentials in public error information.
                        item.error_info = "IMAGE_ANALYSIS_FAILED:" + type(exc).__name__
                        self.repository.save_collection_item(item)
                        continue
                item.result_id, item.progress_percent = result.id, 100
                item.status = "partial" if result.completion_status == "partial" else "succeeded"
                item.error_info = "PARTIAL_ANALYSIS" if item.status == "partial" else None
                self.repository.save_collection_item(item)
            collection.aggregation = aggregate_collection(self.repository, items)
            statuses = {item.status for item in items}
            collection.status = "succeeded" if statuses == {"succeeded"} else "failed" if statuses == {"failed"} else "partial"
            self.repository.save_collection(collection)
        return self.view(collection_id)

    def view(self, collection_id):
        collection = self.get(collection_id)
        items = self.repository.list_collection_items(collection_id)
        return {"collection": collection, "items": items,
                "progress_percent": sum(i.progress_percent for i in items) / len(items) if items else 0}
