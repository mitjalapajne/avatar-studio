"""RunPod serverless worker: script + avatar image (+ voice) -> talking-head MP4.

Pipeline
  1. F5-TTS      script text (+ your voice sample) -> speech WAV
  2. InfiniteTalk avatar image + speech WAV          -> lip-synced video (no audio track guaranteed)
  3. FFmpeg      video + speech WAV                  -> H.264/AAC MP4

Model weights are downloaded once to the RunPod network volume (WEIGHTS_DIR) and reused
on every cold start.

Input  (job["input"]):
  script            str   text to speak (required)
  voice             str   "custom" | "default"
  voice_b64         str   base64 WAV of your voice (required when voice == "custom")
  voice_transcript  str   what is said in voice_b64 (optional; empty = auto-transcribe)
  image_b64         str   base64 JPG/PNG of the avatar (required)

Output: {"video_b64": "<base64 mp4>"}  or the job fails with an error message.
"""

from __future__ import annotations

import base64
import json
import os
import subprocess
import tempfile
import threading
from importlib.resources import files
from pathlib import Path

import runpod

WEIGHTS = Path(os.environ.get("WEIGHTS_DIR", "/runpod-volume/weights"))
WAN_DIR = WEIGHTS / "Wan2.1-I2V-14B-480P"
W2V_DIR = WEIGHTS / "chinese-wav2vec2-base"
IT_DIR = WEIGHTS / "InfiniteTalk"
INFINITETALK_REPO = Path(os.environ.get("INFINITETALK_REPO", "/app/InfiniteTalk"))
SIZE = os.environ.get("VIDEO_SIZE", "infinitetalk-480")  # or infinitetalk-720
SAMPLE_STEPS = int(os.environ.get("SAMPLE_STEPS", "40"))

_weights_lock = threading.Lock()
_weights_ready = False
_tts = None


# ---- one-time weight setup ---------------------------------------------------

def ensure_weights() -> None:
    global _weights_ready
    with _weights_lock:
        if _weights_ready:
            return
        from huggingface_hub import hf_hub_download, snapshot_download

        WEIGHTS.mkdir(parents=True, exist_ok=True)
        marker = WEIGHTS / ".complete"
        if not marker.exists():
            snapshot_download("Wan-AI/Wan2.1-I2V-14B-480P", local_dir=str(WAN_DIR))
            snapshot_download("TencentGameMate/chinese-wav2vec2-base", local_dir=str(W2V_DIR))
            hf_hub_download("TencentGameMate/chinese-wav2vec2-base", "model.safetensors",
                            revision="refs/pr/1", local_dir=str(W2V_DIR))
            snapshot_download("MeiGen-AI/InfiniteTalk", local_dir=str(IT_DIR))
            marker.write_text("ok")
        _weights_ready = True


# ---- stage 1: speech ---------------------------------------------------------

def get_tts():
    global _tts
    if _tts is None:
        from f5_tts.api import F5TTS
        _tts = F5TTS(model="F5TTS_v1_Base")
    return _tts


def synthesize(script: str, ref_wav: Path, ref_text: str, out_wav: Path) -> None:
    get_tts().infer(
        ref_file=str(ref_wav),
        ref_text=ref_text,  # "" makes F5-TTS transcribe the reference itself
        gen_text=script,
        file_wave=str(out_wav),
        seed=-1,
    )


def default_reference(tmp: Path) -> Path:
    """The sample voice bundled with F5-TTS, used when no custom voice is saved."""
    src = files("f5_tts").joinpath("infer/examples/basic/basic_ref_en.wav")
    dst = tmp / "default_ref.wav"
    dst.write_bytes(src.read_bytes())
    return dst


# ---- stage 2: talking head ---------------------------------------------------

def animate(image: Path, speech: Path, workdir: Path) -> Path:
    spec = {
        "prompt": "A person is speaking naturally to the camera, with natural head movement and expressions.",
        "cond_video": str(image),
        "cond_audio": {"person1": str(speech)},
    }
    spec_path = workdir / "input.json"
    spec_path.write_text(json.dumps(spec))
    stem = workdir / "talk"
    cmd = [
        "python", "generate_infinitetalk.py",
        "--ckpt_dir", str(WAN_DIR),
        "--wav2vec_dir", str(W2V_DIR),
        "--infinitetalk_dir", str(IT_DIR / "single" / "infinitetalk.safetensors"),
        "--input_json", str(spec_path),
        "--size", SIZE,
        "--sample_steps", str(SAMPLE_STEPS),
        "--mode", "streaming",
        "--motion_frame", "9",
        "--save_file", str(stem),
    ]
    proc = subprocess.run(cmd, cwd=INFINITETALK_REPO, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"InfiniteTalk failed: {proc.stderr[-1500:]}")
    produced = sorted(workdir.glob("talk*.mp4"))
    if not produced:
        raise RuntimeError("InfiniteTalk finished but produced no MP4")
    return produced[-1]


# ---- stage 3: mux -------------------------------------------------------------

def mux(video: Path, speech: Path, out: Path) -> None:
    cmd = [
        "ffmpeg", "-y", "-loglevel", "error",
        "-i", str(video), "-i", str(speech),
        "-map", "0:v:0", "-map", "1:a:0",
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-preset", "medium", "-crf", "18",
        "-c:a", "aac", "-b:a", "192k",
        "-shortest", "-movflags", "+faststart",
        str(out),
    ]
    if subprocess.run(cmd).returncode != 0:
        raise RuntimeError("FFmpeg failed to mux the final video")


# ---- handler -----------------------------------------------------------------

def _decode(b64: str, path: Path) -> Path:
    path.write_bytes(base64.b64decode(b64))
    return path


def handler(job: dict) -> dict:
    inp = job.get("input") or {}
    script = (inp.get("script") or "").strip()
    if not script:
        raise ValueError("script is required")
    if not inp.get("image_b64"):
        raise ValueError("image_b64 is required")
    voice = inp.get("voice", "custom")

    ensure_weights()

    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        image = _decode(inp["image_b64"], tmp / "avatar.jpg")

        if voice == "custom":
            if not inp.get("voice_b64"):
                raise ValueError("voice_b64 is required for a custom voice")
            ref = _decode(inp["voice_b64"], tmp / "voice.wav")
        else:
            ref = default_reference(tmp)

        speech = tmp / "speech.wav"
        synthesize(script, ref, inp.get("voice_transcript", "") or "", speech)

        talking = animate(image, speech, tmp)
        final = tmp / "final.mp4"
        mux(talking, speech, final)

        return {"video_b64": base64.b64encode(final.read_bytes()).decode("ascii")}


if __name__ == "__main__":
    runpod.serverless.start({"handler": handler})
