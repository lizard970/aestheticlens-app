"""Versioned semantic boundary; public /api/v1 models remain unchanged."""
from __future__ import annotations

import base64
import json
import math
import os
import re
import time
from dataclasses import dataclass, field
from io import BytesIO
from pathlib import Path
from typing import Any, Literal, Protocol

import httpx
import numpy as np
from PIL import Image
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from .feature_pipeline import NormalizedImage
from .models import AnalysisProfile, DimensionResult, FeatureResult

CONFIG_DIR = Path(__file__).resolve().parent.parent / "config"
SCHEMA_VERSION = "1.0.0"


class StrictOutput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class SemanticDimension(StrictOutput):
    code: str
    observation: str = Field(min_length=1)
    interpretation: str = Field(min_length=1)
    confidence: float = Field(ge=0, le=1)
    evidence_refs: list[str]
    uncertainty: str | None


class SemanticOutput(StrictOutput):
    schema_version: Literal["1.0.0"]
    summary: str = Field(min_length=1)
    dimensions: list[SemanticDimension]
    tags: list[str]


@dataclass
class SemanticSettings:
    provider: str = "mock"
    base_url: str = ""
    model: str = ""
    api_key: str = field(default="", repr=False)
    timeout_seconds: float = 45
    max_retries: int = 1
    retry_delay_seconds: float = 0.5
    max_completion_tokens: int = 3000

    @classmethod
    def from_env(cls):
        return cls(
            provider=os.getenv("AESTHETICLENS_PROVIDER", "mock"),
            base_url=os.getenv("AESTHETICLENS_BASE_URL", ""),
            model=os.getenv("AESTHETICLENS_MODEL", ""),
            api_key=os.getenv("AESTHETICLENS_API_KEY", ""),
            timeout_seconds=float(os.getenv("AESTHETICLENS_TIMEOUT_SECONDS", "45")),
            max_retries=int(os.getenv("AESTHETICLENS_MAX_RETRIES", "1")),
            retry_delay_seconds=float(os.getenv("AESTHETICLENS_RETRY_DELAY_SECONDS", "0.5")),
            max_completion_tokens=int(os.getenv("AESTHETICLENS_MAX_COMPLETION_TOKENS", "3000")),
        )


@dataclass
class SemanticResult:
    summary: str
    dimensions: list[DimensionResult]
    tags: list[str]
    metadata: dict[str, Any]
    warnings: list[str] = field(default_factory=list)


class SemanticFailure(Exception):
    def __init__(self, code: str, metadata: dict[str, Any]):
        super().__init__(code)
        self.metadata = metadata


class AnalysisAdapter(Protocol):
    def analyze(self, image: NormalizedImage, features: list[FeatureResult],
                profile: AnalysisProfile) -> SemanticResult: ...


class MockAnalysisAdapter:
    def analyze(self, image, features, profile):
        return SemanticResult(
            summary="真实计算特征已完成；五维语义分析仍为 Mock。",
            dimensions=[DimensionResult(
                code=d.code, label=d.label, observation=f"{d.label}分析槽位已建立。",
                interpretation="当前为交互 Mock，尚未生成画面专属判断。",
                confidence=0.5, evidence_refs=[f"mock:{d.code}"],
            ) for d in profile.dimensions],
            tags=["真实计算特征", "Mock 语义分析"],
            metadata={"provider": "mock", "status": "mock"},
        )


def feature_evidence(features: list[FeatureResult]) -> dict[str, Any]:
    """Canonical leaf references: feature:<extractor_code>#<JSON pointer>."""
    evidence = {}

    def walk(value, prefix):
        if isinstance(value, dict):
            for key, child in value.items():
                escaped = str(key).replace("~", "~0").replace("/", "~1")
                walk(child, f"{prefix}/{escaped}")
        elif isinstance(value, list):
            for index, child in enumerate(value):
                walk(child, f"{prefix}/{index}")
        elif value is not None:
            evidence[prefix] = value

    for feature in features:
        if feature.status == "succeeded":
            walk(feature.values, f"feature:{feature.extractor_code}#")
    return evidence


