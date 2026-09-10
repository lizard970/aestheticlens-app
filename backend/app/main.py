from uuid import UUID
import os

from fastapi import FastAPI, File, Header, HTTPException, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response

from .config import load_analysis_profiles
from .embeddings import EmbeddingError, configured_embedding_adapter
from .models import (AnalysisJob, AnalysisJobCreate, AnalysisResultView, Asset, Capability,
                     Feedback, FeedbackCreate, HybridSearchRequest, SemanticSearchRequest,
                     StructuredSearchRequest)
from .repositories import repository_from_env
from .services import MockAnalysisService
from .feature_pipeline import ImageNormalizationError
from .reviews import ReviewService
from .knowledge import HybridSearchService, SemanticSearchService, StoredKnowledgeRepository
from .answers import AnswerError, AnswerRequest, ChatAnswerAdapter, KnowledgeAnswer, KnowledgeAnswerService
from .collection_routes import collection_router
from .evaluation import evaluation_router


app = FastAPI(title="AestheticLens API", version="0.1.0")
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"], allow_methods=["*"], allow_headers=["*"])
repository = repository_from_env()
analysis_service = MockAnalysisService(repository)
embedding_adapter = configured_embedding_adapter()
semantic_search_service = SemanticSearchService(repository, embedding_adapter) if embedding_adapter else None
hybrid_search_service = HybridSearchService(repository, embedding_adapter)
allowed_media_types = {"image/jpeg", "image/png", "image/webp"}
app.include_router(collection_router(lambda: repository))
app.include_router(evaluation_router(lambda: repository))


@app.post("/api/v1/knowledge/answers", response_model=KnowledgeAnswer)
def knowledge_answer(request: AnswerRequest):
    try:
        return KnowledgeAnswerService(repository, hybrid_search_service, ChatAnswerAdapter(),
                                      float(os.getenv("AESTHETICLENS_ANSWER_MIN_SIMILARITY", "0.3"))).answer(request)
    except (AnswerError, EmbeddingError) as exc:
        code = str(exc)
        raise HTTPException(status_code=503 if code.endswith("NOT_CONFIGURED") else 502, detail=code) from None


@app.get("/api/v1/capabilities")
def get_capabilities() -> dict[str, list[Capability]]:
    return {"capabilities": [
        Capability(code="single_image_analysis", status="available", version="0.1"),
        Capability(code="video_shot_detection", status="not_implemented"),
        Capability(code="hybrid_retrieval", status="not_implemented"),
        Capability(code="structured_search", status="available", version="1.0"),
        Capability(code="semantic_search", status="available", version="1.0"),
        Capability(code="hybrid_search", status="available", version="1.0"),
        Capability(code="evaluation_runner", status="not_implemented"),
    ]}


@app.get("/api/v1/analysis-profiles")
def list_analysis_profiles():
    return {"items": list(load_analysis_profiles().values())}


@app.post("/api/v1/assets", status_code=status.HTTP_201_CREATED)
async def create_asset(file: UploadFile = File(...)) -> Asset:
    if file.content_type not in allowed_media_types:
        raise HTTPException(status_code=415, detail="UNSUPPORTED_MEDIA_TYPE")
    body = await file.read()
    asset = Asset(original_filename=file.filename or "upload", mime_type=file.content_type, size_bytes=len(body))
    repository.save_asset(asset, body)
    return asset


@app.post("/api/v1/analysis-jobs", status_code=status.HTTP_202_ACCEPTED)
def create_analysis_job(payload: AnalysisJobCreate, idempotency_key: str | None = Header(default=None)) -> AnalysisJob:
    del idempotency_key  # Stage 1A accepts the contract; persistence will enforce it later.
    if repository.get_asset(payload.target.id) is None:
        raise HTTPException(status_code=404, detail="ASSET_NOT_FOUND")
    if payload.analysis_profile_id not in load_analysis_profiles():
        raise HTTPException(status_code=404, detail="ANALYSIS_PROFILE_NOT_FOUND")
    job = AnalysisJob(**payload.model_dump())
    repository.save_job(job)
    try:
        analysis_service.run(job)
    except ImageNormalizationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return job


@app.get("/api/v1/analysis-jobs/{job_id}")
def get_analysis_job(job_id: UUID) -> AnalysisJob:
    job = repository.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="ANALYSIS_JOB_NOT_FOUND")
    return job


@app.get("/api/v1/analysis-jobs/{job_id}/result")
def get_analysis_result(job_id: UUID) -> AnalysisResultView:
    result = repository.get_result_by_job(job_id)
    if not result:
        raise HTTPException(status_code=404, detail="ANALYSIS_RESULT_NOT_FOUND")
    return ReviewService(repository).view(result.id)


@app.post("/api/v1/analysis-results/{result_id}/feedback", status_code=status.HTTP_201_CREATED)
def create_feedback(result_id: UUID, payload: FeedbackCreate) -> Feedback:
    try:
        return ReviewService(repository, semantic_search_service).save(result_id, payload)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409 if str(exc) == "REVISION_CONFLICT" else 422, detail=str(exc)) from exc


@app.get("/api/v1/analysis-results/{result_id}/feedback")
def read_feedback(result_id: UUID):
    try:
        return ReviewService(repository).history(result_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/api/v1/analysis-results/{result_id}")
def read_result(result_id: UUID, revision: int | None = None) -> AnalysisResultView:
    try:
        return ReviewService(repository).view(result_id, revision)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/api/v1/analysis-results")
def list_result_history():
    items = []
    for result in reversed(repository.list_results()):
        job = repository.get_job(result.job_id)
        asset = repository.get_asset(job.target.id) if job else None
        if asset:
            items.append({"id": result.id, "job_id": job.id, "asset_id": asset.id,
                          "original_filename": asset.original_filename, "created_at": job.created_at,
                          "summary": result.summary})
    return {"items": items}


@app.delete("/api/v1/knowledge/cases/{result_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_knowledge_case(result_id: UUID):
    """Delete knowledge/analysis records; retain the original asset bytes."""
    try:
        repository.delete_knowledge_case(result_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/api/v1/assets/{asset_id}/content")
def read_asset_content(asset_id: UUID):
    asset = repository.get_asset(asset_id)
    body = repository.get_asset_bytes(asset_id)
    if asset is None or body is None:
        raise HTTPException(status_code=404, detail="ASSET_NOT_FOUND")
    return Response(content=body, media_type=asset.mime_type, headers={"X-Content-Type-Options": "nosniff"})


@app.post("/api/v1/search/structured")
def structured_search(query: StructuredSearchRequest):
    return {"items": StoredKnowledgeRepository(repository).search(query)}


@app.post("/api/v1/search/semantic")
def semantic_search(query: SemanticSearchRequest):
    if semantic_search_service is None:
        raise HTTPException(status_code=503, detail="SEMANTIC_SEARCH_NOT_CONFIGURED")
    try:
        return {"items": semantic_search_service.search(query)}
    except EmbeddingError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.post("/api/v1/search/hybrid")
def hybrid_search(query: HybridSearchRequest):
    try:
        return {"items": hybrid_search_service.search(query)}
    except EmbeddingError as exc:
        status_code = 503 if str(exc) == "SEMANTIC_SEARCH_NOT_CONFIGURED" else 502
        raise HTTPException(status_code=status_code, detail=str(exc)) from exc
