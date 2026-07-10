from __future__ import annotations

import json
import uuid
from typing import Any

from redis import asyncio as aioredis
from sqlalchemy import JSON, DateTime, Float, String, Text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from .config import settings
from .models import GenerateRequest, JobStage, JobStatus, VideoPlan, utcnow


class Base(DeclarativeBase):
    pass


class JobRow(Base):
    __tablename__ = "jobs"

    job_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    request_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    stage: Mapped[str] = mapped_column(String(64), nullable=False)
    progress: Mapped[float] = mapped_column(Float, nullable=False)
    message: Mapped[str] = mapped_column(String(512), nullable=False, default="")
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    result_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    plan_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    provider_summary_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[Any] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[Any] = mapped_column(DateTime(timezone=True), nullable=False)


class JobCheckpointRow(Base):
    __tablename__ = "job_checkpoints"

    job_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    last_node: Mapped[str] = mapped_column(String(64), nullable=False)
    state_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[Any] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[Any] = mapped_column(DateTime(timezone=True), nullable=False)


class PersistentJobStore:
    def __init__(self, database_url: str) -> None:
        self._engine = create_async_engine(database_url, future=True)
        self._session = async_sessionmaker(self._engine, class_=AsyncSession, expire_on_commit=False)

    async def init(self) -> None:
        async with self._engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    async def create(self, request: GenerateRequest) -> JobStatus:
        job_id = str(uuid.uuid4())
        now = utcnow()
        row = JobRow(
            job_id=job_id,
            request_json=request.model_dump(),
            stage=JobStage.queued.value,
            progress=0.0,
            message="Job created",
            error=None,
            result_url=None,
            plan_json=None,
            provider_summary_json=None,
            created_at=now,
            updated_at=now,
        )
        async with self._session() as session:
            session.add(row)
            await session.commit()

        return self._to_status(row)

    async def get_status(self, job_id: str) -> JobStatus | None:
        async with self._session() as session:
            row = await session.get(JobRow, job_id)
            if not row:
                return None
            return self._to_status(row)

    async def get_request(self, job_id: str) -> GenerateRequest | None:
        async with self._session() as session:
            row = await session.get(JobRow, job_id)
            if not row:
                return None
            return GenerateRequest.model_validate(row.request_json)

    async def update(
        self,
        job_id: str,
        *,
        stage: JobStage | None = None,
        progress: float | None = None,
        message: str | None = None,
        error: str | None = None,
        result_url: str | None = None,
        plan: VideoPlan | None = None,
        provider_summary: dict[str, str] | None = None,
    ) -> JobStatus | None:
        async with self._session() as session:
            row = await session.get(JobRow, job_id)
            if not row:
                return None
            if stage is not None:
                row.stage = stage.value
            if progress is not None:
                row.progress = progress
            if message is not None:
                row.message = message
            if error is not None:
                row.error = error
            if result_url is not None:
                row.result_url = result_url
            if plan is not None:
                row.plan_json = plan.model_dump()
            if provider_summary is not None:
                row.provider_summary_json = provider_summary
            row.updated_at = utcnow()
            await session.commit()
            await session.refresh(row)
            return self._to_status(row)

    @staticmethod
    def _to_status(row: JobRow) -> JobStatus:
        return JobStatus(
            job_id=row.job_id,
            stage=JobStage(row.stage),
            progress=row.progress,
            message=row.message,
            created_at=row.created_at,
            updated_at=row.updated_at,
            error=row.error,
            result_url=row.result_url,
            plan=VideoPlan.model_validate(row.plan_json) if row.plan_json else None,
            provider_summary=row.provider_summary_json,
        )

    async def save_checkpoint(self, job_id: str, last_node: str, state_json: dict[str, Any]) -> None:
        now = utcnow()
        async with self._session() as session:
            row = await session.get(JobCheckpointRow, job_id)
            if row is None:
                row = JobCheckpointRow(
                    job_id=job_id,
                    last_node=last_node,
                    state_json=state_json,
                    created_at=now,
                    updated_at=now,
                )
                session.add(row)
            else:
                row.last_node = last_node
                row.state_json = state_json
                row.updated_at = now
            await session.commit()

    async def load_checkpoint(self, job_id: str) -> dict[str, Any] | None:
        async with self._session() as session:
            row = await session.get(JobCheckpointRow, job_id)
            if row is None:
                return None
            return row.state_json

    async def clear_checkpoint(self, job_id: str) -> None:
        async with self._session() as session:
            row = await session.get(JobCheckpointRow, job_id)
            if row is not None:
                await session.delete(row)
                await session.commit()


class RedisJobQueue:
    def __init__(self, redis_url: str, queue_key: str) -> None:
        self._redis = aioredis.from_url(redis_url, decode_responses=True)
        self._queue_key = queue_key
        self._checkpoint_key_prefix = f"{queue_key}:checkpoint:"

    async def enqueue(self, job_id: str) -> None:
        await self._redis.lpush(self._queue_key, job_id)

    async def dequeue(self, timeout_s: int = 2) -> str | None:
        item = await self._redis.brpop(self._queue_key, timeout=timeout_s)
        if not item:
            return None
        _, job_id = item
        return job_id

    async def close(self) -> None:
        await self._redis.aclose()

    async def set_checkpoint_cache(self, job_id: str, payload: dict[str, Any], ttl_seconds: int = 86400) -> None:
        key = f"{self._checkpoint_key_prefix}{job_id}"
        await self._redis.set(key, json.dumps(payload), ex=ttl_seconds)

    async def get_checkpoint_cache(self, job_id: str) -> dict[str, Any] | None:
        key = f"{self._checkpoint_key_prefix}{job_id}"
        data = await self._redis.get(key)
        if not data:
            return None
        return json.loads(data)

    async def clear_checkpoint_cache(self, job_id: str) -> None:
        key = f"{self._checkpoint_key_prefix}{job_id}"
        await self._redis.delete(key)


store = PersistentJobStore(settings.database_url)
queue = RedisJobQueue(settings.redis_url, settings.redis_queue_key)
