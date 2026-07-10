from __future__ import annotations

import math
from pathlib import Path

from .models import GenerateRequest, SceneAsset, ScenePlan, VideoPlan
from .providers import ProviderBundle


async def director_agent(request: GenerateRequest) -> VideoPlan:
    text = " ".join(request.story.strip().split())
    raw_parts = [p.strip() for p in text.replace("\n", " ").split(".") if p.strip()]

    scene_count = min(8, max(4, math.ceil(request.target_duration_s / 12)))
    if not raw_parts:
        raw_parts = ["A story scene"] * scene_count

    while len(raw_parts) < scene_count:
        raw_parts.append(raw_parts[-1])

    selected = raw_parts[:scene_count]
    duration = round(request.target_duration_s / scene_count, 2)

    scenes = [
        ScenePlan(
            scene_id=f"scene_{i+1:02d}",
            narration=part,
            visual_prompt=f"{request.style} visual of: {part}",
            duration_s=duration,
            camera="wide shot" if i % 2 == 0 else "medium shot",
            transition_out="dissolve" if i % 3 == 2 else "cut",
        )
        for i, part in enumerate(selected)
    ]

    return VideoPlan(
        title=request.title,
        style=request.style,
        aspect_ratio=request.aspect_ratio,
        fps=request.fps,
        total_duration_s=round(sum(s.duration_s for s in scenes), 2),
        scenes=scenes,
    )


async def storyboard_agent(plan: VideoPlan) -> VideoPlan:
    enriched = []
    for i, scene in enumerate(plan.scenes):
        enriched.append(
            scene.model_copy(
                update={
                    "visual_prompt": f"{scene.visual_prompt}; continuity character seed=hero_v1; scene index={i+1}",
                }
            )
        )

    return plan.model_copy(update={"scenes": enriched})


async def asset_agent(plan: VideoPlan, assets_dir: Path, providers: ProviderBundle) -> list[SceneAsset]:
    assets_dir.mkdir(parents=True, exist_ok=True)
    generated: list[SceneAsset] = []
    for i, scene in enumerate(plan.scenes):
        video_path = assets_dir / f"{scene.scene_id}.mp4"
        maybe_video = await providers.video_provider.generate(
            prompt=scene.visual_prompt,
            out_path=video_path,
            aspect_ratio=plan.aspect_ratio,
            duration_s=scene.duration_s,
        )
        if maybe_video:
            generated.append(
                SceneAsset(
                    scene_id=scene.scene_id,
                    media_type="video",
                    media_path=str(maybe_video),
                    duration_s=scene.duration_s,
                )
            )
            continue

        image_path = await providers.image_provider.generate(
            prompt=scene.visual_prompt,
            out_path=assets_dir / f"{scene.scene_id}.png",
            aspect_ratio=plan.aspect_ratio,
        )
        generated.append(
            SceneAsset(
                scene_id=scene.scene_id,
                media_type="image",
                media_path=str(image_path),
                duration_s=scene.duration_s,
            )
        )

    return generated


async def voice_agent(plan: VideoPlan, voice_dir: Path, providers: ProviderBundle) -> str:
    voice_dir.mkdir(parents=True, exist_ok=True)
    narration = " ".join(scene.narration for scene in plan.scenes)
    audio_path = await providers.tts_provider.synthesize(
        text=narration,
        out_path=voice_dir / "voiceover.mp3",
        duration_s=plan.total_duration_s,
    )
    return str(audio_path)


async def critic_agent(plan: VideoPlan, assets: list[SceneAsset], output_path: str) -> tuple[bool, str]:
    expected = len(plan.scenes)
    if len(assets) != expected:
        return False, f"Asset count mismatch: expected {expected}, got {len(assets)}"
    if not output_path:
        return False, "No rendered output path"
    return True, "Quality gate passed"
