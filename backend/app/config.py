import json
from functools import lru_cache
from pathlib import Path

from typing import Any

from .models import AnalysisProfile


CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "analysis_profiles.json"


@lru_cache(maxsize=1)
def load_analysis_profiles() -> dict[str, AnalysisProfile]:
    payload = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    profiles = [AnalysisProfile.model_validate(item) for item in payload["profiles"]]
    return {profile.id: profile for profile in profiles}


@lru_cache(maxsize=1)
def load_feature_config() -> dict[str, Any]:
    payload = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    return payload["feature_pipeline"]
