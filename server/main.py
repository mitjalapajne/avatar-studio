"""Avatar Studio API: avatar setup, video jobs on RunPod, MP4 storage.

Run:  uvicorn main:app --reload --port 8000   (from the server/ directory)
"""

from __future__ import annotations

import asyncio
import base64
import io
import logging
import shutil
import subprocess
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from PIL import Image
from pydantic import BaseModel, Field

import runpod_client
import store

load_dotenv(Path(__file__).resolve().parent / ".env")
log = logging.getLogger("avatar-studio")
logging.basicConfig(level=logging.INFO)

MAX_SCRIPT_CHARS = 600          # roughly 30 seconds of speech
MAX_VOICE_SECONDS = 12          # F5-TTS works best with a 5–12 s reference clip
MIN_VOICE_SECONDS = 3
POLL_SECONDS = 5

_tasks: dict[str, asyncio.Task] = {}


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---- lifecycle: resume any jobs that were in flight when the server stopped ----

@asynccontextmanager
async def lifespan(app: FastAPI):
    store.ensure_dirs()
    for v in store.list_videos():
        if v["status"] in ("queued", "running") and v.get("runpod_job_id"):
            _start_poller(v["id"])
    yield
    for t in _tasks.values():
        t.cancel()


app = FastAPI(title="Avatar Studio", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---- avatar ------------------------------------------------------------------

def _avatar_public(a: dict | None) -> dict | None:
    if not a:
        return None
    return {
        "name": a["name"],
        "created_at": a["created_at"],
        "image_url": "/api/avatar/image",
        "has_custom_voice": a["has_custom_voice"],
        "voice_seconds": a.get("voice_seconds"),
    }


@app.get("/api/status")
def status_check():
    return {
        "runpod_configured": runpod_client.is_configured(),
        "ffmpeg": shutil.which("ffmpeg") is not None,
    }


@app.get("/api/avatar")
def get_avatar():
    return _avatar_public(store.get_avatar())


@app.get("/api/avatar/image")
def get_avatar_image():
    path = store.AVATAR_DIR / "image.jpg"
    if not path.exists():
        raise HTTPException(404, "No avatar image")
    return FileResponse(path, media_type="image/jpeg")


@app.post("/api/avatar")
async def create_avatar(
    name: str = Form(...),
    image: UploadFile | None = File(None),
    voice_mode: str = Form("default"),          # "default" | "custom"
    voice: UploadFile | None = File(None),
    voice_transcript: str = Form(""),
):
    previous = store.get_avatar()
    if voice_mode not in ("default", "custom"):
        raise HTTPException(400, "voice_mode must be default or custom")
    name = name.strip()
    if not name:
        raise HTTPException(400, "Give your avatar a name")
    if len(name) > 60:
        raise HTTPException(400, "Name must be 60 characters or fewer")

    if image is not None and image.filename:
        raw = await image.read()
        try:
            img = Image.open(io.BytesIO(raw)).convert("RGB")
        except Exception:
            raise HTTPException(400, "Could not read that image. Use a JPG or PNG.")
        img.thumbnail((1024, 1024))  # keeps RunPod payloads small; the model works at ~480–720p anyway
        store.ensure_dirs()
        img.save(store.AVATAR_DIR / "image.jpg", "JPEG", quality=92)
    elif previous is None:
        raise HTTPException(400, "Add a photo of yourself")

    has_voice = False
    voice_seconds = previous.get("voice_seconds") if previous else None
    if voice_mode == "custom":
        if voice is not None and voice.filename:
            src = store.AVATAR_DIR / "voice_upload"
            src.write_bytes(await voice.read())
            dst = store.AVATAR_DIR / "voice.wav"
            try:
                voice_seconds = _convert_voice(src, dst)
            finally:
                src.unlink(missing_ok=True)
            (store.AVATAR_DIR / "voice_transcript.txt").write_text(voice_transcript.strip(), encoding="utf-8")
            has_voice = True
        elif previous and previous["has_custom_voice"]:
            has_voice = True  # keep the voice already saved
        else:
            raise HTTPException(400, "Choose a voice clip, or use the default voice")

    record = {
        "name": name,
        "created_at": now(),
        "has_custom_voice": has_voice,
        "voice_seconds": voice_seconds if has_voice else None,
    }
    store.save_avatar(record)
    return _avatar_public(record)


def _convert_voice(src: Path, dst: Path) -> float:
    """Convert any audio to 24 kHz mono WAV, trimmed to the reference length F5-TTS expects."""
    if not shutil.which("ffmpeg"):
        raise HTTPException(500, "ffmpeg is not installed")
    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-i", str(src), "-t", str(MAX_VOICE_SECONDS),
           "-ac", "1", "-ar", "24000", str(dst)]
    if subprocess.run(cmd).returncode != 0:
        raise HTTPException(400, "Could not read that audio file.")
    seconds = _duration(dst)
    if seconds < MIN_VOICE_SECONDS:
        dst.unlink(missing_ok=True)
        raise HTTPException(400, f"Voice sample must be at least {MIN_VOICE_SECONDS} seconds long.")
    return round(seconds, 1)


