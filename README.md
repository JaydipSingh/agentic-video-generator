# Agentic Video Generator (Starter)

This starter now includes:
- FastAPI endpoint: `/generate`
- Async queue-backed jobs with status polling: `/jobs/{job_id}`
- JSON schemas: `VideoPlan` and `ScenePlan`
- ffmpeg pipeline for image/video scene assembly + narration muxing
- Redis queue persistence
- Postgres job persistence
- Real provider adapters for image/video/TTS (Replicate + ElevenLabs)
- LangGraph checkpointing with Redis (hot cache) + Postgres (durable)
- Two UI options: Streamlit (`ui/streamlit_app.py`) and React (`ui/react`)

## Project status (as of 2026-06-14)

### Completed
- Core API scaffold with `POST /generate` and `GET /jobs/{job_id}`
- Multi-agent pipeline (`director` -> `storyboard` -> `asset_generator` -> `voice` -> `editor` -> `critic`)
- ffmpeg render pipeline with optional narration audio mux
- Provider abstraction with real adapters (Replicate + ElevenLabs) and local fallbacks
- Postgres-backed job persistence and Redis-backed job queue
- Local infra setup using Docker/Colima and `docker-compose`

### Verified in this workspace
- Python virtual environment created at `.venv`
- Dependencies installed from [requirements.txt](requirements.txt)
- Redis and Postgres containers started from [docker-compose.yml](docker-compose.yml)
- ffmpeg installed and available

### Current runtime note
- If health check returns connection error (exit code `7`), it usually means the API process is not currently running. Start it again with:
  - `./.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload`
  - then test `GET /health`.

### Next recommended milestone
- Add production worker separation (independent worker process), retry policies, and structured telemetry for each graph node.

## Architecture

Orchestration runtime: **LangGraph** state machine.

Pipeline graph:
1. `director` -> builds `VideoPlan`
2. `storyboard` -> enriches prompts for continuity
3. `asset_generator` -> uses provider adapters for scene media
4. `voice` -> TTS narration
5. `editor` -> ffmpeg render + audio mux
6. `critic` -> validates output consistency

Checkpoint/resume behavior:
- After each node completes, graph state is checkpointed.
- Checkpoints are stored durably in Postgres and cached in Redis.
- If a run fails, it can resume from the next node after the last successful checkpoint.
- Resume endpoint: `POST /jobs/{job_id}/resume`

## Provider strategy

- **Image**: Replicate (fallback: local placeholder image)
- **Video**: Replicate (fallback: disabled, image path used)
- **TTS**: ElevenLabs (fallback: silent audio track)

## Persistence strategy

- **Postgres** stores request, plan, status, progress, result URL, provider summary
- **Redis** stores queue items (`job_id`) for worker consumption

## Quickstart (macOS)

1) Install local software:

```bash
brew install ffmpeg docker
```

2) Start Postgres + Redis:

```bash
docker compose up -d
```

3) Create and activate virtual environment:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

4) Configure env:

```bash
cp .env.example .env
```

Then add your keys to `.env`:
- `REPLICATE_API_TOKEN`
- `ELEVENLABS_API_KEY`

5) Run API:

```bash
uvicorn app.main:app --reload
```

6) Submit a job:

```bash
curl -X POST http://127.0.0.1:8000/generate \
  -H "Content-Type: application/json" \
  -d '{
    "title":"The Last Lighthouse",
    "story":"A keeper receives a message from the sea. He repairs the old light. A storm arrives. The beam guides lost ships home.",
    "style":"cinematic watercolor",
    "target_duration_s":60,
    "aspect_ratio":"16:9",
    "fps":24,
    "voiceover_enabled":true
  }'
```

7) Poll job status:

```bash
curl http://127.0.0.1:8000/jobs/<job_id>
```

When completed, open:
`http://127.0.0.1:8000/outputs/<job_id>.mp4`

## Minimal Streamlit UI

Run backend first:

```bash
./.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

In another terminal, run UI:

```bash
./.venv/bin/streamlit run ui/streamlit_app.py
```

UI features:
- submit form
- job status polling
- result video preview
- resume button (`POST /jobs/{job_id}/resume`)

## React UI (Alternative)

Run backend first:

```bash
./.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

In another terminal:

```bash
cd ui/react
npm install
npm start
```

React UI runs at:
- `http://localhost:3000`

Optional: set backend URL via env var before starting React UI:

```bash
cd ui/react
REACT_APP_API_BASE_URL=http://127.0.0.1:8000 npm start
```

React UI features:
- submit form
- job status polling (manual + auto)
- result video preview
- resume button (`POST /jobs/{job_id}/resume`)
- responsive dark theme with Tailwind CSS

## Important notes

- Replicate model slugs can change by account/availability. Update in `.env` if needed.
- If ffmpeg is missing, rendering will fail with an explicit install message.
- If provider keys are missing, safe local fallbacks are used.
