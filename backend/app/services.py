from .config import load_analysis_profiles, load_feature_config
from .feature_pipeline import ExtractorRegistry, ImageNormalizationError, normalize_image
from .models import AnalysisJob, AnalysisResult, DimensionResult, JobStatus
from .repositories import Repository
from .semantic_adapter import AnalysisAdapter, SemanticFailure, configured_adapter


class MockAnalysisService:
    """Existing orchestrator with injectable semantic adapter (legacy name retained)."""

    def __init__(self, repository: Repository, registry: ExtractorRegistry | None = None,
                 adapter: AnalysisAdapter | None = None) -> None:
        self.repository = repository
        self.registry = registry or ExtractorRegistry()
        self.adapter = adapter

    def run(self, job: AnalysisJob) -> AnalysisResult:
        profile = load_analysis_profiles()[job.analysis_profile_id]
        reusable = None
        # A retry creates a fresh semantic attempt, preserving prior raw output/reviews.
        for candidate in reversed(self.repository.list_results()):
            previous_job = self.repository.get_job(candidate.job_id)
            if (previous_job and previous_job.target == job.target
                    and previous_job.analysis_profile_id == job.analysis_profile_id
                    and candidate.features and all(f.status == "succeeded" for f in candidate.features)
                    and candidate.provenance.get("semantic", {}).get("status") in {"failed", "pending", "processing"}):
                reusable = candidate
                break
        job.status = JobStatus.RUNNING
        job.progress_stage = "analyzing" if reusable is not None else "normalizing"
        job.progress_percent = 20
        self.repository.save_job(job)
        try:
            content = self.repository.get_asset_bytes(job.target.id)
            if content is None:
                raise ImageNormalizationError("ASSET_NOT_FOUND")
            image = normalize_image(content, load_feature_config())
        except ImageNormalizationError:
            job.status = JobStatus.FAILED
            job.progress_stage = "failed"
            job.progress_percent = 100
            self.repository.save_job(job)
            raise
        job.progress_stage = "extracting_features" if reusable is None else "analyzing"
        job.progress_percent = 55 if reusable is None else 75
        self.repository.save_job(job)
        try:
            features = reusable.features if reusable is not None else self.registry.run(image, load_feature_config())
        except Exception as exc:
            job.status, job.progress_stage, job.progress_percent = JobStatus.FAILED, "failed", 100
            self.repository.save_job(job)
            raise ImageNormalizationError(f"FEATURE_EXTRACTION_FAILED:{type(exc).__name__}") from exc
        succeeded = [item for item in features if item.status == "succeeded"]
        failed = [item for item in features if item.status == "failed"]
        if not succeeded:
            job.status = JobStatus.FAILED
            job.progress_stage = "failed"
            job.progress_percent = 100
            self.repository.save_job(job)
            raise ImageNormalizationError("ALL_FEATURE_EXTRACTORS_FAILED")
        job.progress_stage = "analyzing"
        job.progress_percent = 75
        self.repository.save_job(job)
        feature_status = "failed" if failed else "completed"
        checkpoint = AnalysisResult(
            job_id=job.id, summary="计算特征已保存；等待语义分析。", dimensions=[], tags=[], features=features,
            provenance={"mode": "real", "semantic": {"status": "processing"},
                        "feature_analysis_status": feature_status, "semantic_analysis_status": "processing",
                        "reused_feature_result_id": str(reusable.id) if reusable else None},
            warnings=list(image.warnings), completion_status="partial",
        )
        # Durable before any network request, including quota/credential failures.
        self.repository.save_result(checkpoint)
        semantic_failed = False
        semantic_error = None
        warnings = list(image.warnings)
        try:
            semantic = (self.adapter or configured_adapter()).analyze(image, succeeded, profile)
            dimensions, summary, tags = semantic.dimensions, semantic.summary, semantic.tags
            metadata = semantic.metadata
            warnings.extend(semantic.warnings)
        except Exception as exc:
            semantic_failed = True
            semantic_error = str(exc) if isinstance(exc, SemanticFailure) else f"SEMANTIC_ANALYSIS_FAILED:{type(exc).__name__}"
            metadata = {**(exc.metadata if isinstance(exc, SemanticFailure) else {}), "status": "failed", "error_message": semantic_error}
            warnings.append(semantic_error)
            summary, tags = "计算特征已保留；五维模型分析未完成。", []
            dimensions = [DimensionResult(
                code=d.code, label=d.label, observation="模型分析不可用。",
                interpretation="本次调用失败，请检查警告后重试；已完成的计算结果可继续查看。",
                confidence=0, evidence_refs=[],
            ) for d in profile.dimensions]
        partial = bool(failed) or semantic_failed
        result = AnalysisResult(
            id=checkpoint.id,
            job_id=job.id,
            summary=summary,
            dimensions=dimensions,
            tags=tags,
            provenance={
                "mode": "hybrid" if metadata.get("status") == "mock" else "real",
                "profile_version": profile.version,
                "pipeline_version": "1.1.0",
                "semantic": metadata,
                "feature_analysis_status": feature_status,
                "semantic_analysis_status": "failed" if semantic_failed else "completed",
                "semantic_error_message": semantic_error,
                "reused_feature_result_id": str(reusable.id) if reusable else None,
            },
            features=features,
            warnings=warnings,
            completion_status="partial" if partial else "complete",
        )
        job.status = JobStatus.PARTIAL if partial else JobStatus.SUCCEEDED
        job.progress_stage = "semantic_failed" if semantic_failed else "complete"
        job.progress_percent = 100
        self.repository.save_result(result)
        self.repository.save_job(job)
        return result
