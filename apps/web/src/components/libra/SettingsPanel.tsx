"use client";

import type { VoiceProviderId, VoiceSettings } from "@/types/voice";

interface Props {
  provider: VoiceProviderId;
  voice: string;
  onVoiceChange: (value: string) => void;
  instructions: string;
  onInstructionsChange: (value: string) => void;
  voiceSettings: VoiceSettings;
  onVoiceSettingsChange: (next: VoiceSettings) => void;
  memoryEnabled: boolean;
  onMemoryEnabledChange: (value: boolean) => void;
  disabled?: boolean;
}

const OPENAI_VOICE_OPTIONS = ["alloy", "verse", "aria", "coral", "sage", "ash"];

interface SliderProps {
  label: string;
  value: number;
  min: number;
  max: number;
  step: number;
  disabled?: boolean;
  onChange: (n: number) => void;
}

function Slider({ label, value, min, max, step, disabled, onChange }: SliderProps) {
  return (
    <label className="flex flex-col gap-1.5">
      <span className="flex items-center justify-between font-mono text-[10px] uppercase tracking-[0.22em] text-white/45">
        <span>{label}</span>
        <span className="text-white/70">{value.toFixed(2)}</span>
      </span>
      <input
        type="range"
        min={min}
        max={max}
        step={step}
        value={value}
        disabled={disabled}
        onChange={(e) => onChange(Number(e.target.value))}
        className="h-1 w-full cursor-pointer appearance-none rounded bg-white/10 accent-white disabled:cursor-not-allowed disabled:opacity-40"
      />
    </label>
  );
}

export function SettingsPanel({
  provider,
  voice,
  onVoiceChange,
  instructions,
  onInstructionsChange,
  voiceSettings,
  onVoiceSettingsChange,
  memoryEnabled,
  onMemoryEnabledChange,
  disabled,
}: Props) {
  const isOpenAI = provider === "openai-realtime";
  const isEleven = provider === "elevenlabs-openai";

  return (
    <div className="flex flex-col gap-3">
      <span className="panel-title">Settings</span>

      {isOpenAI ? (
        <label className="flex flex-col gap-1.5">
          <span className="font-mono text-[10px] uppercase tracking-[0.22em] text-white/45">
            Voice
          </span>
          <select
            disabled={disabled}
            value={voice}
            onChange={(e) => onVoiceChange(e.target.value)}
            className="rounded-md border border-white/10 bg-transparent px-2.5 py-1.5 text-sm text-white outline-none transition focus:border-white/40 disabled:opacity-40"
          >
            {OPENAI_VOICE_OPTIONS.map((v) => (
              <option key={v} value={v} className="bg-black text-white">
                {v}
              </option>
            ))}
          </select>
        </label>
      ) : null}

      {isEleven ? (
        <div className="flex flex-col gap-3">
          <Slider
            label="Stability"
            value={voiceSettings.stability}
            min={0}
            max={1}
            step={0.05}
            disabled={disabled}
            onChange={(n) => onVoiceSettingsChange({ ...voiceSettings, stability: n })}
          />
          <Slider
            label="Similarity"
            value={voiceSettings.similarityBoost}
            min={0}
            max={1}
            step={0.05}
            disabled={disabled}
            onChange={(n) =>
              onVoiceSettingsChange({ ...voiceSettings, similarityBoost: n })
            }
          />
          <Slider
            label="Speed"
            value={voiceSettings.speed}
            min={0.7}
            max={1.2}
            step={0.05}
            disabled={disabled}
            onChange={(n) => onVoiceSettingsChange({ ...voiceSettings, speed: n })}
          />
        </div>
      ) : null}

      <label className="flex flex-col gap-1.5">
        <span className="font-mono text-[10px] uppercase tracking-[0.22em] text-white/45">
          Instructions
        </span>
        <textarea
          disabled={disabled}
          value={instructions}
          onChange={(e) => onInstructionsChange(e.target.value)}
          rows={5}
          className="resize-none rounded-md border border-white/10 bg-transparent px-2.5 py-1.5 font-mono text-[11px] leading-relaxed text-white/80 outline-none transition focus:border-white/40 disabled:opacity-40"
        />
      </label>

      <label className="flex items-center justify-between gap-3">
        <span className="flex flex-col gap-0.5">
          <span className="font-mono text-[10px] uppercase tracking-[0.22em] text-white/55">
            Memory
          </span>
          <span className="text-[10px] leading-snug text-white/35">
            Recall + distill across sessions
          </span>
        </span>
        <button
          type="button"
          role="switch"
          aria-checked={memoryEnabled}
          disabled={disabled}
          onClick={() => onMemoryEnabledChange(!memoryEnabled)}
          className={[
            "relative h-5 w-9 rounded-full border transition",
            memoryEnabled
              ? "border-white/40 bg-white/20"
              : "border-white/15 bg-transparent",
            disabled ? "cursor-not-allowed opacity-40" : "cursor-pointer",
          ].join(" ")}
        >
          <span
            className={[
              "absolute top-1/2 h-3.5 w-3.5 -translate-y-1/2 rounded-full bg-white transition",
              memoryEnabled ? "left-[18px]" : "left-0.5",
            ].join(" ")}
          />
        </button>
      </label>

      <p className="text-[10px] leading-snug text-white/35">
        Applied on next connect. Keys stay server-side.
      </p>
    </div>
  );
}
