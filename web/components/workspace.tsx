"use client";

import { useEffect, useMemo, useState } from "react";
import { api, assetUrl, Avatar, isPending, SystemStatus, Video, VoiceChoice } from "@/lib/api";
import { Button, Label, Segmented, Textarea } from "./ui";

const MAX_CHARS = 600;

export function Workspace({
  avatar,
  system,
  onEditAvatar,
}: {
  avatar: Avatar;
  system: SystemStatus | null;
  onEditAvatar: () => void;
}) {
  const [script, setScript] = useState("");
  const [voice, setVoice] = useState<VoiceChoice>(avatar.has_custom_voice ? "custom" : "default");
  const [videos, setVideos] = useState<Video[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [now, setNow] = useState(() => Date.now());

  // Initial load, then poll only while a job is pending. Every update happens after a
  // network await or inside an interval, never synchronously inside the effect body.
  const anyPending = videos.some((v) => isPending(v.status));
  useEffect(() => {
    let cancelled = false;
    const load = () => api.listVideos().then((v) => !cancelled && setVideos(v)).catch(() => {});
    load();
    const poll = setInterval(() => {
      if (anyPending) load();
    }, 3000);
    const tick = setInterval(() => setNow(Date.now()), 1000);
    return () => {
      cancelled = true;
      clearInterval(poll);
      clearInterval(tick);
    };
  }, [anyPending]);

  const selected = useMemo(
    () => videos.find((v) => v.id === selectedId) ?? videos[0] ?? null,
    [videos, selectedId],
  );

  const gpuReady = system?.runpod_configured ?? true;
  const canGenerate = script.trim().length > 0 && !submitting && gpuReady && script.length <= MAX_CHARS;

  async function generate() {
    if (!canGenerate) return;
    setSubmitting(true);
    setSubmitError(null);
    try {
      const video = await api.createVideo(script.trim(), voice);
      setVideos((prev) => [video, ...prev.filter((v) => v.id !== video.id)]);
      setSelectedId(video.id);
    } catch (err) {
      setSubmitError(err instanceof Error ? err.message : "Could not start generation");
    } finally {
      setSubmitting(false);
    }
  }

  function onKeyDown(e: React.KeyboardEvent) {
    if ((e.metaKey || e.ctrlKey) && e.key === "Enter") generate();
  }

  return (
    <div className="grid gap-10 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.15fr)]">
      {/* Left: compose */}
      <section className="flex min-w-0 flex-col">
        <div className="mb-8 flex items-center gap-4">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img
            src={assetUrl(avatar.image_url) + `?v=${encodeURIComponent(avatar.created_at)}`}
            alt=""
            className="h-11 w-11 rounded-full object-cover shadow-[0_0_0_1px_rgba(0,0,0,0.06)]"
          />
          <div className="min-w-0">
            <p className="truncate text-[15px] font-medium text-neutral-950">{avatar.name}</p>
            <button onClick={onEditAvatar} className="text-[13px] text-neutral-500 transition-colors hover:text-neutral-900">
              Edit avatar
            </button>
          </div>
        </div>

        <Label hint={`${script.length} / ${MAX_CHARS}`}>Script</Label>
        <Textarea
          value={script}
          onChange={(e) => setScript(e.target.value)}
          onKeyDown={onKeyDown}
          placeholder="What should your avatar say?"
          maxLength={MAX_CHARS + 200}
          className="min-h-[300px] flex-1 text-[16px] leading-[1.7] lg:min-h-[360px]"
        />

        <div className="mt-6 flex items-end justify-between gap-4">
          <div>
            <Label>Voice</Label>
            <Segmented<VoiceChoice>
              value={voice}
              onChange={setVoice}
              options={[
                { value: "custom", label: "My voice", disabled: !avatar.has_custom_voice },
                { value: "default", label: "Default" },
              ]}
            />
          </div>
          <Button onClick={generate} disabled={!canGenerate} className="h-10 px-6">
            {submitting ? "Starting…" : "Generate video"}
            {!submitting && <kbd className="ml-1 hidden rounded bg-white/15 px-1.5 py-0.5 font-sans text-[11px] text-white/80 sm:inline">⌘↵</kbd>}
          </Button>
        </div>

        {!gpuReady && (
          <p className="mt-4 text-[13px] leading-relaxed text-neutral-500">
            GPU not connected. Add <code className="rounded bg-neutral-100 px-1 py-0.5 text-[12px]">RUNPOD_API_KEY</code> and{" "}
            <code className="rounded bg-neutral-100 px-1 py-0.5 text-[12px]">RUNPOD_ENDPOINT_ID</code> to <code className="rounded bg-neutral-100 px-1 py-0.5 text-[12px]">server/.env</code>.
          </p>
        )}
        {submitError && <p className="mt-4 text-[13px] text-red-600">{submitError}</p>}
      </section>

      {/* Right: preview */}
      <section className="flex min-w-0 flex-col">
        <Preview video={selected} now={now} onRetry={() => setScript(selected?.script ?? "")} />

        {videos.length > 0 && (
          <div className="mt-8">
            <p className="mb-2 text-[13px] font-medium text-neutral-900">Recent</p>
            <ul className="divide-y divide-neutral-100 overflow-hidden rounded-xl border border-neutral-200">
              {videos.slice(0, 12).map((v) => (
                <li key={v.id}>
                  <button
                    onClick={() => setSelectedId(v.id)}
                    className={
                      "flex w-full items-center gap-4 px-4 py-3 text-left transition-colors " +
                      (selected?.id === v.id ? "bg-neutral-50" : "hover:bg-neutral-50/60")
                    }
                  >
                    <StatusDot status={v.status} />
                    <span className="min-w-0 flex-1 truncate text-[14px] text-neutral-900">{v.script}</span>
                    <span className="shrink-0 text-[12px] text-neutral-400">{relative(v.created_at)}</span>
                  </button>
                </li>
              ))}
            </ul>
          </div>
        )}
      </section>
    </div>
  );
}

function Preview({ video, now, onRetry }: { video: Video | null; now: number; onRetry: () => void }) {
  const frame =
    "relative flex aspect-video w-full items-center justify-center overflow-hidden rounded-2xl border border-neutral-200 bg-neutral-50";

  if (!video) {
    return (
      <div className={frame}>
        <p className="px-8 text-center text-[14px] text-neutral-400">Your video will appear here.</p>
      </div>
    );
  }

  if (video.status === "completed" && video.video_url) {
    const src = assetUrl(video.video_url);
    return (
      <div className="animate-[fade-up_400ms_cubic-bezier(0.2,0.8,0.2,1)]">
        <div className="overflow-hidden rounded-2xl border border-neutral-200 bg-black">
          <video key={src} src={src} controls playsInline className="aspect-video w-full" />
        </div>
        <div className="mt-4 flex items-center justify-between gap-4">
          <p className="min-w-0 truncate text-[14px] text-neutral-500">{video.script}</p>
          <a
            href={`${src}?download=1`}
            className="inline-flex h-9 shrink-0 items-center rounded-lg bg-neutral-900 px-4 text-[13px] font-medium text-white transition-colors hover:bg-neutral-800"
          >
            Download MP4
          </a>
        </div>
      </div>
    );
  }

  if (video.status === "failed") {
    return (
      <div className={frame + " px-8"}>
        <div className="max-w-sm text-center">
          <p className="text-[15px] font-medium text-neutral-900">Generation failed</p>
          <p className="mt-2 break-words text-[13px] leading-relaxed text-neutral-500">{video.error}</p>
          <Button variant="secondary" className="mt-6" onClick={onRetry}>
            Edit script and try again
          </Button>
        </div>
      </div>
    );
  }

  // queued / running: real RunPod status only, no invented percentages
  const elapsed = Math.max(0, Math.floor((now - new Date(video.created_at).getTime()) / 1000));
  const label = video.status === "queued" ? "Waiting for a GPU" : "Generating speech and video";
  return (
    <div className={frame}>
      <div className="w-full max-w-xs px-8 text-center">
        <div className="relative mx-auto mb-6 h-px w-full overflow-hidden bg-neutral-200">
          <div className="absolute inset-y-0 w-1/3 bg-neutral-900 animate-[sweep_1.6s_ease-in-out_infinite]" />
        </div>
        <p className="text-[15px] font-medium text-neutral-900">{label}</p>
        <p className="mt-2 font-mono text-[13px] tabular-nums text-neutral-400">{formatElapsed(elapsed)}</p>
        <p className="mt-6 text-[12px] leading-relaxed text-neutral-400">
          This usually takes a few minutes. You can keep writing other scripts while it runs.
        </p>
      </div>
    </div>
  );
}

function StatusDot({ status }: { status: Video["status"] }) {
  const color =
    status === "completed" ? "bg-neutral-900" : status === "failed" ? "bg-red-500" : "bg-neutral-300 animate-pulse";
  return <span className={`h-2 w-2 shrink-0 rounded-full ${color}`} aria-label={status} />;
}

function formatElapsed(total: number) {
  const m = Math.floor(total / 60);
  const s = total % 60;
  return `${m}:${s.toString().padStart(2, "0")}`;
}

function relative(iso: string) {
  const diff = Date.now() - new Date(iso).getTime();
  const min = Math.round(diff / 60000);
  if (min < 1) return "just now";
  if (min < 60) return `${min}m ago`;
  const h = Math.round(min / 60);
  if (h < 24) return `${h}h ago`;
  return new Date(iso).toLocaleDateString(undefined, { month: "short", day: "numeric" });
}
