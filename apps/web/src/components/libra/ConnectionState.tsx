"use client";

import clsx from "clsx";
import type { ConnectionState as State } from "@/types/voice";

const LABEL: Record<State, string> = {
  disconnected: "Standby",
  connecting: "Linking",
  listening: "Listening",
  thinking: "Processing",
  speaking: "Responding",
  error: "Fault",
};

const DOT: Record<State, string> = {
  disconnected: "bg-white/30",
  connecting: "bg-white/70 animate-breathe",
  listening: "bg-white animate-breathe",
  thinking: "bg-white animate-breathe",
  speaking: "bg-white",
  error: "bg-white/50",
};

export function ConnectionStateBadge({ state }: { state: State }) {
  const muted = state === "disconnected" || state === "error";
  return (
    <div className="inline-flex items-center gap-2.5 font-mono text-[10px] uppercase tracking-ultra">
      <span className={clsx("h-1.5 w-1.5 rounded-full", DOT[state])} />
      <span className={muted ? "text-white/40" : "text-white/80"}>{LABEL[state]}</span>
    </div>
  );
}
