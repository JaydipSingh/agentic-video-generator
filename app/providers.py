from __future__ import annotations

import asyncio
import subprocess
from dataclasses import dataclass
from pathlib import Path

import httpx
from PIL import Image, ImageDraw

from .config import settings


@dataclass
class ProviderBundle:
    image_provider: "BaseImageProvider"
    video_provider: "BaseVideoProvider"
    tts_provider: "BaseTTSProvider"

    @property
    def summary(self) -> dict[str, str]:
        return {
            "image": self.image_provider.name,
            "video": self.video_provider.name,
            "tts": self.tts_provider.name,
        }


class BaseImageProvider:
    name = "base-image"

    async def generate(self, prompt: str, out_path: Path, aspect_ratio: str) -> Path:
        raise NotImplementedError


class BaseVideoProvider:
    name = "base-video"

    async def generate(self, prompt: str, out_path: Path, aspect_ratio: str, duration_s: float) -> Path | None:
        raise NotImplementedError


class BaseTTSProvider:
    name = "base-tts"

    async def synthesize(self, text: str, out_path: Path, duration_s: float | None = None) -> Path:
        raise NotImplementedError


class PlaceholderImageProvider(BaseImageProvider):
    name = "placeholder-image"

    async def generate(self, prompt: str, out_path: Path, aspect_ratio: str) -> Path:
        width, height = _resolution(aspect_ratio)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        # Brighter placeholder frame so fallback output is visibly non-blank.
        img = Image.new("RGB", (width, height), color="#0ea5e9")
        draw = ImageDraw.Draw(img)
        draw.rectangle((36, 36, width - 36, height - 36), outline="#ffffff", width=4)
        draw.rectangle((60, 60, width - 60, 280), fill="#0f172a")
        draw.text((88, 92), "Fallback Visual", fill="#f8fafc")
        draw.text((88, 152), _trim_text(prompt, 160), fill="#e2e8f0")
        img.save(out_path)
        return out_path


class ReplicateImageProvider(BaseImageProvider):
    name = "replicate-image"

    async def generate(self, prompt: str, out_path: Path, aspect_ratio: str) -> Path:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        prediction = await _replicate_create_prediction(
            model=settings.replicate_image_model,
            input_payload={
                "prompt": prompt,
                "aspect_ratio": aspect_ratio,
                "output_format": "png",
            },
        )
        result = await _replicate_wait(prediction["id"])
        output = result.get("output")
        if isinstance(output, list) and output:
            url = str(output[0])
        elif isinstance(output, str):
            url = output
        else:
            raise RuntimeError("Replicate image generation returned no output")

        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            out_path.write_bytes(resp.content)
        return out_path


class PlaceholderVideoProvider(BaseVideoProvider):
    name = "placeholder-video-disabled"

    async def generate(self, prompt: str, out_path: Path, aspect_ratio: str, duration_s: float) -> Path | None:
        return None


class ReplicateVideoProvider(BaseVideoProvider):
    name = "replicate-video"

    async def generate(self, prompt: str, out_path: Path, aspect_ratio: str, duration_s: float) -> Path | None:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        prediction = await _replicate_create_prediction(
            model=settings.replicate_video_model,
            input_payload={
                "prompt": prompt,
                "aspect_ratio": aspect_ratio,
                "duration": int(max(4, min(10, round(duration_s)))),
            },
        )
        result = await _replicate_wait(prediction["id"], timeout_s=420)
        output = result.get("output")
        if isinstance(output, list) and output:
            url = str(output[0])
        elif isinstance(output, str):
            url = output
        else:
            return None

        async with httpx.AsyncClient(timeout=240) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            out_path.write_bytes(resp.content)
        return out_path


class SilentTTSProvider(BaseTTSProvider):
    name = "silent-tts"

    async def synthesize(self, text: str, out_path: Path, duration_s: float | None = None) -> Path:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        duration = max(2, int(round(duration_s if duration_s is not None else len(text.split()) // 2)))
        cmd = [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "anullsrc=r=44100:cl=stereo",
            "-t",
            str(duration),
            str(out_path),
        ]
        await _run(cmd)
        return out_path


class ElevenLabsTTSProvider(BaseTTSProvider):
    name = "elevenlabs-tts"

    async def synthesize(self, text: str, out_path: Path, duration_s: float | None = None) -> Path:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        url = f"https://api.elevenlabs.io/v1/text-to-speech/{settings.elevenlabs_voice_id}"
        headers = {
            "xi-api-key": settings.elevenlabs_api_key or "",
            "accept": "audio/mpeg",
            "content-type": "application/json",
        }
        payload = {
            "text": text,
            "model_id": "eleven_multilingual_v2",
            "voice_settings": {"stability": 0.5, "similarity_boost": 0.75},
        }
        async with httpx.AsyncClient(timeout=180) as client:
            resp = await client.post(url, headers=headers, json=payload)
            resp.raise_for_status()
            out_path.write_bytes(resp.content)
        return out_path


def build_providers() -> ProviderBundle:
    if settings.replicate_api_token:
        image_provider: BaseImageProvider = ReplicateImageProvider()
        video_provider: BaseVideoProvider = ReplicateVideoProvider()
    else:
        image_provider = PlaceholderImageProvider()
        video_provider = PlaceholderVideoProvider()

    if settings.elevenlabs_api_key:
        tts_provider: BaseTTSProvider = ElevenLabsTTSProvider()
    else:
        tts_provider = SilentTTSProvider()

    return ProviderBundle(
        image_provider=image_provider,
        video_provider=video_provider,
        tts_provider=tts_provider,
    )


async def _replicate_create_prediction(model: str, input_payload: dict) -> dict:
    headers = {
        "Authorization": f"Token {settings.replicate_api_token}",
        "Content-Type": "application/json",
    }
    payload = {"input": input_payload}
    url = f"https://api.replicate.com/v1/models/{model}/predictions"
    async with httpx.AsyncClient(timeout=90) as client:
        resp = await client.post(url, headers=headers, json=payload)
        if resp.status_code >= 400:
            raise RuntimeError(f"Replicate create failed: {resp.text}")
        return resp.json()


async def _replicate_wait(prediction_id: str, timeout_s: int = 300) -> dict:
    headers = {"Authorization": f"Token {settings.replicate_api_token}"}
    url = f"https://api.replicate.com/v1/predictions/{prediction_id}"
    elapsed = 0
    interval = 3

    async with httpx.AsyncClient(timeout=60) as client:
        while elapsed < timeout_s:
            resp = await client.get(url, headers=headers)
            resp.raise_for_status()
            data = resp.json()
            status = data.get("status")
            if status == "succeeded":
                return data
            if status in {"failed", "canceled"}:
                raise RuntimeError(f"Replicate prediction failed: {data.get('error')}")
            await asyncio.sleep(interval)
            elapsed += interval

    raise TimeoutError("Timed out waiting for Replicate prediction")


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



def _trim_text(text: str, max_len: int) -> str:
    cleaned = " ".join(text.split())
    if len(cleaned) <= max_len:
        return cleaned
    return cleaned[: max_len - 3].rstrip() + "..."
