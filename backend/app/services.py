from .config import load_analysis_profiles
from .models import AnalysisJob, AnalysisResult, DimensionResult, JobStatus
from .repositories import Repository


class MockAnalysisService:
    """Contract-valid adapter for stage 1A. It never claims image-specific analysis."""

    def __init__(self, repository: Repository) -> None:
        self.repository = repository

    def run(self, job: AnalysisJob) -> AnalysisResult:
        profile = load_analysis_profiles()[job.analysis_profile_id]
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
            summary="分析契约已跑通，等待接入真实视觉特征和多模态模型。",
            dimensions=dimensions,
            tags=["交互原型", "待真实模型分析"],
            provenance={
                "mode": "mock",
                "profile_version": profile.version,
                "pipeline_version": profile.pipeline_version,
            },
        )
        job.status = JobStatus.SUCCEEDED
        job.progress_stage = "complete"
        job.progress_percent = 100
        self.repository.results[job.id] = result
        return result
