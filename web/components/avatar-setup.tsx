"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { api, Avatar, assetUrl } from "@/lib/api";
import { Button, Input, Label, Segmented, Textarea } from "./ui";

type VoiceMode = "default" | "custom";

export function AvatarSetup({
  existing,
  onSaved,
  onCancel,
}: {
  existing: Avatar | null;
  onSaved: (a: Avatar) => void;
  onCancel?: () => void;
}) {
  const [name, setName] = useState(existing?.name ?? "");
  const [photo, setPhoto] = useState<File | null>(null);
  const [voiceMode, setVoiceMode] = useState<VoiceMode>(existing?.has_custom_voice ? "custom" : "default");
  const [voice, setVoice] = useState<File | null>(null);
  const [transcript, setTranscript] = useState("");
  const [dragging, setDragging] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);
  const voiceRef = useRef<HTMLInputElement>(null);

  const preview = useMemo(() => (photo ? URL.createObjectURL(photo) : null), [photo]);
  useEffect(() => () => {
    if (preview) URL.revokeObjectURL(preview);
  }, [preview]);

  const existingPhoto = existing ? assetUrl(existing.image_url) : null;
  const canSave = name.trim().length > 0 && (photo !== null || existing !== null) && (voiceMode === "default" || voice !== null || existing?.has_custom_voice);

  function pickPhoto(file: File | undefined) {
    if (file && file.type.startsWith("image/")) setPhoto(file);
  }

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!canSave || saving) return;
    setSaving(true);
    setError(null);
    try {
      const form = new FormData();
      form.append("name", name.trim());
      if (photo) form.append("image", photo);
      else if (existingPhoto) {
        // Re-use the saved photo when only the name or voice changes.
        const blob = await fetch(existingPhoto).then((r) => r.blob());
        form.append("image", new File([blob], "avatar.jpg", { type: "image/jpeg" }));
      }
      form.append("voice_mode", voiceMode);
      if (voiceMode === "custom" && voice) {
        form.append("voice", voice);
        form.append("voice_transcript", transcript);
      }
      const saved = await api.saveAvatar(form);
      onSaved(saved);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong");
    } finally {
      setSaving(false);
    }
  }

  const shownPhoto = preview ?? existingPhoto;

  return (
    <div className="mx-auto w-full max-w-[560px] animate-[fade-up_420ms_cubic-bezier(0.2,0.8,0.2,1)]">
      <div className="mb-10">
        <h1 className="text-[28px] font-semibold tracking-[-0.02em] text-neutral-950">
          {existing ? "Edit your avatar" : "Create your avatar"}
        </h1>
        <p className="mt-2 text-[15px] leading-relaxed text-neutral-500">
          One photo of you, facing the camera, in good light. Your avatar is saved and reused for every video.
        </p>
      </div>

      <form onSubmit={submit} className="space-y-8">
        <div>
          <Label>Photo</Label>
          <div
            role="button"
            tabIndex={0}
            onClick={() => fileRef.current?.click()}
            onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && fileRef.current?.click()}
            onDragOver={(e) => {
              e.preventDefault();
              setDragging(true);
            }}
            onDragLeave={() => setDragging(false)}
            onDrop={(e) => {
              e.preventDefault();
              setDragging(false);
              pickPhoto(e.dataTransfer.files[0]);
            }}
            className={
              "group relative flex aspect-[5/3] w-full cursor-pointer items-center justify-center overflow-hidden rounded-2xl border transition-colors duration-200 " +
              (dragging ? "border-neutral-900 bg-neutral-50" : "border-neutral-200 bg-neutral-50/60 hover:border-neutral-300")
            }
          >
            {shownPhoto ? (
              // eslint-disable-next-line @next/next/no-img-element
              <img src={shownPhoto} alt="Your avatar photo" className="h-full w-full object-cover" />
            ) : (
              <div className="text-center">
                <div className="mx-auto mb-3 flex h-10 w-10 items-center justify-center rounded-full bg-white shadow-[0_0_0_1px_rgba(0,0,0,0.06)]">
                  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" className="text-neutral-500">
                    <path d="M12 16V4m0 0-4 4m4-4 4 4M4 16v2a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-2" strokeLinecap="round" strokeLinejoin="round" />
                  </svg>
                </div>
                <p className="text-[14px] text-neutral-900">Drop a photo or click to choose</p>
                <p className="mt-1 text-[12px] text-neutral-400">JPG or PNG</p>
              </div>
            )}
            {shownPhoto && (
              <div className="absolute bottom-3 right-3 rounded-md bg-white px-2.5 py-1 text-[12px] font-medium text-neutral-900 opacity-0 shadow-[0_0_0_1px_rgba(0,0,0,0.06)] transition-opacity group-hover:opacity-100">
                Replace
              </div>
            )}
          </div>
          <input ref={fileRef} type="file" accept="image/*" className="hidden" onChange={(e) => pickPhoto(e.target.files?.[0])} />
        </div>

        <div>
          <Label>Name</Label>
          <Input value={name} onChange={(e) => setName(e.target.value)} placeholder="How should we call this avatar?" maxLength={60} />
        </div>

        <div>
          <Label>Voice</Label>
          <Segmented<VoiceMode>
            value={voiceMode}
            onChange={setVoiceMode}
            options={[
              { value: "default", label: "Default voice" },
              { value: "custom", label: "Clone my voice" },
            ]}
          />

          {voiceMode === "custom" && (
            <div className="mt-4 space-y-3 animate-[fade-up_300ms_ease-out]">
              <button
                type="button"
                onClick={() => voiceRef.current?.click()}
                className="flex h-16 w-full items-center justify-between rounded-lg border border-dashed border-neutral-300 px-4 text-left transition-colors hover:border-neutral-400"
              >
                <span className="text-[14px] text-neutral-900">{voice ? voice.name : existing?.has_custom_voice ? "Keep saved voice, or choose a new clip" : "Choose a voice clip"}</span>
                <span className="text-[12px] text-neutral-400">
                  {voice ? "Change" : "8–12 seconds of you speaking"}
                </span>
              </button>
              <input ref={voiceRef} type="file" accept="audio/*,video/*" className="hidden" onChange={(e) => setVoice(e.target.files?.[0] ?? null)} />
              <p className="text-[12px] leading-relaxed text-neutral-400">
                Speak one clear sentence in a quiet room, with no music or background noise. Clips are trimmed to 12 seconds.
              </p>
              {voice && (
                <div className="space-y-2">
                  <Label hint="Optional">What you say in the clip</Label>
                  <Textarea rows={2} value={transcript} onChange={(e) => setTranscript(e.target.value)} placeholder="Type it exactly. Leave empty to auto-detect." />
                </div>
              )}
            </div>
          )}
        </div>

        {error && <p className="text-[13px] text-red-600">{error}</p>}

        <div className="flex items-center justify-end gap-2 border-t border-neutral-100 pt-6">
          {onCancel && (
            <Button type="button" variant="ghost" onClick={onCancel}>
              Cancel
            </Button>
          )}
          <Button type="submit" disabled={!canSave || saving}>
            {saving ? "Saving…" : existing ? "Save changes" : "Save avatar"}
          </Button>
        </div>
      </form>
    </div>
  );
}
