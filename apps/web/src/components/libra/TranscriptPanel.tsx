"use client";

import clsx from "clsx";
import { useEffect, useRef } from "react";
import type { TranscriptEntry } from "@/types/voice";

interface Props {
  entries: TranscriptEntry[];
  onClear: () => void;
}

const ROLE_LABEL: Record<TranscriptEntry["role"], string> = {
  user: "You",
  assistant: "Libra",
  system: "System",
};

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
            {entries.map((e) => (
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
                  {e.partial ? <span className="text-white/30"> …</span> : null}
                </p>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
