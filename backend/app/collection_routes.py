import json
from uuid import UUID

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from .collection_models import CollectionCreate
from .collections import CollectionService, MAX_UPLOAD_BYTES, MAX_ITEMS


def collection_router(repository):
    router = APIRouter(prefix="/api/v1/collections")

    def call(method, *args):
        try:
            return method(*args)
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from None
        except ValueError as exc:
            raise HTTPException(status_code=409 if str(exc) == "COLLECTION_BUSY" else 422,
                                detail=str(exc)) from None

    @router.post("", status_code=201)
    def create(request: CollectionCreate):
        return call(CollectionService(repository()).create, request)

    @router.post("/{collection_id}/items", status_code=201)
    async def upload(collection_id: UUID, files: list[UploadFile] = File(...),
                     timestamps_ms: str | None = Form(default=None)):
        service = CollectionService(repository())
        call(service.get, collection_id)
        if len(files) > MAX_ITEMS:
            raise HTTPException(status_code=413, detail="COLLECTION_ITEM_LIMIT")
        uploads, size = [], 0
        for file in files:
            body = await file.read(MAX_UPLOAD_BYTES + 1)
            size += len(body)
            if size > MAX_UPLOAD_BYTES:
                raise HTTPException(status_code=413, detail="COLLECTION_UPLOAD_TOO_LARGE")
            uploads.append((file.filename or "image", body))
        try:
            timestamps = json.loads(timestamps_ms) if timestamps_ms else None
            if timestamps is not None and not isinstance(timestamps, list):
                raise ValueError()
        except ValueError:
            raise HTTPException(status_code=422, detail="INVALID_TIMESTAMPS") from None
        return call(service.upload, collection_id, uploads, timestamps)

    @router.post("/{collection_id}/process")
    def process(collection_id: UUID):
        return call(CollectionService(repository()).process, collection_id)

    @router.get("/{collection_id}")
    def status(collection_id: UUID):
        return call(CollectionService(repository()).view, collection_id)

    @router.get("/{collection_id}/results")
    def results(collection_id: UUID):
        return call(CollectionService(repository()).view, collection_id)

    return router
