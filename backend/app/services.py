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
        job.status = JobStatus.RUNNING
        job.progress_stage = "normalizing"
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
        job.progress_stage = "extracting_features"
        job.progress_percent = 55
        features = self.registry.run(image, load_feature_config())
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
        semantic_failed = False
        warnings = list(image.warnings)
        try:
            semantic = (self.adapter or configured_adapter()).analyze(image, succeeded, profile)
            dimensions, summary, tags = semantic.dimensions, semantic.summary, semantic.tags
            metadata = semantic.metadata
            warnings.extend(semantic.warnings)
        except SemanticFailure as exc:
            semantic_failed = True
            metadata = exc.metadata
            warnings.append(str(exc))
            summary, tags = "计算特征已保留；五维模型分析未完成。", []
            dimensions = [DimensionResult(
                code=d.code, label=d.label, observation="模型分析不可用。",
                interpretation="本次调用失败，请检查警告后重试；已完成的计算结果可继续查看。",
                confidence=0, evidence_refs=[],
            ) for d in profile.dimensions]
        partial = bool(failed) or semantic_failed
        result = AnalysisResult(
            job_id=job.id,
            summary=summary,
            dimensions=dimensions,
            tags=tags,
            provenance={
                "mode": "hybrid" if metadata.get("status") == "mock" else "real",
                "profile_version": profile.version,
                "pipeline_version": "1.1.0",
                "semantic": metadata,
            },
            features=features,
            warnings=warnings,
            completion_status="partial" if partial else "complete",
        )
        job.status = JobStatus.PARTIAL if partial else JobStatus.SUCCEEDED
        job.progress_stage = "complete"
        job.progress_percent = 100
        self.repository.save_job(job)
        self.repository.save_result(result)
        return result