def normalized_png(image: NormalizedImage) -> str:
    buffer = BytesIO()
    Image.fromarray(np.rint(np.clip(image.srgb, 0, 1) * 255).astype(np.uint8)).save(buffer, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buffer.getvalue()).decode("ascii")


def validate_output(content: str, evidence: dict, profile: AnalysisProfile, vocabulary: dict):
    output = SemanticOutput.model_validate_json(content)
    expected = {d.code for d in profile.dimensions}
    codes = [d.code for d in output.dimensions]
    if len(codes) != len(expected) or set(codes) != expected:
        raise ValueError("INVALID_DIMENSIONS")
    allowed_tags = {t["code"] for t in vocabulary["tags"]}
    if len(output.tags) != len(set(output.tags)) or not set(output.tags) <= allowed_tags:
        raise ValueError("INVALID_STYLE_TAGS")
    for dimension in output.dimensions:
        if any(ref not in evidence for ref in dimension.evidence_refs):
            raise ValueError("INVALID_FEATURE_REFERENCE")
        if not dimension.evidence_refs and not dimension.uncertainty:
            raise ValueError("MISSING_EVIDENCE_OR_UNCERTAINTY")
        if dimension.uncertainty is not None and not dimension.uncertainty.strip():
            raise ValueError("EMPTY_UNCERTAINTY")
        for text in (dimension.observation, dimension.interpretation, dimension.uncertainty or ""):
            refs = re.findall(r"\{\{([^{}]+)\}\}", text)
            if any(ref not in evidence or ref not in dimension.evidence_refs for ref in refs):
                raise ValueError("INVALID_INLINE_REFERENCE")
            plain = re.sub(r"\{\{[^{}]+\}\}", "", text)
            if re.search(r"[0-9{}]", plain):
                raise ValueError("UNSUPPORTED_INLINE_NUMBER")
    if re.search(r"[0-9{}]", output.summary):
        raise ValueError("UNSUPPORTED_SUMMARY_NUMBER")
    return output


def render_evidence(text: str, evidence: dict) -> str:
    return re.sub(r"\{\{([^{}]+)\}\}", lambda match: json.dumps(evidence[match[1]], ensure_ascii=False), text)


