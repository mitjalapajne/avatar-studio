"""Minimal RunPod serverless client: submit a job, read its status."""

from __future__ import annotations

import os

import httpx

API_BASE = "https://api.runpod.ai/v2"


class RunPodError(RuntimeError):
    pass


def config() -> tuple[str, str]:
    key = os.environ.get("RUNPOD_API_KEY", "").strip()
    endpoint = os.environ.get("RUNPOD_ENDPOINT_ID", "").strip()
    if not key or not endpoint:
        raise RunPodError(
            "RunPod is not configured. Set RUNPOD_API_KEY and RUNPOD_ENDPOINT_ID in server/.env"
        )
    return key, endpoint


def is_configured() -> bool:
    try:
        config()
        return True
    except RunPodError:
        return False


async def submit(payload: dict) -> str:
    key, endpoint = config()
    async with httpx.AsyncClient(timeout=60) as client:
        r = await client.post(
            f"{API_BASE}/{endpoint}/run",
            json={"input": payload},
            headers={"Authorization": f"Bearer {key}"},
        )
    if r.status_code >= 400:
        raise RunPodError(f"RunPod rejected the job ({r.status_code}): {r.text[:300]}")
    return r.json()["id"]


async def status(job_id: str) -> dict:
    key, endpoint = config()
    async with httpx.AsyncClient(timeout=60) as client:
        r = await client.get(
            f"{API_BASE}/{endpoint}/status/{job_id}",
            headers={"Authorization": f"Bearer {key}"},
        )
    if r.status_code >= 400:
        raise RunPodError(f"RunPod status error ({r.status_code}): {r.text[:300]}")
    return r.json()
