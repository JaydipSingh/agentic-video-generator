from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field


class JobStage(str, Enum):
    queued = "queued"
    planning = "planning"
    storyboarding = "storyboarding"
    generating_assets = "generating_assets"
    synthesizing_voice = "synthesizing_voice"
    editing = "editing"
    critic_review = "critic_review"
    completed = "completed"
    failed = "failed"


class ScenePlan(BaseModel):
    scene_id: str
    narration: str
    visual_prompt: str
    duration_s: float = Field(gt=0)
    camera: str = "medium shot"
    transition_out: str = "cut"


class VideoPlan(BaseModel):
    title: str
    style: str = "cinematic"
    aspect_ratio: Literal["16:9", "9:16", "1:1"] = "16:9"
    fps: int = Field(default=24, ge=12, le=60)
    total_duration_s: float = Field(gt=0)
    scenes: list[ScenePlan]


class SceneAsset(BaseModel):
    scene_id: str
    media_type: Literal["image", "video"] = "image"
    media_path: str
    duration_s: float


class GenerateRequest(BaseModel):
    story: str = Field(min_length=10)
    title: str = "Generated Story Video"
    style: str = "cinematic"
    target_duration_s: int = Field(default=60, ge=15, le=600)
    aspect_ratio: Literal["16:9", "9:16", "1:1"] = "16:9"
    fps: int = Field(default=24, ge=12, le=60)
    voiceover_enabled: bool = True
    provider_hint: Literal["auto", "replicate", "openai"] = "auto"


class GenerateResponse(BaseModel):
    job_id: str
    status_url: str


class JobStatus(BaseModel):
    job_id: str
    stage: JobStage
    progress: float = Field(ge=0.0, le=1.0)
    message: str = ""
    created_at: datetime
    updated_at: datetime
    error: str | None = None
    result_url: str | None = None
    plan: VideoPlan | None = None
    provider_summary: dict[str, str] | None = None


class JobRecord(BaseModel):
    request: GenerateRequest
    status: JobStatus



def utcnow() -> datetime:
    return datetime.now(timezone.utc)