class ChatCompletionsAdapter:
    def __init__(self, settings: SemanticSettings, transport: httpx.BaseTransport | None = None):
        self.settings, self.transport = settings, transport

    def analyze(self, image, features, profile):
        settings = self.settings
        started = time.monotonic()
        metadata = {"provider": settings.provider, "model": settings.model,
                    "schema_version": SCHEMA_VERSION, "status": "failed",
                    "attempts": [], "cost": None, "usage": None}

        def fail(code):
            metadata.update(error_code=code, elapsed_ms=round((time.monotonic() - started) * 1000))
            raise SemanticFailure(code, metadata)

        if (settings.provider != "chat_completions" or not all((settings.base_url, settings.model, settings.api_key))
                or not 0 <= settings.max_retries <= 3 or settings.timeout_seconds <= 0
                or not math.isfinite(settings.timeout_seconds) or not math.isfinite(settings.retry_delay_seconds)
                or settings.retry_delay_seconds < 0 or settings.max_completion_tokens <= 0):
            fail("MODEL_CONFIGURATION_INVALID")
        try:
            endpoint = httpx.URL(settings.base_url)
            if endpoint.scheme not in {"http", "https"} or not endpoint.host or endpoint.userinfo or endpoint.query or endpoint.fragment:
                fail("MODEL_CONFIGURATION_INVALID")
        except httpx.InvalidURL:
            fail("MODEL_CONFIGURATION_INVALID")
        try:
            prompt = json.loads((CONFIG_DIR / "semantic_prompt.json").read_text(encoding="utf-8"))
            vocabulary = json.loads((CONFIG_DIR / "style_vocabulary.json").read_text(encoding="utf-8"))
            evidence = feature_evidence(features)
            metadata.update(prompt_version=prompt["version"], vocabulary_version=vocabulary["version"])
            payload = {
                "model": settings.model, "max_completion_tokens": settings.max_completion_tokens,
                "response_format": {"type": "json_object"},
                "messages": [
                    {"role": "system", "content": prompt["instructions"] + "\n" + prompt["numeric_policy"]},
                    {"role": "user", "content": [
                        {"type": "text", "text": json.dumps({
                            "dimensions": [d.model_dump() for d in profile.dimensions],
                            "schema": SemanticOutput.model_json_schema(),
                            "style_vocabulary": vocabulary,
                            "feature_evidence": evidence,
                            "normalization": image.provenance,
                            "feature_versions": {f.extractor_code: f.extractor_version for f in features if f.status == "succeeded"},
                        }, ensure_ascii=False)},
                        {"type": "image_url", "image_url": {"url": normalized_png(image)}},
                    ]},
                ],
            }
        except (OSError, ValueError, KeyError, TypeError):
            fail("MODEL_CONFIGURATION_INVALID")

        with httpx.Client(transport=self.transport, timeout=settings.timeout_seconds, follow_redirects=False) as client:
            for attempt in range(settings.max_retries + 1):
                entry = {"number": attempt + 1, "usage": None}
                metadata["attempts"].append(entry)
                retryable = False
                try:
                    response = client.post(settings.base_url.rstrip("/") + "/chat/completions",
                                           headers={"Authorization": f"Bearer {settings.api_key}"}, json=payload)
                    response.raise_for_status()
                    body = response.json()
                    usage = body.get("usage")
                    # Whitelist counters; never retain provider bodies, headers, or secrets.
                    if isinstance(usage, dict):
                        entry["usage"] = {k: v for k, v in usage.items()
                                          if k in {"prompt_tokens", "completion_tokens", "total_tokens"}
                                          and type(v) is int and v >= 0}
                    choice = body["choices"][0]
                    if choice.get("finish_reason") != "stop" or choice["message"].get("refusal"):
                        raise ValueError("INCOMPLETE_OR_REFUSED_OUTPUT")
                    output = validate_output(choice["message"]["content"], evidence, profile, vocabulary)
                    labels = {d.code: d.label for d in profile.dimensions}
                    dimensions = [DimensionResult(
                        code=d.code, label=labels[d.code], observation=render_evidence(d.observation, evidence),
                        interpretation=render_evidence(d.interpretation + (f"\n不确定性：{d.uncertainty}" if d.uncertainty else ""), evidence),
                        confidence=d.confidence, evidence_refs=d.evidence_refs,
                    ) for d in output.dimensions]
                    metadata.update(status="succeeded", elapsed_ms=round((time.monotonic() - started) * 1000),
                                    uncertainty={d.code: render_evidence(d.uncertainty, evidence) for d in output.dimensions if d.uncertainty},
                                    confidence_kind="model_self_report_uncalibrated")
                    known = [a["usage"] for a in metadata["attempts"] if a["usage"] is not None]
                    metadata["usage"] = {k: sum(a.get(k, 0) for a in known) for k in set().union(*(a.keys() for a in known))} if known else None
                    metadata["usage_complete"] = all(a["usage"] is not None for a in metadata["attempts"])
                    return SemanticResult(output.summary, dimensions, output.tags, metadata)
                except httpx.HTTPStatusError as exc:
                    code = f"MODEL_HTTP_{exc.response.status_code}"
                    retryable = exc.response.status_code == 429 or exc.response.status_code >= 500
                except httpx.TimeoutException:
                    code, retryable = "MODEL_TIMEOUT", True
                except httpx.TransportError:
                    code, retryable = "MODEL_TRANSPORT_ERROR", True
                except (ValidationError, ValueError, KeyError, IndexError, TypeError):
                    code = "MODEL_OUTPUT_INVALID"
                entry["error_code"] = code
                if not retryable or attempt == settings.max_retries:
                    fail(code)
                time.sleep(settings.retry_delay_seconds)


def configured_adapter() -> AnalysisAdapter:
    try:
        settings = SemanticSettings.from_env()
    except ValueError:
        raise SemanticFailure("MODEL_CONFIGURATION_INVALID", {"status": "failed", "cost": None}) from None
    return MockAnalysisAdapter() if settings.provider == "mock" else ChatCompletionsAdapter(settings)
