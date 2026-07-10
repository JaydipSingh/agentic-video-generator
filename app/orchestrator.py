from __future__ import annotations

from pathlib import Path
from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph

from . import agents
from .editor import render_video
from .models import GenerateRequest, JobStage, SceneAsset, VideoPlan
from .providers import ProviderBundle
from .storage import PersistentJobStore, RedisJobQueue


class GraphState(TypedDict, total=False):
    request: GenerateRequest
    job_id: str
    resume_from: str
    plan: VideoPlan
    assets: list[SceneAsset]
    voiceover_path: str | None
    output_path: str


class AgentOrchestrator:
    def __init__(
        self,
        store: PersistentJobStore,
        queue: RedisJobQueue,
        data_dir: Path,
        providers: ProviderBundle,
    ) -> None:
        self.store = store
        self.queue = queue
        self.providers = providers
        self.data_dir = data_dir
        self.assets_dir = data_dir / "assets"
        self.voice_dir = data_dir / "voice"
        self.outputs_dir = data_dir / "outputs"
        self.graph = self._build_graph()

    def _build_graph(self):
        builder = StateGraph(GraphState)
        builder.add_node("resume_router", self._resume_router_node)
        builder.add_node("director", self._director_node)
        builder.add_node("storyboard", self._storyboard_node)
        builder.add_node("asset_generator", self._asset_node)
        builder.add_node("voice", self._voice_node)
        builder.add_node("editor", self._editor_node)
        builder.add_node("critic", self._critic_node)

        builder.add_edge(START, "resume_router")
        builder.add_conditional_edges(
            "resume_router",
            self._resume_route,
            {
                "director": "director",
                "storyboard": "storyboard",
                "asset_generator": "asset_generator",
                "voice": "voice",
                "editor": "editor",
                "critic": "critic",
            },
        )
        builder.add_edge("director", "storyboard")
        builder.add_edge("storyboard", "asset_generator")
        builder.add_edge("asset_generator", "voice")
        builder.add_edge("voice", "editor")
        builder.add_edge("editor", "critic")
        builder.add_edge("critic", END)
        return builder.compile()

    async def run(self, job_id: str, request: GenerateRequest) -> None:
        state: GraphState = {
            "request": request,
            "job_id": job_id,
            "resume_from": "director",
        }
        checkpoint = await self._load_checkpoint(job_id)
        if checkpoint is not None:
            state = checkpoint
            await self.store.update(
                job_id,
                message=f"Resuming from checkpoint at node '{state.get('resume_from', 'director')}'",
            )

        try:
            result = await self.graph.ainvoke(state)

            await self.store.update(
                job_id,
                stage=JobStage.completed,
                progress=1.0,
                message="Video generated successfully",
                result_url=f"/outputs/{job_id}.mp4",
                plan=result.get("plan"),
                provider_summary=self.providers.summary,
            )
            await self.store.clear_checkpoint(job_id)
            await self.queue.clear_checkpoint_cache(job_id)
        except Exception as exc:  # noqa: BLE001
            await self.store.update(
                job_id,
                stage=JobStage.failed,
                progress=1.0,
                message="Pipeline failed (checkpoint saved for resume)",
                error=str(exc),
            )

    async def _resume_router_node(self, state: GraphState) -> GraphState:
        return {}

    def _resume_route(self, state: GraphState) -> str:
        start_node = state.get("resume_from", "director")
        if start_node in {"director", "storyboard", "asset_generator", "voice", "editor", "critic"}:
            return start_node
        return "director"

    async def _director_node(self, state: GraphState) -> GraphState:
        job_id = state["job_id"]
        request = state["request"]
        await self._mark_stage(job_id, "director")
        plan = await agents.director_agent(request)
        await self.store.update(job_id, plan=plan)
        update = {"plan": plan}
        await self._save_checkpoint("director", state, update)
        return update

    async def _storyboard_node(self, state: GraphState) -> GraphState:
        job_id = state["job_id"]
        await self._mark_stage(job_id, "storyboard")
        plan = state.get("plan")
        if plan is None:
            raise RuntimeError("Missing plan for storyboard node")
        revised_plan = await agents.storyboard_agent(plan)
        await self.store.update(job_id, plan=revised_plan)
        update = {"plan": revised_plan}
        await self._save_checkpoint("storyboard", state, update)
        return update

    async def _asset_node(self, state: GraphState) -> GraphState:
        job_id = state["job_id"]
        await self._mark_stage(job_id, "asset_generator")
        plan = state.get("plan")
        if plan is None:
            raise RuntimeError("Missing plan for asset node")
        job_assets_dir = self.assets_dir / job_id
        assets = await agents.asset_agent(plan, job_assets_dir, self.providers)
        update = {"assets": assets}
        await self._save_checkpoint("asset_generator", state, update)
        return update

    async def _voice_node(self, state: GraphState) -> GraphState:
        job_id = state["job_id"]
        request = state["request"]
        await self._mark_stage(job_id, "voice")
        plan = state.get("plan")
        if plan is None:
            raise RuntimeError("Missing plan for voice node")
        if not request.voiceover_enabled:
            update = {"voiceover_path": None}
            await self._save_checkpoint("voice", state, update)
            return update
        voice_path = await agents.voice_agent(plan, self.voice_dir / job_id, self.providers)
        update = {"voiceover_path": voice_path}
        await self._save_checkpoint("voice", state, update)
        return update

    async def _editor_node(self, state: GraphState) -> GraphState:
        job_id = state["job_id"]
        await self._mark_stage(job_id, "editor")
        plan = state.get("plan")
        assets = state.get("assets")
        if plan is None or assets is None:
            raise RuntimeError("Missing plan/assets for editor node")
        output_path = self.outputs_dir / f"{job_id}.mp4"
        rendered = await render_video(
            scene_assets=assets,
            output_path=output_path,
            aspect_ratio=plan.aspect_ratio,
            fps=plan.fps,
            narration_audio_path=state.get("voiceover_path"),
        )
        update = {"output_path": rendered}
        await self._save_checkpoint("editor", state, update)
        return update

    async def _critic_node(self, state: GraphState) -> GraphState:
        job_id = state["job_id"]
        await self._mark_stage(job_id, "critic")
        plan = state.get("plan")
        assets = state.get("assets")
        output_path = state.get("output_path")
        if plan is None or assets is None or output_path is None:
            raise RuntimeError("Missing plan/assets/output for critic node")
        ok, msg = await agents.critic_agent(plan, assets, output_path)
        if not ok:
            raise RuntimeError(msg)
        await self.store.update(job_id, message=msg)
        await self._save_checkpoint("critic", state, {})
        return {}

    async def _mark_stage(self, job_id: str, node_name: str) -> None:
        stage, msg, progress = _stage_message(node_name)
        await self.store.update(job_id, stage=stage, progress=progress, message=msg)

    async def _save_checkpoint(self, node_name: str, state: GraphState, update: GraphState) -> None:
        merged = dict(state)
        merged.update(update)
        job_id = merged["job_id"]
        payload = self._serialize_state(merged, last_node=node_name)
        await self.store.save_checkpoint(job_id=job_id, last_node=node_name, state_json=payload)
        await self.queue.set_checkpoint_cache(job_id, payload)

    async def _load_checkpoint(self, job_id: str) -> GraphState | None:
        cached = await self.queue.get_checkpoint_cache(job_id)
        source = cached
        if source is None:
            db_checkpoint = await self.store.load_checkpoint(job_id)
            if db_checkpoint is None:
                return None
            source = db_checkpoint
            if source is not None:
                await self.queue.set_checkpoint_cache(job_id, source)
        if source is None:
            return None
        return self._deserialize_state(source)

    def _serialize_state(self, state: GraphState, *, last_node: str) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "job_id": state["job_id"],
            "resume_from": _next_node_from_last(last_node),
        }
        if "request" in state:
            payload["request"] = state["request"].model_dump()
        if "plan" in state and state["plan"] is not None:
            payload["plan"] = state["plan"].model_dump()
        if "assets" in state and state["assets"] is not None:
            payload["assets"] = [a.model_dump() for a in state["assets"]]
        if "voiceover_path" in state:
            payload["voiceover_path"] = state.get("voiceover_path")
        if "output_path" in state and state.get("output_path") is not None:
            payload["output_path"] = state["output_path"]
        return payload

    def _deserialize_state(self, payload: dict[str, Any]) -> GraphState:
        state: GraphState = {
            "job_id": str(payload["job_id"]),
            "resume_from": str(payload.get("resume_from", "director")),
        }
        if payload.get("request") is not None:
            state["request"] = GenerateRequest.model_validate(payload["request"])
        if payload.get("plan") is not None:
            state["plan"] = VideoPlan.model_validate(payload["plan"])
        if payload.get("assets") is not None:
            state["assets"] = [SceneAsset.model_validate(a) for a in payload["assets"]]
        if "voiceover_path" in payload:
            state["voiceover_path"] = payload.get("voiceover_path")
        if payload.get("output_path") is not None:
            state["output_path"] = str(payload["output_path"])
        return state



def _stage_message(node_name: str) -> tuple[JobStage, str, float]:
    if node_name == "director":
        return JobStage.planning, "Director agent is creating the video plan", 0.0
    if node_name == "storyboard":
        return JobStage.storyboarding, "Storyboard agent is expanding shot prompts", 0.16
    if node_name == "asset_generator":
        return JobStage.generating_assets, "Asset agent is creating scene placeholders", 0.33
    if node_name == "voice":
        return JobStage.synthesizing_voice, "Voice agent is synthesizing narration", 0.5
    if node_name == "editor":
        return JobStage.editing, "Editor agent is rendering with ffmpeg", 0.66
    if node_name == "critic":
        return JobStage.critic_review, "Critic agent is validating final output", 0.83
    return JobStage.queued, "Queued", 0.0


def _next_node_from_last(last_node: str) -> str:
    order = ["director", "storyboard", "asset_generator", "voice", "editor", "critic"]
    if last_node not in order:
        return "director"
    idx = order.index(last_node)
    if idx >= len(order) - 1:
        return "critic"
    return order[idx + 1]
