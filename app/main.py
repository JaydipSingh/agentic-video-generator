from __future__ import annotations

import asyncio
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles

from .models import GenerateRequest, GenerateResponse, JobStatus
from .orchestrator import AgentOrchestrator
from .providers import build_providers
from .storage import queue, store

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
OUTPUT_DIR = DATA_DIR / "outputs"
ASSETS_DIR = DATA_DIR / "assets"
VOICE_DIR = DATA_DIR / "voice"

DATA_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
ASSETS_DIR.mkdir(parents=True, exist_ok=True)
VOICE_DIR.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="Agentic Video Generator", version="0.1.0")
app.mount("/outputs", StaticFiles(directory=str(OUTPUT_DIR)), name="outputs")

providers = build_providers()
orchestrator = AgentOrchestrator(store=store, queue=queue, data_dir=DATA_DIR, providers=providers)
worker_task: asyncio.Task | None = None


@app.on_event("startup")
async def startup_event() -> None:
    global worker_task
    await store.init()
    worker_task = asyncio.create_task(_queue_worker())


@app.on_event("shutdown")
async def shutdown_event() -> None:
    global worker_task
    if worker_task is not None:
        worker_task.cancel()
        try:
            await worker_task
        except asyncio.CancelledError:
            pass
    await queue.close()


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/generate", response_model=GenerateResponse)
async def generate_video(request: GenerateRequest) -> GenerateResponse:
    status = await store.create(request)
    await queue.enqueue(status.job_id)

    return GenerateResponse(job_id=status.job_id, status_url=f"/jobs/{status.job_id}")


@app.get("/jobs/{job_id}", response_model=JobStatus)
async def get_job_status(job_id: str) -> JobStatus:
    status = await store.get_status(job_id)
    if not status:
        raise HTTPException(status_code=404, detail="Job not found")
    return status


@app.post("/jobs/{job_id}/resume", response_model=GenerateResponse)
async def resume_job(job_id: str) -> GenerateResponse:
    status = await store.get_status(job_id)
    if not status:
        raise HTTPException(status_code=404, detail="Job not found")
    if status.stage == status.stage.completed:
        raise HTTPException(status_code=400, detail="Job is already completed")
    await queue.enqueue(job_id)
    await store.update(job_id, stage=status.stage, message="Job requeued for checkpoint resume")
    return GenerateResponse(job_id=job_id, status_url=f"/jobs/{job_id}")


async def _queue_worker() -> None:
    while True:
        job_id = await queue.dequeue(timeout_s=2)
        if not job_id:
            await asyncio.sleep(0.1)
            continue
        request = await store.get_request(job_id)
        if request is None:
            await store.update(
                job_id,
                message="Request payload missing",
                error="Job request not found in database",
            )
            continue
        await orchestrator.run(job_id, request)
