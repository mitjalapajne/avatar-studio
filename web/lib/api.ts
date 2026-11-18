export const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export type Avatar = {
  name: string;
  created_at: string;
  image_url: string;
  has_custom_voice: boolean;
  voice_seconds: number | null;
};

export type VideoStatus = "queued" | "running" | "completed" | "failed";
export type VoiceChoice = "custom" | "default";

export type Video = {
  id: string;
  script: string;
  voice: VoiceChoice;
  status: VideoStatus;
  error: string | null;
  created_at: string;
  updated_at: string;
  video_url: string | null;
};

export type SystemStatus = { runpod_configured: boolean; ffmpeg: boolean };

export const isPending = (s: VideoStatus) => s === "queued" || s === "running";

export function assetUrl(path: string) {
  return `${API}${path}`;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API}${path}`, init);
  if (!res.ok) {
    let message = `Request failed (${res.status})`;
    try {
      const body = await res.json();
      if (typeof body.detail === "string") message = body.detail;
      else if (Array.isArray(body.detail) && body.detail[0]?.msg) message = body.detail[0].msg;
    } catch {
      /* non-JSON error body */
    }
    throw new Error(message);
  }
  return res.json() as Promise<T>;
}

export const api = {
  status: () => request<SystemStatus>("/api/status"),
  getAvatar: () => request<Avatar | null>("/api/avatar"),
  saveAvatar: (form: FormData) =>
    request<Avatar>("/api/avatar", { method: "POST", body: form }),
  listVideos: () => request<Video[]>("/api/videos"),
  createVideo: (script: string, voice: VoiceChoice) =>
    request<Video>("/api/videos", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ script, voice }),
    }),
};
