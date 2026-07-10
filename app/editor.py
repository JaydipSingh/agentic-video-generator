from __future__ import annotations

import asyncio
import shlex
import subprocess
from pathlib import Path

from .models import SceneAsset


class FFmpegUnavailableError(RuntimeError):
    pass


async def render_video(
    scene_assets: list[SceneAsset],
    output_path: Path,
    *,
    aspect_ratio: str,
    fps: int,
    narration_audio_path: str | None = None,
) -> str:
    await _ensure_ffmpeg()

    output_path.parent.mkdir(parents=True, exist_ok=True)
    work_dir = output_path.parent / f"tmp_{output_path.stem}"
    work_dir.mkdir(parents=True, exist_ok=True)

    width, height = _resolution(aspect_ratio)
    clips: list[Path] = []

    for idx, asset in enumerate(scene_assets, start=1):
        clip = work_dir / f"clip_{idx:03d}.mp4"
        vf = (
            f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
            f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,format=yuv420p"
        )

        if asset.media_type == "image":
            cmd = [
                "ffmpeg",
                "-y",
                "-loop",
                "1",
                "-i",
                asset.media_path,
                "-t",
                str(asset.duration_s),
                "-vf",
                vf,
                "-r",
                str(fps),
                "-c:v",
                "libx264",
                "-pix_fmt",
                "yuv420p",
                str(clip),
            ]
        else:
            cmd = [
                "ffmpeg",
                "-y",
                "-i",
                asset.media_path,
                "-t",
                str(asset.duration_s),
                "-vf",
                vf,
                "-r",
                str(fps),
                "-c:v",
                "libx264",
                "-pix_fmt",
                "yuv420p",
                str(clip),
            ]
        await _run(cmd)
        clips.append(clip)

    concat_file = work_dir / "concat.txt"
    lines = [f"file {shlex.quote(str(path))}" for path in clips]
    concat_file.write_text("\n".join(lines), encoding="utf-8")

    merged_video = work_dir / "merged.mp4"
    cmd_concat = [
        "ffmpeg",
        "-y",
        "-f",
        "concat",
        "-safe",
        "0",
        "-i",
        str(concat_file),
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        "-r",
        str(fps),
        str(merged_video),
    ]
    await _run(cmd_concat)

    if narration_audio_path:
        cmd_mux = [
            "ffmpeg",
            "-y",
            "-i",
            str(merged_video),
            "-i",
            narration_audio_path,
            "-map",
            "0:v:0",
            "-map",
            "1:a:0",
            "-c:v",
            "copy",
            "-c:a",
            "aac",
            "-af",
            "apad",
            "-shortest",
            str(output_path),
        ]
        await _run(cmd_mux)
    else:
        merged_video.replace(output_path)

    return str(output_path)


async def _ensure_ffmpeg() -> None:
    try:
        await _run(["ffmpeg", "-version"])
    except Exception as exc:  # noqa: BLE001
        raise FFmpegUnavailableError(
            "ffmpeg is required. Install with Homebrew: brew install ffmpeg"
        ) from exc


async def _run(cmd: list[str]) -> None:
    def _execute() -> None:
        subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    await asyncio.to_thread(_execute)



def _resolution(aspect_ratio: str) -> tuple[int, int]:
    if aspect_ratio == "9:16":
        return 720, 1280
    if aspect_ratio == "1:1":
        return 1080, 1080
    return 1280, 720
