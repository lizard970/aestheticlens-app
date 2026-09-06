from .config import load_analysis_profiles, load_feature_config
from .feature_pipeline import ExtractorRegistry, ImageNormalizationError, normalize_image
from .models import AnalysisJob, AnalysisResult, DimensionResult, JobStatus
from .repositories import Repository


class MockAnalysisService:
    """Hybrid orchestrator: real features plus the preserved Stage 1A Mock semantics."""

    def __init__(self, repository: Repository, registry: ExtractorRegistry | None = None) -> None:
        self.repository = repository
        self.registry = registry or ExtractorRegistry()

    def run(self, job: AnalysisJob) -> AnalysisResult:
        profile = load_analysis_profiles()[job.analysis_profile_id]
        job.status = JobStatus.RUNNING
        job.progress_stage = "normalizing"
        job.progress_percent = 20
        try:
            image = normalize_image(self.repository.asset_bytes[job.target.id], load_feature_config())
        except ImageNormalizationError:
            job.status = JobStatus.FAILED
            job.progress_stage = "failed"
            job.progress_percent = 100
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
            raise ImageNormalizationError("ALL_FEATURE_EXTRACTORS_FAILED")
        dimensions = [
            DimensionResult(
                code=dimension.code,
                label=dimension.label,
                observation=f"{dimension.label}分析槽位已建立。",
                interpretation="当前为交互 Mock，尚未生成画面专属判断。",
                confidence=0.5,
                evidence_refs=[f"mock:{dimension.code}"],
            )
            for dimension in profile.dimensions
        ]
        result = AnalysisResult(
            job_id=job.id,
            summary="真实计算特征已完成；五维语义分析仍为 Mock。",
            dimensions=dimensions,
            tags=["真实计算特征", "Mock 语义分析"],
            provenance={
                "mode": "hybrid",
                "profile_version": profile.version,
                "pipeline_version": profile.pipeline_version,
            },
            features=features,
            warnings=image.warnings,
            completion_status="partial" if failed else "complete",
        )
        job.status = JobStatus.PARTIAL if failed else JobStatus.SUCCEEDED
        job.progress_stage = "complete"
        job.progress_percent = 100
        self.repository.results[job.id] = result
        return result
