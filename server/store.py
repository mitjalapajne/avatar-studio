"""Tiny JSON-file persistence for the single avatar and generated videos."""

from __future__ import annotations

import json
import os
import threading
from pathlib import Path
from typing import Any

ROOT = Path(os.environ.get("AVATAR_DATA_DIR", Path(__file__).resolve().parent.parent / "data"))
AVATAR_DIR = ROOT / "avatar"
VIDEO_DIR = ROOT / "videos"
VIDEO_INDEX = ROOT / "videos.json"
AVATAR_INDEX = AVATAR_DIR / "avatar.json"

_lock = threading.RLock()


def ensure_dirs() -> None:
    AVATAR_DIR.mkdir(parents=True, exist_ok=True)
    VIDEO_DIR.mkdir(parents=True, exist_ok=True)


def _read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _write_json(path: Path, data: Any) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    os.replace(tmp, path)  # atomic on POSIX


# ---- avatar -----------------------------------------------------------------

def get_avatar() -> dict | None:
    with _lock:
        return _read_json(AVATAR_INDEX, None)


def save_avatar(record: dict) -> None:
    with _lock:
        ensure_dirs()
        _write_json(AVATAR_INDEX, record)


# ---- videos -----------------------------------------------------------------

def list_videos() -> list[dict]:
    with _lock:
        return _read_json(VIDEO_INDEX, [])


def get_video(video_id: str) -> dict | None:
    return next((v for v in list_videos() if v["id"] == video_id), None)


def upsert_video(record: dict) -> None:
    with _lock:
        ensure_dirs()
        videos = list_videos()
        for i, v in enumerate(videos):
            if v["id"] == record["id"]:
                videos[i] = record
                break
        else:
            videos.insert(0, record)
        _write_json(VIDEO_INDEX, videos)


def video_path(video_id: str) -> Path:
    return VIDEO_DIR / f"{video_id}.mp4"
