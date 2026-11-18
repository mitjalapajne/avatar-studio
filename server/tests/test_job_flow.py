"""Lifecycle test with RunPod stubbed out: queue -> running -> completed (MP4 saved and served),
plus a failure path and restart recovery. This tests Avatar Studio's own plumbing only;
it does not exercise the GPU worker."""

import base64
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

os.environ["AVATAR_DATA_DIR"] = tempfile.mkdtemp()
os.environ["RUNPOD_API_KEY"] = "test"
os.environ["RUNPOD_ENDPOINT_ID"] = "test"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient  # noqa: E402
import main  # noqa: E402
import runpod_client  # noqa: E402
import store  # noqa: E402

main.POLL_SECONDS = 0.05
calls = {"submitted": [], "states": []}


async def fake_submit(payload):
    calls["submitted"].append(payload)
    return "rp-job-1"


async def fake_status(job_id):
    return calls["states"].pop(0)


runpod_client.submit = fake_submit
runpod_client.status = fake_status

def make_mp4(path: Path):
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", "testsrc=s=320x240:d=1",
                    "-f", "lavfi", "-i", "sine=d=1", "-shortest", "-pix_fmt", "yuv420p", str(path)], check=True)
    return path

def wait_for(client, vid, states, timeout=5):
    end = time.time() + timeout
    while time.time() < end:
        v = client.get(f"/api/videos/{vid}").json()
        if v["status"] in states:
            return v
        time.sleep(0.05)
    raise AssertionError(f"timed out, last={v}")

client = TestClient(main.app)
png = Path(tempfile.mkdtemp()) / "a.png"
subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", "color=c=gray:s=320x240", "-frames:v", "1", str(png)], check=True)
wav = Path(tempfile.mkdtemp()) / "v.wav"
subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", "sine=d=5", "-ar", "24000", str(wav)], check=True)

with TestClient(main.app) as c:
    # avatar with custom voice
    r = c.post("/api/avatar", data={"name": "Me", "voice_mode": "custom", "voice_transcript": "hello"},
               files={"image": ("a.png", png.read_bytes(), "image/png"), "voice": ("v.wav", wav.read_bytes(), "audio/wav")})
    assert r.status_code == 200 and r.json()["has_custom_voice"] is True, r.text

    # re-save name only: custom voice must be kept
    r = c.post("/api/avatar", data={"name": "Me 2", "voice_mode": "custom"})
    assert r.status_code == 200 and r.json()["has_custom_voice"] is True and r.json()["name"] == "Me 2", r.text

    # switching to default clears custom voice
    r = c.post("/api/avatar", data={"name": "Me 2", "voice_mode": "default"})
    assert r.json()["has_custom_voice"] is False, r.text
    r = c.post("/api/avatar", data={"name": "Me", "voice_mode": "custom", "voice_transcript": "hello"},
               files={"voice": ("v.wav", wav.read_bytes(), "audio/wav")})
    assert r.json()["has_custom_voice"] is True

    # validation
    assert c.post("/api/videos", json={"script": "   "}).status_code == 400
    assert c.post("/api/videos", json={"script": "x" * 601}).status_code == 400

    # happy path
    mp4 = make_mp4(Path(tempfile.mkdtemp()) / "out.mp4")
    calls["states"] = [
        {"status": "IN_QUEUE"},
        {"status": "IN_PROGRESS"},
        {"status": "COMPLETED", "output": {"video_b64": base64.b64encode(mp4.read_bytes()).decode()}},
    ]
    r = c.post("/api/videos", json={"script": "Hello world", "voice": "custom"})
    assert r.status_code == 202, r.text
    vid = r.json()["id"]
    sent = calls["submitted"][-1]
    assert sent["voice"] == "custom" and sent["voice_b64"] and sent["image_b64"] and sent["voice_transcript"] == "hello"

    done = wait_for(c, vid, {"completed", "failed"})
    assert done["status"] == "completed", done
    assert done["video_url"] == f"/api/videos/{vid}/file"
    f = c.get(done["video_url"])
    assert f.status_code == 200 and f.headers["content-type"] == "video/mp4" and len(f.content) > 1000
    assert c.get(done["video_url"], params={"download": 1}).headers["content-disposition"].startswith("attachment")
    print("ok: completed job saved and served MP4")

    # failure path: worker raises -> RunPod FAILED with error
    calls["states"] = [{"status": "IN_PROGRESS"}, {"status": "FAILED", "error": "CUDA out of memory"}]
    vid2 = c.post("/api/videos", json={"script": "Second", "voice": "default"}).json()["id"]
    failed = wait_for(c, vid2, {"completed", "failed"})
    assert failed["status"] == "failed" and "out of memory" in failed["error"], failed
    assert failed["video_url"] is None
    assert c.get(f"/api/videos/{vid2}/file").status_code == 404
    print("ok: failed job reports the RunPod error")

    # network blip then success
    class Blip(Exception):
        pass
    seq = [Blip("connection reset"), {"status": "IN_PROGRESS"}, {"status": "COMPLETED", "output": {"error": "bad audio"}}]
    async def flaky(job_id):
        item = seq.pop(0)
        if isinstance(item, Exception):
            raise item
        return item
    runpod_client.status = flaky
    vid3 = c.post("/api/videos", json={"script": "Third", "voice": "default"}).json()["id"]
    v3 = wait_for(c, vid3, {"completed", "failed"})
    assert v3["status"] == "failed" and "bad audio" in v3["error"], v3
    print("ok: transient status error is retried; worker error surfaces")

    # restart recovery: a job left 'queued' on disk is picked up and completed
    store.upsert_video({"id": "resume1", "script": "resume", "voice": "default", "status": "queued", "error": None,
                        "runpod_job_id": "rp-old", "created_at": "2026-01-01T00:00:00+00:00", "updated_at": "2026-01-01T00:00:00+00:00"})
    runpod_client.status = fake_status
    calls["states"] = [{"status": "COMPLETED", "output": {"video_b64": base64.b64encode(mp4.read_bytes()).decode()}}]
    with TestClient(main.app) as c2:
        res = wait_for(c2, "resume1", {"completed", "failed"})
        assert res["status"] == "completed", res
    print("ok: unfinished job resumes after restart")

print("ALL PASSED")
