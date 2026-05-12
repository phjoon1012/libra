"use client";

import clsx from "clsx";
import type { VoiceProviderDescriptor, VoiceProviderId } from "@/types/voice";

interface Props {
  providers: VoiceProviderDescriptor[];
  active: VoiceProviderId;
  disabled?: boolean;
  onChange: (id: VoiceProviderId) => void;
}

export function ProviderSwitcher({ providers, active, disabled, onChange }: Props) {
  return (
    <div className="flex flex-col gap-3">
      <span className="panel-title">Provider</span>
      <div className="flex flex-col gap-2">
        {providers.map((p) => {
          const isActive = p.id === active;
          return (
            <button
              key={p.id}
              type="button"
              disabled={disabled}
              onClick={() => onChange(p.id)}
              className={clsx(
                "group rounded-md border px-3 py-2.5 text-left transition disabled:cursor-not-allowed disabled:opacity-40",
                isActive
                  ? "border-white/40 bg-white/[0.04]"
                  : "border-white/10 hover:border-white/25",
              )}
            >
              <div className="flex items-center justify-between gap-2">
                <span
                  className={clsx(
                    "font-mono text-[11px] uppercase tracking-[0.22em]",
                    isActive ? "text-white" : "text-white/70",
                  )}
                >
                  {p.label}
                </span>
                <span
                  className={clsx(
                    "font-mono text-[9px] uppercase tracking-[0.22em]",
                    p.status === "ready" ? "text-white/60" : "text-white/35",
                  )}
                >
                  {p.status}
                </span>
              </div>
              <p className="mt-1.5 text-[11px] leading-snug text-white/45">
                {p.description}
              </p>
            </button>
          );
        })}
      </div>
    </div>
  );
}
