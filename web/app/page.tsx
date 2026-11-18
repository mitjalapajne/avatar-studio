"use client";

import { useEffect, useState } from "react";
import { api, Avatar, SystemStatus } from "@/lib/api";
import { AvatarSetup } from "@/components/avatar-setup";
import { Workspace } from "@/components/workspace";

export default function Home() {
  const [avatar, setAvatar] = useState<Avatar | null | undefined>(undefined); // undefined = loading
  const [system, setSystem] = useState<SystemStatus | null>(null);
  const [editing, setEditing] = useState(false);
  const [offline, setOffline] = useState(false);

  useEffect(() => {
    api
      .getAvatar()
      .then((a) => {
        setAvatar(a);
        setOffline(false);
      })
      .catch(() => setOffline(true));
    api.status().then(setSystem).catch(() => {});
  }, []);

  return (
    <div className="flex min-h-screen flex-col">
      <header className="sticky top-0 z-10 border-b border-neutral-100 bg-white/80 backdrop-blur-md">
        <div className="mx-auto flex h-14 max-w-6xl items-center justify-between px-6">
          <span className="text-[15px] font-semibold tracking-[-0.01em]">Avatar Studio</span>
          {avatar && !editing && (
            <span className="text-[13px] text-neutral-400">{avatar.name}</span>
          )}
        </div>
      </header>

      <main className="mx-auto w-full max-w-6xl flex-1 px-6 py-12 lg:py-16">
        {offline ? (
          <div className="mx-auto max-w-md pt-24 text-center">
            <p className="text-[16px] font-medium">Can’t reach the server</p>
            <p className="mt-2 text-[14px] leading-relaxed text-neutral-500">
              Start the API with <code className="rounded bg-neutral-100 px-1.5 py-0.5 text-[12px]">uvicorn main:app --port 8000</code> in the <code className="rounded bg-neutral-100 px-1.5 py-0.5 text-[12px]">server</code> folder.
            </p>
          </div>
        ) : avatar === undefined ? null : avatar === null || editing ? (
          <AvatarSetup
            existing={avatar}
            onCancel={avatar ? () => setEditing(false) : undefined}
            onSaved={(a) => {
              setAvatar(a);
              setEditing(false);
            }}
          />
        ) : (
          <Workspace avatar={avatar} system={system} onEditAvatar={() => setEditing(true)} />
        )}
      </main>
    </div>
  );
}
