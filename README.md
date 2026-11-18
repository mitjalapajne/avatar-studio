# Avatar Studio

A personal tool: save one photo of yourself, type a script, get an MP4 of yourself saying it.

```
server/   FastAPI API: avatar, job queue, RunPod polling, MP4 storage (local JSON + files)
web/      Next.js + Tailwind UI
worker/   RunPod serverless GPU worker: F5-TTS → InfiniteTalk → FFmpeg
data/     created at runtime: avatar photo/voice, generated videos, JSON indexes
```

## 1. Run locally

Requirements: Node 20+, pnpm, Python 3.10+, FFmpeg (`brew install ffmpeg`).

```bash
# API
cd server
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # then fill in RUNPOD_API_KEY and RUNPOD_ENDPOINT_ID
uvicorn main:app --port 8000

# UI (new terminal)
cd web
pnpm install
pnpm dev                      # http://localhost:3000
```

Without RunPod credentials the app still works for avatar setup; generation shows a clear
"GPU not connected" message instead of pretending to run.

Tests (stubs RunPod; verifies the job lifecycle, MP4 storage, failure handling and restart recovery):

```bash
cd server && .venv/bin/python tests/test_job_flow.py
```

## 2. Deploy the GPU worker on RunPod

1. **Build and push the image** (needs Docker and a Docker Hub account):
   ```bash
   cd worker
   docker build -t <dockerhub-user>/avatar-studio-worker:latest .
   docker push <dockerhub-user>/avatar-studio-worker:latest
   ```
2. **Create a network volume** in RunPod, about **100 GB**, in a region where your GPU is available.
   The first job downloads ~50 GB of model weights into `/runpod-volume/weights`. Later cold starts reuse them.
3. **Create a serverless endpoint** using that image:
   - GPU: one 80 GB class card (A100 80GB or H100). InfiniteTalk at 480p is large; a 24 GB card will not fit the 14B model without offloading.
   - Network volume: mount the volume you created (mounts at `/runpod-volume`).
   - Max workers: 1 is enough for personal use. Set an idle timeout so you aren't billed while idle.
4. Copy the **endpoint ID** and create an **API key** (Settings → API Keys), then put them in `server/.env`.
5. Restart `uvicorn`. `GET /api/status` should report `"runpod_configured": true`.

## 3. How a video is made

1. `POST /api/videos` stores the job and submits it to RunPod with the avatar photo, your voice clip and the script.
2. A background poller checks RunPod status every 5 seconds and writes it to `data/videos.json`.
   If the API restarts mid-job, unfinished jobs are picked up again.
3. The worker:
   - **F5-TTS** synthesises the script in your cloned voice (or the bundled default voice).
   - **InfiniteTalk** (image-to-video, `infinitetalk-480`, streaming mode) animates the photo to the speech.
   - **FFmpeg** muxes video and speech into an H.264/AAC MP4.
4. The finished MP4 is saved to `data/videos/<id>.mp4` and served in the preview, with a Download button.

## Known limits (MVP)

- Scripts are capped at 600 characters (about 30 seconds of speech).
- Output is returned to the API as base64 inside the RunPod response. This is fine for 30-second 480p clips, but RunPod's payload limits should be checked for larger outputs. Moving outputs to object storage would be the fix.
- 720p is supported in the worker via the `VIDEO_SIZE=infinitetalk-720` env var, but is not exposed in the UI.
- F5-TTS v1 Base is trained mainly on English and Chinese. Non-English scripts (for example Slovenian) will not clone your voice well. See the note in the final summary.
