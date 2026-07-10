from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Settings:
    database_url: str = os.getenv(
        "DATABASE_URL",
        "postgresql+asyncpg://video_agent:video_agent@localhost:5432/video_agent",
    )
    redis_url: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    redis_queue_key: str = os.getenv("REDIS_QUEUE_KEY", "video_agent:jobs")

    openai_api_key: str | None = os.getenv("OPENAI_API_KEY")
    replicate_api_token: str | None = os.getenv("REPLICATE_API_TOKEN")
    elevenlabs_api_key: str | None = os.getenv("ELEVENLABS_API_KEY")

    replicate_image_model: str = os.getenv(
        "REPLICATE_IMAGE_MODEL",
        "black-forest-labs/flux-schnell",
    )
    replicate_video_model: str = os.getenv(
        "REPLICATE_VIDEO_MODEL",
        "minimax/video-01",
    )
    elevenlabs_voice_id: str = os.getenv("ELEVENLABS_VOICE_ID", "EXAVITQu4vr4xnSDxMaL")


settings = Settings()