def _duration(path: Path) -> float:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
        capture_output=True, text=True,
    )
    try:
        return float(out.stdout.strip())
    except ValueError:
        return 0.0


# ---- videos ------------------------------------------------------------------

class VideoRequest(BaseModel):
    script: str = Field(..., min_length=1)
    voice: str = Field("custom", pattern="^(custom|default)$")


def _video_public(v: dict) -> dict:
    out = {k: v[k] for k in ("id", "script", "voice", "status", "error", "created_at", "updated_at")}
    out["video_url"] = f"/api/videos/{v['id']}/file" if v["status"] == "completed" else None
    return out


@app.get("/api/videos")
def list_videos():
    return [_video_public(v) for v in store.list_videos()]


@app.get("/api/videos/{video_id}")
def get_video(video_id: str):
    v = store.get_video(video_id)
    if not v:
        raise HTTPException(404, "Video not found")
    return _video_public(v)


@app.get("/api/videos/{video_id}/file")
def get_video_file(video_id: str, download: bool = False):
    v = store.get_video(video_id)
    path = store.video_path(video_id)
    if not v or v["status"] != "completed" or not path.exists():
        raise HTTPException(404, "Video not ready")
    headers = {"Content-Disposition": f'attachment; filename="avatar-{video_id[:8]}.mp4"'} if download else {}
    return FileResponse(path, media_type="video/mp4", headers=headers)


@app.post("/api/videos", status_code=202)
async def create_video(req: VideoRequest):
    script = req.script.strip()
    if not script:
        raise HTTPException(400, "Write something for the avatar to say")
    if len(script) > MAX_SCRIPT_CHARS:
        raise HTTPException(400, f"Script must be {MAX_SCRIPT_CHARS} characters or fewer for now")

    avatar = store.get_avatar()
    if not avatar:
        raise HTTPException(409, "Set up your avatar first")
    if req.voice == "custom" and not avatar["has_custom_voice"]:
        raise HTTPException(409, "No custom voice saved. Use the default voice or add a voice sample.")
    if not runpod_client.is_configured():
        raise HTTPException(503, "RunPod is not configured. Add RUNPOD_API_KEY and RUNPOD_ENDPOINT_ID to server/.env")

    payload = {
        "script": script,
        "voice": req.voice,
        "image_b64": _b64(store.AVATAR_DIR / "image.jpg"),
    }
    if req.voice == "custom":
        payload["voice_b64"] = _b64(store.AVATAR_DIR / "voice.wav")
        transcript_path = store.AVATAR_DIR / "voice_transcript.txt"
        payload["voice_transcript"] = transcript_path.read_text(encoding="utf-8") if transcript_path.exists() else ""

    try:
        job_id = await runpod_client.submit(payload)
    except runpod_client.RunPodError as e:
        raise HTTPException(502, str(e))

    video_id = uuid.uuid4().hex
    record = {
        "id": video_id,
        "script": script,
        "voice": req.voice,
        "status": "queued",
        "error": None,
        "runpod_job_id": job_id,
        "created_at": now(),
        "updated_at": now(),
    }
    store.upsert_video(record)
    _start_poller(video_id)
    return _video_public(record)


def _b64(path: Path) -> str:
    return base64.b64encode(path.read_bytes()).decode("ascii")


# ---- job poller --------------------------------------------------------------

def _start_poller(video_id: str) -> None:
    if video_id in _tasks and not _tasks[video_id].done():
        return
    _tasks[video_id] = asyncio.create_task(_poll(video_id))


async def _poll(video_id: str) -> None:
    """Watch one RunPod job until it finishes. Survives transient network errors."""
    while True:
        record = store.get_video(video_id)
        if not record or record["status"] in ("completed", "failed"):
            return
        try:
            st = await runpod_client.status(record["runpod_job_id"])
        except Exception as e:  # network blip or RunPod hiccup: try again
            log.warning("status check failed for %s: %s", video_id, e)
            await asyncio.sleep(POLL_SECONDS)
            continue

        state = st.get("status")
        if state == "IN_QUEUE":
            _update(record, status="queued")
        elif state == "IN_PROGRESS":
            _update(record, status="running")
        elif state == "COMPLETED":
            _finish(record, st.get("output") or {})
            return
        elif state in ("FAILED", "CANCELLED", "TIMED_OUT"):
            err = st.get("error") or _error_text(st.get("output")) or f"RunPod job {state.lower()}"
            _update(record, status="failed", error=str(err)[:1000])
            return
        await asyncio.sleep(POLL_SECONDS)


def _error_text(output) -> str | None:
    if isinstance(output, dict):
        return output.get("error")
    if isinstance(output, str):
        return output
    return None


def _update(record: dict, **fields) -> None:
    if all(record.get(k) == v for k, v in fields.items()):
        return
    record.update(fields)
    record["updated_at"] = now()
    store.upsert_video(record)


def _finish(record: dict, output: dict) -> None:
    if output.get("error") or not output.get("video_b64"):
        _update(record, status="failed", error=str(output.get("error") or "Worker returned no video")[:1000])
        return
    store.ensure_dirs()
    store.video_path(record["id"]).write_bytes(base64.b64decode(output["video_b64"]))
    _update(record, status="completed", error=None)
