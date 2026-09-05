from uuid import UUID

from fastapi import FastAPI, File, Header, HTTPException, UploadFile, status

from .config import load_analysis_profiles
from .models import AnalysisJob, AnalysisJobCreate, AnalysisResult, Asset, Capability, Feedback, FeedbackCreate
from .repositories import InMemoryRepository
from .services import MockAnalysisService


app = FastAPI(title="AestheticLens API", version="0.1.0")
repository = InMemoryRepository()
analysis_service = MockAnalysisService(repository)
allowed_media_types = {"image/jpeg", "image/png", "image/webp"}


@app.get("/api/v1/capabilities")
def get_capabilities() -> dict[str, list[Capability]]:
    return {"capabilities": [
        Capability(code="single_image_analysis", status="available", version="0.1"),
        Capability(code="video_shot_detection", status="not_implemented"),
        Capability(code="hybrid_retrieval", status="not_implemented"),
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
    repository.assets[asset.id] = asset
    return asset


@app.post("/api/v1/analysis-jobs", status_code=status.HTTP_202_ACCEPTED)
def create_analysis_job(payload: AnalysisJobCreate, idempotency_key: str | None = Header(default=None)) -> AnalysisJob:
    del idempotency_key  # Stage 1A accepts the contract; persistence will enforce it later.
    if payload.target.id not in repository.assets:
        raise HTTPException(status_code=404, detail="ASSET_NOT_FOUND")
    if payload.analysis_profile_id not in load_analysis_profiles():
        raise HTTPException(status_code=404, detail="ANALYSIS_PROFILE_NOT_FOUND")
    job = AnalysisJob(**payload.model_dump())
    repository.jobs[job.id] = job
    analysis_service.run(job)
    return job


@app.get("/api/v1/analysis-jobs/{job_id}")
def get_analysis_job(job_id: UUID) -> AnalysisJob:
    job = repository.jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="ANALYSIS_JOB_NOT_FOUND")
    return job


@app.get("/api/v1/analysis-jobs/{job_id}/result")
def get_analysis_result(job_id: UUID) -> AnalysisResult:
    result = repository.results.get(job_id)
    if not result:
        raise HTTPException(status_code=404, detail="ANALYSIS_RESULT_NOT_FOUND")
    return result


@app.post("/api/v1/analysis-results/{result_id}/feedback", status_code=status.HTTP_201_CREATED)
def create_feedback(result_id: UUID, payload: FeedbackCreate) -> Feedback:
    if not any(result.id == result_id for result in repository.results.values()):
        raise HTTPException(status_code=404, detail="ANALYSIS_RESULT_NOT_FOUND")
    feedback = Feedback(result_id=result_id, **payload.model_dump())
    repository.feedback.setdefault(result_id, []).append(feedback)
    return feedback
