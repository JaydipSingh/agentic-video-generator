from __future__ import annotations

import os
import time
from typing import Any

import httpx
import streamlit as st

DEFAULT_API_BASE_URL = os.getenv("VIDEO_AGENT_API_BASE_URL", "http://127.0.0.1:8000")
TERMINAL_STAGES = {"completed", "failed"}


st.set_page_config(page_title="Video Agent UI", page_icon="🎬", layout="centered")
st.title("🎬 Agentic Video Generator")
st.caption("Minimal Streamlit UI for submit, status polling, preview, and resume.")


if "job_id" not in st.session_state:
    st.session_state.job_id = ""
if "last_status" not in st.session_state:
    st.session_state.last_status = None
if "auto_poll" not in st.session_state:
    st.session_state.auto_poll = False


with st.sidebar:
    st.header("API Settings")
    api_base_url = st.text_input("Backend URL", value=DEFAULT_API_BASE_URL).rstrip("/")
    poll_seconds = st.slider("Polling interval (seconds)", min_value=2, max_value=20, value=4)


def _http_post(url: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    with httpx.Client(timeout=60) as client:
        response = client.post(url, json=payload)
        response.raise_for_status()
        return response.json()


def _http_get(url: str) -> dict[str, Any]:
    with httpx.Client(timeout=60) as client:
        response = client.get(url)
        response.raise_for_status()
        return response.json()


def submit_job() -> None:
    payload = {
        "title": st.session_state.form_title,
        "story": st.session_state.form_story,
        "style": st.session_state.form_style,
        "target_duration_s": st.session_state.form_duration,
        "aspect_ratio": st.session_state.form_aspect_ratio,
        "fps": st.session_state.form_fps,
        "voiceover_enabled": st.session_state.form_voiceover_enabled,
    }
    try:
        data = _http_post(f"{api_base_url}/generate", payload)
        st.session_state.job_id = data["job_id"]
        st.session_state.auto_poll = True
        st.success(f"Job submitted: {st.session_state.job_id}")
    except Exception as exc:  # noqa: BLE001
        st.error(f"Submit failed: {exc}")


with st.form("generate_form"):
    st.subheader("Submit generation request")
    st.text_input("Title", value="The Last Lighthouse", key="form_title")
    st.text_area(
        "Story",
        value=(
            "A keeper receives a message from the sea. "
            "He repairs the old light. A storm arrives. "
            "The beam guides lost ships home."
        ),
        height=140,
        key="form_story",
    )
    col_a, col_b = st.columns(2)
    with col_a:
        st.text_input("Style", value="cinematic watercolor", key="form_style")
        st.number_input("Duration (seconds)", min_value=15, max_value=600, value=60, key="form_duration")
    with col_b:
        st.selectbox("Aspect ratio", options=["16:9", "9:16", "1:1"], index=0, key="form_aspect_ratio")
        st.number_input("FPS", min_value=12, max_value=60, value=24, key="form_fps")

    st.checkbox("Enable voiceover", value=True, key="form_voiceover_enabled")
    submitted = st.form_submit_button("Generate video")
    if submitted:
        submit_job()

st.divider()
st.subheader("Job status")

job_id_input = st.text_input("Job ID", value=st.session_state.job_id)
if job_id_input:
    st.session_state.job_id = job_id_input.strip()

col1, col2, col3 = st.columns([1, 1, 2])
with col1:
    refresh_clicked = st.button("Refresh status")
with col2:
    if st.button("Resume job"):
        if not st.session_state.job_id:
            st.warning("Provide a job ID first.")
        else:
            try:
                _http_post(f"{api_base_url}/jobs/{st.session_state.job_id}/resume")
                st.session_state.auto_poll = True
                st.success("Job requeued for resume.")
            except Exception as exc:  # noqa: BLE001
                st.error(f"Resume failed: {exc}")
with col3:
    st.session_state.auto_poll = st.checkbox("Auto polling", value=st.session_state.auto_poll)

if st.session_state.job_id and (refresh_clicked or st.session_state.auto_poll):
    try:
        status_data = _http_get(f"{api_base_url}/jobs/{st.session_state.job_id}")
        st.session_state.last_status = status_data
    except Exception as exc:  # noqa: BLE001
        st.error(f"Status fetch failed: {exc}")

status = st.session_state.last_status
if status:
    st.json(status)

    progress = float(status.get("progress", 0.0))
    st.progress(max(0.0, min(progress, 1.0)))

    stage = str(status.get("stage", "")).lower()
    if stage == "completed" and status.get("result_url"):
        video_url = f"{api_base_url}{status['result_url']}"
        st.success("Video is ready.")
        st.video(video_url)
        st.markdown(f"Open output: {video_url}")
    elif stage == "failed":
        st.error(status.get("error") or "Job failed")

if st.session_state.auto_poll and st.session_state.job_id:
    latest_stage = ""
    if st.session_state.last_status:
        latest_stage = str(st.session_state.last_status.get("stage", "")).lower()
    if latest_stage not in TERMINAL_STAGES:
        time.sleep(poll_seconds)
        st.rerun()
