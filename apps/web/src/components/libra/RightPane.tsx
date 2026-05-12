"use client";

import { useState } from "react";

import type { TranscriptEntry } from "@/types/voice";

import { MemoryPanel } from "./MemoryPanel";
import { TranscriptPanel } from "./TranscriptPanel";

interface Props {
  entries: TranscriptEntry[];
  onClearTranscript: () => void;
  memoryRefreshKey: number;
}

type Tab = "transcript" | "memory";

export function RightPane({
  entries,
  onClearTranscript,
  memoryRefreshKey,
}: Props) {
  const [tab, setTab] = useState<Tab>("transcript");

  return (
    <div className="flex h-full min-h-0 flex-col gap-3">
      <div className="flex gap-1">
        <TabButton active={tab === "transcript"} onClick={() => setTab("transcript")}>
          Transcript
        </TabButton>
        <TabButton active={tab === "memory"} onClick={() => setTab("memory")}>
          Memory
        </TabButton>
      </div>
      <div className="flex min-h-0 flex-1 flex-col">
        {tab === "transcript" ? (
          <TranscriptPanel entries={entries} onClear={onClearTranscript} />
        ) : (
          <MemoryPanel refreshKey={memoryRefreshKey} />
        )}
      </div>
    </div>
  );
}

function TabButton({
  active,
  onClick,
  children,
}: {
  active: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={[
        "flex-1 rounded border px-2 py-1.5 font-mono text-[10px] uppercase tracking-[0.22em] transition",
        active
          ? "border-white/30 bg-white/[0.04] text-white"
          : "border-white/[0.07] text-white/45 hover:border-white/15 hover:text-white/70",
      ].join(" ")}
    >
      {children}
    </button>
  );
}
