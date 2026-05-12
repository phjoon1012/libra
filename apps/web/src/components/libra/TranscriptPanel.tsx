"use client";

import clsx from "clsx";
import { useEffect, useRef } from "react";
import type { ToolEntry, TranscriptEntry } from "@/types/voice";

interface Props {
  entries: TranscriptEntry[];
  onClear: () => void;
}

const ROLE_LABEL: Record<"user" | "assistant" | "system", string> = {
  user: "You",
  assistant: "Libra",
  system: "System",
};

const STATE_DOT: Record<ToolEntry["state"], string> = {
  started: "bg-white/40",
  completed: "bg-emerald-400 shadow-[0_0_6px_rgba(52,211,153,0.55)]",
  denied: "bg-red-400 shadow-[0_0_6px_rgba(248,113,113,0.55)]",
  pending: "bg-amber-400 shadow-[0_0_6px_rgba(251,191,36,0.55)]",
};

const STATE_LABEL: Record<ToolEntry["state"], string> = {
  started: "Running",
  completed: "Done",
  denied: "Denied",
  pending: "Awaiting approval",
};

function formatArgs(args: Record<string, unknown>): string {
  const keys = Object.keys(args);
  if (keys.length === 0) return "";
  const parts = keys.map((k) => `${k}=${JSON.stringify(args[k])}`);
  return parts.join(" ");
}

function ToolRow({ entry }: { entry: ToolEntry }) {
  return (
    <div className="rounded border border-white/[0.07] bg-white/[0.02] p-3">
      <div className="flex items-center justify-between gap-3">
        <span className="flex items-center gap-2.5">
          <span
            aria-hidden
            className={clsx(
              "block h-1.5 w-1.5 rounded-full transition-colors",
              STATE_DOT[entry.state],
            )}
          />
          <span className="font-mono text-[10px] uppercase tracking-[0.22em] text-white">
            Tool · {entry.toolName}
          </span>
        </span>
        <span className="font-mono text-[9px] uppercase tracking-[0.22em] text-white/40">
          {STATE_LABEL[entry.state]}
          {entry.durationMs ? ` · ${entry.durationMs}ms` : ""}
        </span>
      </div>
      {Object.keys(entry.args).length > 0 ? (
        <p className="mt-2 truncate font-mono text-[10.5px] text-white/45">
          {formatArgs(entry.args)}
        </p>
      ) : null}
      {entry.state === "completed" && entry.content ? (
        <p
          className={clsx(
            "mt-2 text-[12.5px] leading-relaxed",
            entry.error ? "text-red-300/80" : "text-white/75",
          )}
        >
          {entry.content}
        </p>
      ) : null}
      {entry.state === "denied" && entry.reason ? (
        <p className="mt-2 text-[12px] text-red-300/80">{entry.reason}</p>
      ) : null}
      {entry.state === "pending" ? (
        <p className="mt-2 text-[12px] text-amber-300/80">
          {entry.reason ?? "Waiting on user approval."}
        </p>
      ) : null}
    </div>
  );
}

export function TranscriptPanel({ entries, onClear }: Props) {
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    scrollRef.current?.scrollTo({
      top: scrollRef.current.scrollHeight,
      behavior: "smooth",
    });
  }, [entries]);

  return (
    <div className="flex h-full flex-col gap-3">
      <div className="flex items-center justify-between">
        <span className="panel-title">Transcript</span>
        <button
          type="button"
          onClick={onClear}
          className="font-mono text-[10px] uppercase tracking-[0.22em] text-white/30 transition hover:text-white"
        >
          clear
        </button>
      </div>
      <div
        ref={scrollRef}
        className="flex-1 overflow-y-auto pr-1 [scrollbar-color:rgba(255,255,255,0.15)_transparent] [scrollbar-width:thin]"
      >
        {entries.length === 0 ? (
          <p className="font-mono text-[11px] text-white/30">
            No transcript yet.
          </p>
        ) : (
          <ul className="flex flex-col gap-4">
            {entries.map((e) =>
              e.kind === "tool" ? (
                <li key={e.id}>
                  <ToolRow entry={e} />
                </li>
              ) : (
                <li key={e.id} className="leading-snug">
                  <div className="flex items-baseline gap-2">
                    <span className="font-mono text-[10px] uppercase tracking-[0.22em] text-white/40">
                      {ROLE_LABEL[e.role]}
                    </span>
                    <span className="font-mono text-[9px] text-white/20">
                      {new Date(e.ts).toLocaleTimeString()}
                    </span>
                  </div>
                  <p
                    className={clsx(
                      "mt-1 text-[13px] leading-relaxed",
                      e.role === "assistant" ? "text-white" : "text-white/75",
                    )}
                  >
                    {e.text}
                    {e.partial ? (
                      <span className="text-white/30"> …</span>
                    ) : null}
                  </p>
                </li>
              ),
            )}
          </ul>
        )}
      </div>
    </div>
  );
}
